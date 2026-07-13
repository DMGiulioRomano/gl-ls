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
duration: 40
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
                                    {"duration": (20.0, 40.0)})
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
                                    {"duration": (20.0, 40.0)})
    assert len(acts) == 1
    new_text = _apply(text, acts[0].edit.changes["file:///t.yml"])
    # base: normalized, intatto
    assert "  density: [[0, 10], [1, 20]]" in new_text
    # stream v: absolute, riscalato
    assert "      density: [[0, 10], [12, 20]]" in new_text
