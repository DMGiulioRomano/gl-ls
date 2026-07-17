"""Completion, hover e semantic tokens per le chiavi puntate di spread.over."""
from glls import completion, hover, model, semtokens, yamlpos

BASE = """study_id: t
duration: 20
base:
  onset: 0
  duration: 6
  sample: corpus.wav
axes:
  density:
    path: density
    baseline: 20
    values: [10, 30]
"""


def _doc_model(text):
    doc = yamlpos.parse(text)
    return doc, model.build(doc)


def _decode(data):
    """Delta-encoding LSP -> lista di (line, col, length, type)."""
    out = []
    line = col = 0
    for i in range(0, len(data), 5):
        d_line, d_col, length, tok, _mod = data[i:i + 5]
        line += d_line
        col = col + d_col if d_line == 0 else d_col
        out.append((line, col, length, tok))
    return out


# ---------------------------------------------------------------------------
# semantic tokens


def _spread_text(over_line):
    return BASE + (
        "streams:\n"
        "  fan:\n"
        "    spread:\n"
        "      n: 3\n"
        "      over:\n"
        f"{over_line}\n"
    )


def test_semtokens_split_dotted_key_into_path_and_marker():
    text = _spread_text("        base.onset.values: [0, 1, 2]")
    doc, m = _doc_model(text)
    toks = _decode(semtokens.tokens(doc, m))
    lines = text.splitlines()
    row = next(i for i, l in enumerate(lines) if "base.onset.values" in l)
    key_col = lines[row].index("base.onset.values")
    macro = semtokens._T["macro"]
    prop = semtokens._T["property"]
    # path 'base.onset' come property, 'values' come macro
    assert (row, key_col, len("base.onset"), prop) in toks
    assert (row, key_col + len("base.onset") + 1, len("values"), macro) in toks


def test_semtokens_nested_key_not_split():
    text = _spread_text("        base.onset:\n          values: [0, 1, 2]")
    doc, m = _doc_model(text)
    toks = _decode(semtokens.tokens(doc, m))
    lines = text.splitlines()
    row = next(i for i, l in enumerate(lines) if l.strip() == "base.onset:")
    key_col = lines[row].index("base.onset")
    prop = semtokens._T["property"]
    # la chiave annidata resta un unico token property (path intero)
    assert (row, key_col, len("base.onset"), prop) in toks


def test_semtokens_dict_valued_dotted_key_not_split():
    # valore-dict: niente split, la chiave resta property intera
    text = _spread_text("        base.onset.ramp:\n          start: 0")
    doc, m = _doc_model(text)
    toks = _decode(semtokens.tokens(doc, m))
    lines = text.splitlines()
    row = next(i for i, l in enumerate(lines) if "base.onset.ramp" in l)
    key_col = lines[row].index("base.onset.ramp")
    prop = semtokens._T["property"]
    assert (row, key_col, len("base.onset.ramp"), prop) in toks


# ---------------------------------------------------------------------------
# hover


def _hover_on(text, needle, offset=0):
    doc, m = _doc_model(text)
    lines = text.splitlines()
    row = next(i for i, l in enumerate(lines) if needle in l)
    col = lines[row].index(needle) + offset
    return hover.hover(doc, m, row, col)


def test_hover_dotted_over_key_shows_marker_doc():
    text = _spread_text("        base.onset.values: [0, 1, 2]")
    h = _hover_on(text, "base.onset.values")
    assert h is not None
    v = h.contents.value
    assert "base.onset" in v
    assert "values" in v
    # doc del marcatore values (dallo schema spread_strategy)
    assert "lista" in v.lower()


def test_hover_dotted_expr_marker():
    text = _spread_text('        base.onset.expr: "i * 2"')
    h = _hover_on(text, "base.onset.expr")
    assert h is not None
    assert "expr" in h.contents.value


def test_hover_nested_over_key_still_works():
    text = _spread_text("        base.onset:\n          values: [0, 1, 2]")
    h = _hover_on(text, "base.onset:")
    assert h is not None
    assert "base.onset" in h.contents.value


# ---------------------------------------------------------------------------
# completion


def test_completion_over_offers_dotted_terminals():
    text = _spread_text("        ")
    doc, m = _doc_model(text)
    lines = text.splitlines()
    row = len(lines) - 1
    items = completion.complete(doc, m, row, 8)
    labels = {i.label for i in items}
    assert any(l.endswith(".values") for l in labels)
    assert any(l.endswith(".expr") for l in labels)
    assert "base.onset.values" in labels
