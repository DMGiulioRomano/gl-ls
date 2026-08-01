"""Unit test delle code action: ricalcoli duration e conversione unita'."""
from lsprotocol import types

from glls import actions, model, yamlpos


def _full_range():
    return types.Range(start=types.Position(0, 0), end=types.Position(999, 0))


def _apply(text, edits):
    """Applica TextEdit non sovrapposti al testo (per verificare il risultato)."""
    lines = text.splitlines(keepends=True)
    offs = []
    pos = 0
    for ln in lines:
        offs.append(pos)
        pos += len(ln)
    def off(p):
        return offs[p.line] + p.character if p.line < len(offs) else len(text)
    out = text
    for e in sorted(edits, key=lambda e: off(e.range.start), reverse=True):
        out = out[:off(e.range.start)] + e.new_text + out[off(e.range.end):]
    return out


# ---------------------------------------------------------------------------
# duration_actions: il time_mode per-stream deve vincere su quello top-level


DUR_TEXT = """study_id: t
base:
  duration: 6
  sample: corpus.wav
  time_mode: absolute
  density: [[0, 10], [6, 20]]
axes:
  density:
    path: density
    baseline: 20
    values: [10, 30]
streams:
  v:
    base:
      time_mode: normalized
      density: [[0, 10], [1, 20]]
"""


def test_duration_rescale_respects_stream_time_mode():
    doc = yamlpos.parse(DUR_TEXT)
    m = model.build(doc)
    acts = actions.duration_actions(doc, m, "file:///t.yml", _full_range(),
                                    {("base", "duration"): (20.0, 40.0)})
    assert len(acts) == 1
    new_text = _apply(DUR_TEXT, acts[0].edit.changes["file:///t.yml"])
    # gli envelope absolute di base: riscalati (x2)
    assert "density: [[0, 10], [12, 20]]" in new_text
    # gli envelope normalized dello stream v: NON riscalati
    assert "density: [[0, 10], [1, 20]]" in new_text


def test_duration_rescale_includes_stream_absolute_override():
    text = DUR_TEXT.replace("time_mode: absolute", "time_mode: normalized") \
                   .replace("      time_mode: normalized",
                            "      time_mode: absolute") \
                   .replace("  density: [[0, 10], [6, 20]]",
                            "  density: [[0, 10], [1, 20]]") \
                   .replace("      density: [[0, 10], [1, 20]]",
                            "      density: [[0, 10], [6, 20]]")
    doc = yamlpos.parse(text)
    m = model.build(doc)
    acts = actions.duration_actions(doc, m, "file:///t.yml", _full_range(),
                                    {("base", "duration"): (20.0, 40.0)})
    assert len(acts) == 1
    new_text = _apply(text, acts[0].edit.changes["file:///t.yml"])
    # base: normalized, intatto
    assert "  density: [[0, 10], [1, 20]]" in new_text
    # stream v: absolute, riscalato
    assert "      density: [[0, 10], [12, 20]]" in new_text


# ---------------------------------------------------------------------------
# Lo SCOPE della riscala: quali envelope vivono sulla durata cambiata.
#
# Finche' la durata era una sola, riscalare tutti i blocchi ``base:`` era
# corretto per costruzione. Con la durata per-stream (granstudies #42) non lo
# e' piu': uno stream con la propria ``duration:`` non eredita il default di
# documento, quindi la sua timeline non si muove quando quello cambia.

SCOPE_TEXT = """study_id: t
base:
  duration: 30
  sample: corpus.wav
  time_mode: absolute
  density: [[0, 10], [20, 20]]
axes:
  density:
    baseline: 20
    values: [10, 30]
streams:
  proprio:
    duration: 100
    base:
      density: [[0, 5], [100, 40]]
  eredita:
    base:
      density: [[0, 1], [20, 9]]
"""


def _rescale(text, pending):
    doc = yamlpos.parse(text)
    m = model.build(doc)
    acts = actions.duration_actions(doc, m, "file:///t.yml", _full_range(), pending)
    if not acts:
        return None
    return _apply(text, acts[0].edit.changes["file:///t.yml"])


def test_document_duration_skips_streams_with_their_own():
    out = _rescale(SCOPE_TEXT, {("base", "duration"): (20.0, 30.0)})
    assert "  density: [[0, 10], [30, 20]]" in out        # base: riscalato
    assert "      density: [[0, 1], [30, 9]]" in out      # eredita: riscalato
    # 'proprio' dichiara duration: 100 e non eredita: la sua timeline non si
    # e' mossa, riscalarla porterebbe il breakpoint finale oltre il bordo
    assert "      density: [[0, 5], [100, 40]]" in out


def test_stream_duration_touches_only_that_stream():
    out = _rescale(SCOPE_TEXT, {("streams", "proprio", "duration"): (50.0, 100.0)})
    assert "      density: [[0, 5], [200, 40]]" in out    # proprio: riscalato
    assert "  density: [[0, 10], [20, 20]]" in out        # base: intatto
    assert "      density: [[0, 1], [20, 9]]" in out      # eredita: intatto


def test_stream_duration_written_inside_its_base():
    text = SCOPE_TEXT.replace("    duration: 100\n    base:\n",
                              "    base:\n      duration: 100\n")
    out = _rescale(text, {("streams", "proprio", "base", "duration"): (50.0, 100.0)})
    assert "      density: [[0, 5], [200, 40]]" in out
    assert "  density: [[0, 10], [20, 20]]" in out


def test_action_is_anchored_on_the_changed_key():
    # l'azione compare solo col cursore sulla riga della durata cambiata
    doc = yamlpos.parse(SCOPE_TEXT)
    m = model.build(doc)
    line = SCOPE_TEXT.split("\n").index("    duration: 100")
    on_key = types.Range(start=types.Position(line, 0),
                         end=types.Position(line, 20))
    elsewhere = types.Range(start=types.Position(0, 0), end=types.Position(0, 5))
    pending = {("streams", "proprio", "duration"): (50.0, 100.0)}
    assert actions.duration_actions(doc, m, "file:///t.yml", on_key, pending)
    assert not actions.duration_actions(doc, m, "file:///t.yml", elsewhere, pending)


# --- memoria delle durate lato server ---------------------------------------


class _Store:
    """Il solo stato che ``_track_durations`` tocca (evita di costruire il
    LanguageServer vero, che vorrebbe un event loop)."""

    def __init__(self):
        self.durations = {}
        self.pending_durations = {}


def _tracked(text):
    from glls import server

    store = _Store()
    server.GllsServer._track_durations(store, "u", model.build(yamlpos.parse(text)))
    return store


def test_tracks_document_and_per_stream_durations():
    assert set(_tracked(SCOPE_TEXT).durations["u"]) == {
        ("base", "duration"),
        ("streams", "proprio", "duration"),
    }


def test_tracks_a_stream_duration_written_inside_its_base():
    text = SCOPE_TEXT.replace("    duration: 100\n    base:\n",
                              "    base:\n      duration: 100\n")
    assert ("streams", "proprio", "base", "duration") in _tracked(text).durations["u"]


def test_does_not_track_the_forbidden_top_level_key():
    # ha una diagnostica e due quick fix che la spostano: armarci sopra un
    # refactor incoraggerebbe a lasciarla dov'e'
    assert ("duration",) not in _tracked("duration: 20\n" + SCOPE_TEXT).durations["u"]


def test_a_stream_name_with_a_dot_stays_addressable():
    # la chiave e' un key-path, non una stringa: un nome libero con un punto
    # dentro non va riparsato (ed e' il motivo per cui non e' una stringa)
    text = SCOPE_TEXT.replace("  proprio:\n", "  a.b:\n")
    assert ("streams", "a.b", "duration") in _tracked(text).durations["u"]
