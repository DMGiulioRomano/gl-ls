"""Forma compatta a cicli come valore di ``let:`` (granstudies ``faa64d0``).

``[pattern, end_time, n_reps, interp?, time_dist?, wrap?]``: la sintassi loop
dell'engine, ammessa nelle manopole di documento e di gruppo. Qui si verifica
il riconoscimento (che non collide con le forme statiche di Env), i due
vincoli propri dello studio (``end_time`` = 1, punti a coppie), il warning
sulle ``x%`` fuori scala e le feature d'appoggio: hover, inlay, semantic token
dei posizionali, snippet di completamento.
"""
from lsprotocol import types

from glls import (actions, completion, diagnostics, hover, inlay, model,
                  semtokens, yamlpos)

BASE = """study_id: t
duration: 20
base:
  onset: 0
  duration: 6
  sample: corpus.wav
  volume:
    expr: "s * 3"
axes:
  density:
    baseline: 20
    values: [10, 30]
"""

VENTAGLIO = "[[[0, 0], [25, 1]], 1, 4, 'linear', null, true]"


def _doc(let_value):
    text = BASE + f"let:\n  s: {let_value}\n"
    doc = yamlpos.parse(text)
    return doc, model.build(doc), text


def _codes(let_value):
    doc, m, _ = _doc(let_value)
    return {d.code for d in diagnostics.collect(doc, m)}


# --- riconoscimento -----------------------------------------------------------


def test_predicato_non_collide_con_le_forme_statiche_di_env():
    assert not model.is_compact_env([[0, 0], [1, 1]])   # breakpoint
    assert not model.is_compact_env([0, 1])             # shorthand [a, b]
    assert not model.is_compact_env(4)
    assert not model.is_compact_env([[[0, 0], [25, 1]], 1])   # troppo corta
    assert model.is_compact_env([[[0, 0], [25, 1]], 1, 4])


def test_ventaglio_valido_nessuna_diagnostica():
    assert _codes(VENTAGLIO) == set()


def test_envelope_disegnato_resta_pulito():
    assert _codes("[[0, 1], [1, 2]]") == set()


# --- vincoli propri dello studio ----------------------------------------------


def test_end_time_in_secondi_e_errore():
    assert "let-compact-end-time" in _codes("[[[0, 0], [25, 1]], 50, 4]")


def test_end_time_errore_ha_il_quick_fix_a_1():
    doc, m, _ = _doc("[[[0, 0], [25, 1]], 50, 4]")
    ds = diagnostics.collect(doc, m)
    rng = types.Range(types.Position(0, 0), types.Position(20, 0))
    acts = actions.collect(doc, m, "file:///x", rng, ds, {})
    fix = [a for a in acts if a.title == "Sostituisci con '1'"]
    assert len(fix) == 1
    (edit,) = fix[0].edit.changes["file:///x"]
    assert edit.new_text == "1"


def test_punto_del_pattern_a_tre_elementi_e_errore():
    assert "let-compact-point" in _codes("[[[0, 0], [25, 1, 'step']], 1, 4]")


def test_x_fuori_scala_e_warning():
    doc, m, _ = _doc("[[[0, 0], [125, 1]], 1, 4]")
    warns = [d for d in diagnostics.collect(doc, m)
             if d.code == "let-compact-x"]
    assert len(warns) == 1
    assert warns[0].severity == types.DiagnosticSeverity.Warning


def test_vincoli_valgono_anche_nel_let_di_gruppo():
    text = BASE + (
        "streams:\n"
        "  a:\n"
        "    let:\n"
        "      s: [[[0, 0], [25, 1]], 50, 4]\n"
    )
    doc = yamlpos.parse(text)
    codes = {d.code for d in diagnostics.collect(doc, model.build(doc))}
    assert "let-compact-end-time" in codes


def test_la_diagnostica_punta_allo_slot_sbagliato():
    doc, m, text = _doc("[[[0, 0], [25, 1]], 50, 4]")
    (d,) = diagnostics.collect(doc, m)
    line = text.splitlines()[d.range.start.line]
    assert line[d.range.start.character:d.range.end.character] == "50"


# --- feature d'appoggio -------------------------------------------------------


def test_hover_sulla_manopola_riassume_l_espansione():
    doc, m, text = _doc(VENTAGLIO)
    row = next(i for i, l in enumerate(text.splitlines()) if l.startswith("  s:"))
    h = hover.hover(doc, m, row, 2)
    assert h is not None
    assert "4 cicli" in h.contents.value and "vertice 25%" in h.contents.value
    assert "end_time` deve essere `1`" in h.contents.value


def test_inlay_hint_sul_valore_compatto():
    doc, m, text = _doc(VENTAGLIO)
    labels = [h.label for h in inlay.hints(doc, m, 0, len(text.splitlines()))]
    assert "4 cicli · vertice 25% · wrap" in labels


def test_i_posizionali_non_sono_breakpoint():
    doc, m, text = _doc(VENTAGLIO)
    data = semtokens.tokens(doc, m)
    row = next(i for i, l in enumerate(text.splitlines()) if l.startswith("  s:"))
    line, col, got = 0, 0, {}
    for i in range(0, len(data), 5):
        d_line, d_col, length, tok, _mod = data[i:i + 5]
        line += d_line
        col = col + d_col if d_line == 0 else d_col
        if line == row:
            got[text.splitlines()[row][col:col + length]] = tok
    assert got["1"] == semtokens._T["number"]        # end_time
    assert got["4"] == semtokens._T["number"]        # n_reps
    assert got["'linear'"] == semtokens._T["enumMember"]
    assert got["true"] == semtokens._T["enumMember"]
    # i numeri del pattern restano senza token: non sono posizionali
    assert "25" not in got


def test_in_spread_let_niente_riassunto():
    # spread.let ha un resolver suo (banda per voce / expr su i/n) che la forma
    # compatta non la conosce: annotarla la' direbbe una cosa falsa
    text = BASE + (
        "streams:\n"
        "  fan:\n"
        "    spread:\n"
        "      n: 3\n"
        "      let:\n"
        f"        s: {VENTAGLIO}\n"
        "      over:\n"
        "        base.onset: {values: [0, 1, 2]}\n"
    )
    doc = yamlpos.parse(text)
    m = model.build(doc)
    rows = text.splitlines()
    row = next(i for i, l in enumerate(rows) if l.strip().startswith("s:"))
    assert inlay.hints(doc, m, 0, len(rows)) == []
    assert hover.hover(doc, m, row, 9) is None


def test_snippet_della_forma_compatta_nel_contesto_let():
    text = "study_id: t\nlet:\n  \n"
    doc = yamlpos.parse(text)
    items = completion.complete(doc, model.build(doc), 2, 2)
    (item,) = [i for i in items if i.label == "manopola_ciclica"]
    assert item.insert_text.startswith("${1:s}: [[[0, ${2:0}]")
    assert "linear,cubic,step" in item.insert_text
