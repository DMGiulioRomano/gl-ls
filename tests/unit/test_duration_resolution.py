"""La catena di risoluzione della ``duration`` (granstudies #42, gl-ls #36).

``duration:`` non e' piu' una chiave top-level: ogni durata sta accanto alla
cosa di cui e' la durata. Quella di uno **stream** si risolve per catena
(``duration:`` di entry > ``base.duration``), con la durata di replica di
``versions:``/``percorso:`` come default di documento; quella del **documento**
non si scrive, e' ``max(onset + duration)``.

Qui si verifica la catena nel modello e le feature che ne dipendono — la stima
anti-runaway della camminata e la code lens dei breakpoint, che leggevano il
top-level e con la migrazione erano diventate silenziosamente morte.
"""
from glls import actions, diagnostics, hover, lens, model, yamlpos

BASE = """study_id: t
base:
  onset: 0
  duration: 6
  sample: corpus.wav
axes:
  density:
    baseline: 20
    values: [10, 30]
"""

NO_BASE_DUR = BASE.replace("  duration: 6\n", "")


def _dm(text):
    doc = yamlpos.parse(text)
    return doc, model.build(doc)


# --- catena nel modello -----------------------------------------------------


def test_document_duration_from_base():
    _doc, m = _dm(BASE)
    assert m.duration_for() == 6.0


def test_stream_entry_duration_wins_over_base():
    _doc, m = _dm(BASE + "streams:\n  a:\n    duration: 12\n")
    assert m.duration_for("a") == 12.0
    assert m.duration_for() == 6.0


def test_stream_base_duration_wins_over_document():
    _doc, m = _dm(BASE + "streams:\n  a:\n    base:\n      duration: 12\n")
    assert m.duration_for("a") == 12.0


def test_stream_dotted_base_duration_is_the_same_key():
    _doc, m = _dm(BASE + "streams:\n  a:\n    base.duration: 12\n")
    assert m.duration_for("a") == 12.0


def test_stream_without_duration_inherits_the_document_default():
    _doc, m = _dm(BASE + "streams:\n  a:\n    base:\n      volume: -6\n")
    assert m.duration_for("a") == 6.0


def test_versions_duration_is_the_document_default():
    _doc, m = _dm(NO_BASE_DUR + "versions:\n  duration: 50\n  d0: {values: [1, 2]}\n")
    assert m.duration_for() == 50.0
    assert m.replica_duration_source == "versions.duration"


def test_percorso_declares_a_replica_duration_even_when_implicit():
    # senza ``percorso.duration`` le istanze sono legate: la durata e'
    # l'intervallo verso la prossima, dedotto da arco/passo
    _doc, m = _dm(NO_BASE_DUR + "percorso:\n  arco: 100\n  passo: 10\n")
    assert m.replica_duration_source == "percorso"
    assert m.declares_duration() is True
    # non e' statica: nessun numero da dare a chi stima
    assert m.duration_for() is None


def test_top_level_duration_is_not_a_source_but_stays_readable():
    # tenuta come ultima rete perche' le stime non muoiano su un documento non
    # ancora migrato — che ha gia' la sua diagnostica
    _doc, m = _dm("duration: 20\n" + NO_BASE_DUR)
    assert m.has_top_duration is True
    assert m.duration_for() == 20.0


# --- le stime che dipendono dalla durata risolta -----------------------------


def _walk(text):
    doc, m = _dm(text)
    return {d.code for d in diagnostics.collect(doc, m)}


RUNAWAY_AXIS = NO_BASE_DUR.replace("    values: [10, 30]\n",
                                   "    base: 5\n    range: 10\n")


def test_walk_runaway_uses_base_duration():
    text = (RUNAWAY_AXIS.replace("  onset: 0\n", "  onset: 0\n  duration: 600\n")
            + "stack:\n  density:\n    base: 2000\n")
    assert "walk-runaway" in _walk(text)


def test_walk_runaway_uses_the_stream_own_duration():
    # base.duration corta, override di stream lunghissimo: il runaway e' dello
    # stream, e la stima va fatta sulla SUA durata
    text = (RUNAWAY_AXIS.replace("  onset: 0\n", "  onset: 0\n  duration: 1\n")
            + "stack:\n  density:\n    base: 5\n"
            + "streams:\n  a:\n    duration: 600\n"
              "    stack:\n      density:\n        base: 2000\n")
    assert "walk-runaway" in _walk(text)


def test_walk_runaway_silent_when_no_duration_resolves():
    text = RUNAWAY_AXIS + "stack:\n  density:\n    base: 2000\n"
    codes = _walk(text)
    assert "walk-runaway" not in codes and "stack-duration" in codes


def test_lens_breakpoint_estimate_on_resolved_duration():
    text = (BASE.replace("  duration: 6\n", "  duration: 60\n")
            .replace("    values: [10, 30]\n", "    base: 5\n    range: 10\n")
            + "stack:\n  density:\n    base: 10\n")
    doc, m = _dm(text)
    titles = [l.command.title for l in lens.lenses(doc, m)]
    walk_title = next(t for t in titles if t.startswith("camminata-X"))
    # camminata deterministica a 10 hz (nessun 'range'): 600 punti su 60 s
    assert "~600 breakpoint su 60s" in walk_title


# --- hover e quick fix ------------------------------------------------------


def _hover_at(text, line, col):
    doc, m = _dm(text)
    h = hover.hover(doc, m, line, col)
    return h.contents.value if h is not None else None


def test_hover_on_top_level_duration_says_it_is_forbidden():
    text = "duration: 20\n" + BASE
    md = _hover_at(text, 0, 2)
    assert "Chiave vietata" in md
    # e dice dove la durata si risolve *in questo* documento
    assert "`base.duration` c'e' gia'" in md


def test_hover_on_top_level_duration_points_at_the_replica_source():
    text = ("duration: 20\n" + NO_BASE_DUR
            + "versions:\n  duration: 50\n  d0: {values: [1, 2]}\n")
    assert "versions.duration" in _hover_at(text, 0, 2)


def _quickfix_titles(text):
    doc, m = _dm(text)
    diags = diagnostics.collect(doc, m)
    return [a.title for a in actions.quickfixes(doc, "file:///t.yml", diags)]


def _apply(text, edits):
    offs, acc = [], 0
    for line in text.split("\n"):
        offs.append(acc)
        acc += len(line) + 1

    def off(p):
        return offs[p.line] + p.character if p.line < len(offs) else len(text)

    out = text
    for e in sorted(edits, key=lambda e: off(e.range.start), reverse=True):
        out = out[:off(e.range.start)] + e.new_text + out[off(e.range.end):]
    return out


def _action_named(text, needle):
    doc, m = _dm(text)
    diags = diagnostics.collect(doc, m)
    acts = actions.quickfixes(doc, "file:///t.yml", diags)
    return next(a for a in acts if needle in a.title)


def test_quickfix_moves_top_level_duration_into_base():
    text = "duration: 20\n" + BASE.replace("  duration: 6\n", "")
    act = _action_named(text, "base.duration")
    out = _apply(text, act.edit.changes["file:///t.yml"])
    assert out.startswith("study_id: t\n")
    assert "\n  duration: 20\n" in out and "\nduration: 20\n" not in out


def test_quickfix_offers_versions_step_when_versions_has_no_step():
    text = ("duration: 20\n" + BASE.replace("  duration: 6\n", "")
            + "versions:\n  d0: {values: [1, 2]}\n")
    titles = _quickfix_titles(text)
    assert any("base.duration" in t for t in titles)
    assert any("versions.duration" in t for t in titles)


def test_quickfix_does_not_offer_versions_when_the_step_is_there():
    text = ("duration: 20\n" + BASE.replace("  duration: 6\n", "")
            + "versions:\n  duration: 50\n  d0: {values: [1, 2]}\n")
    assert not any("versions.duration" in t for t in _quickfix_titles(text))


def test_quickfix_add_base_duration_creates_the_block_when_base_is_absent():
    text = """study_id: t
axes:
  density:
    baseline: 20
    values: [10, 30]
stack: {}
"""
    act = _action_named(text, "Aggiungi 'base:'")
    out = _apply(text, act.edit.changes["file:///t.yml"])
    assert "base:\n  duration: 30\n" in out


def test_quickfix_add_base_duration_into_an_existing_block():
    text = BASE.replace("  duration: 6\n", "") + "stack: {}\n"
    act = _action_named(text, "Aggiungi 'duration' a 'base:'")
    out = _apply(text, act.edit.changes["file:///t.yml"])
    assert "base:\n  duration: 30\n  onset: 0\n" in out
