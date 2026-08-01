"""``let`` e ``axes``/``axis``/``stack`` tengono lo stesso token ovunque."""
from glls import model, semtokens, yamlpos

TEXT = """study_id: t
base:
  onset: 0
  duration: 6
  sample: corpus.wav
let:
  g: 3
axes:
  density:
    path: density
    baseline: 20
    values: [10, 30]
stack:
  density:
    ramp: [0, 1]
streams:
  fan:
    let:
      k: 2
    spread:
      n: 3
      let:
        i: {expr: "k"}
      over:
        base.onset.let: {j: 1}
"""


def _decode(data):
    out, line, col = [], 0, 0
    for i in range(0, len(data), 5):
        d_line, d_col, length, tok, _mod = data[i:i + 5]
        line += d_line
        col = col + d_col if d_line == 0 else d_col
        out.append((line, col, length, tok))
    return out


def _toks():
    doc = yamlpos.parse(TEXT)
    return _decode(semtokens.tokens(doc, model.build(doc))), TEXT.splitlines()


def _tok_at(toks, lines, needle, word):
    row = next(i for i, l in enumerate(lines) if needle in l)
    col = lines[row].index(word)
    return next(t for (r, c, _n, t) in toks if r == row and c == col)


def test_let_same_token_at_every_level():
    toks, lines = _toks()
    mod = semtokens._T["modifier"]
    for needle in ("let:", "    let:", "      let:"):
        assert _tok_at(toks, lines, needle, "let") == mod


def test_axes_and_stack_keep_struct_token():
    toks, lines = _toks()
    struct = semtokens._T["struct"]
    assert _tok_at(toks, lines, "axes:", "axes") == struct
    assert _tok_at(toks, lines, "stack:", "stack") == struct


def test_let_knob_names_are_not_recolored():
    toks, lines = _toks()
    row = next(i for i, l in enumerate(lines) if l.startswith("  g:"))
    assert not [t for (r, _c, _n, t) in toks if r == row]
