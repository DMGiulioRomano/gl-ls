"""Chiavi puntate ``over.<path>`` al primo livello di ``spread:`` (issue #15).

Sintassi introdotta in granulation-studies (``_expand_spread_dotted``,
simmetrica a ``_expand_over_dotted`` un livello sopra): ``over.base.onset.
values: [...]`` scritta al primo livello di ``spread:`` equivale a ``over:
{base.onset.values: [...]}``; frammenti dotted e forma annidata si fondono
nello stesso dict prima della validazione.
"""
from glls import diagnostics, model, schema, yamlpos
from glls.model import expand_over_items, over_items, split_spread_over_key

BASE = """study_id: t
duration: 20
base:
  onset: 0
  duration: 6
  sample: corpus.wav
axes:
  density:
    baseline: 20
    values: [10, 30]
"""


def diags_of(text):
    doc = yamlpos.parse(text)
    m = model.build(doc)
    return diagnostics.collect(doc, m)


def codes(text):
    return {d.code for d in diags_of(text)}


# ---------------------------------------------------------------------------
# split_spread_over_key


def test_split_spread_over_key_dotted():
    assert split_spread_over_key("over.base.onset.values") == "base.onset.values"


def test_split_spread_over_key_literal_over_stays():
    assert split_spread_over_key("over") is None


def test_split_spread_over_key_trailing_dot():
    assert split_spread_over_key("over.") is None


def test_split_spread_over_key_other_prefix():
    assert split_spread_over_key("overlay.x") is None
    assert split_spread_over_key("n") is None


def test_split_spread_over_key_non_string():
    assert split_spread_over_key(5) is None


# ---------------------------------------------------------------------------
# over_items / expand_over_items


def test_over_items_nested_and_dotted_in_document_order():
    spread = {
        "n": 3,
        "over": {"base.onset": {"values": [0, 1, 2]}},
        "over.base.volume.values": [-6, -3, 0],
    }
    items = over_items(spread)
    assert items == [
        ("base.onset", {"values": [0, 1, 2]}, ("over", "base.onset")),
        ("base.volume.values", [-6, -3, 0], ("over.base.volume.values",)),
    ]


def test_over_items_only_dotted():
    spread = {"over.base.onset.values": [1, 2]}
    assert over_items(spread) == [
        ("base.onset.values", [1, 2], ("over.base.onset.values",)),
    ]


def test_expand_from_items_splits_dotted_marker():
    out = expand_over_items(over_items({"over.base.onset.values": [1, 2]}))
    assert set(out) == {"base.onset"}
    e = out["base.onset"]
    assert e.strategy == {"values": [1, 2]}
    assert e.marker_keys == {"values": "over.base.onset.values"}
    assert e.doc_key_paths["over.base.onset.values"] == ("over.base.onset.values",)


def test_expand_from_items_merges_dotted_and_nested():
    out = expand_over_items(over_items({
        "over": {"base.onset": {"let": {"v": 2}}},
        "over.base.onset.expr": "v * i",
    }))
    e = out["base.onset"]
    assert e.strategy == {"let": {"v": 2}, "expr": "v * i"}
    assert e.whole_key == "base.onset"
    assert e.doc_key_paths["base.onset"] == ("over", "base.onset")
    assert e.doc_key_paths["over.base.onset.expr"] == ("over.base.onset.expr",)


def test_expand_over_keeps_legacy_doc_key_paths():
    e = model.expand_over({"base.onset.values": [1, 2]})["base.onset"]
    assert e.doc_key_paths["base.onset.values"] == ("over", "base.onset.values")


# ---------------------------------------------------------------------------
# build: spread_n dalla forma dotted


def test_build_spread_n_from_dotted_over():
    text = BASE + (
        "streams:\n  fan:\n    spread:\n"
        "      over.base.onset.values: [0, 1, 2]\n"
    )
    m = model.build(yamlpos.parse(text))
    assert m.streams["fan"].is_spread
    assert m.streams["fan"].spread_n == 3


# ---------------------------------------------------------------------------
# contesto schema


def test_context_dotted_over_key_children_are_strategy():
    p = ("streams", "s", "spread", "over.base.onset")
    assert schema.context_for_path(p) == "spread_strategy"


def test_context_dotted_over_key_deeper_follows_env():
    p = ("streams", "s", "spread", "over.base.onset", "ramp")
    assert schema.context_for_path(p) == "ramp"


# ---------------------------------------------------------------------------
# diagnostica


def _spread(lines):
    return BASE + "streams:\n  fan:\n    spread:\n" + lines


def test_dotted_over_values_clean():
    text = _spread("      over.base.pointer.start.values: [0.1, 0.25, 0.4]\n")
    assert diags_of(text) == []


def test_dotted_over_no_unknown_key():
    text = _spread("      n: 3\n      over.base.onset.values: [0, 1, 2]\n")
    assert "unknown-key" not in codes(text)


def test_dotted_over_satisfies_over_required():
    text = _spread("      over.base.onset.values: [0, 1, 2]\n")
    assert "spread-no-over" not in codes(text)


def test_dotted_over_owns_count_conflict_with_n():
    text = _spread("      n: 4\n      over.base.onset.values: [0, 1, 2]\n")
    assert "spread-count" in codes(text)


def test_dotted_over_counts_fuse_with_nested():
    text = _spread(
        "      over:\n"
        "        base.onset.values: [0, 1, 2]\n"
        "      over.base.volume.values: [-6, -3]\n"
    )
    assert "spread-count" in codes(text)


def test_dotted_over_bad_path_still_flagged():
    text = _spread("      over.bogus.x.values: [1, 2]\n")
    assert "over-path" in codes(text)


def test_dotted_over_nested_strategy_dict():
    text = _spread(
        "      over.base.onset:\n"
        "        ramp: {start: 0, step: 2}\n"
        "      n: 5\n"
    )
    assert diags_of(text) == []


def test_missing_over_still_flagged():
    text = _spread("      n: 4\n")
    assert "spread-no-over" in codes(text)


# ---------------------------------------------------------------------------
# completion / hover / semantic tokens


from glls import completion, hover, semtokens  # noqa: E402


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


def test_semtokens_spread_dotted_over_key():
    text = _spread("      over.base.onset.values: [0, 1, 2]\n")
    doc, m = _doc_model(text)
    toks = _decode(semtokens.tokens(doc, m))
    lines = text.splitlines()
    row = next(i for i, l in enumerate(lines) if "over.base.onset.values" in l)
    key_col = lines[row].index("over.base.onset.values")
    kw, prop, macro = (semtokens._T[t] for t in ("keyword", "property", "macro"))
    # 'over' keyword, path property, marcatore macro
    assert (row, key_col, len("over"), kw) in toks
    assert (row, key_col + 5, len("base.onset"), prop) in toks
    assert (row, key_col + 5 + len("base.onset") + 1, len("values"), macro) in toks


def test_semtokens_spread_dotted_over_dict_value_not_split():
    text = _spread("      over.base.onset:\n        values: [0, 1, 2]\n")
    doc, m = _doc_model(text)
    toks = _decode(semtokens.tokens(doc, m))
    lines = text.splitlines()
    row = next(i for i, l in enumerate(lines) if "over.base.onset:" in l)
    key_col = lines[row].index("over.base.onset")
    kw, prop = semtokens._T["keyword"], semtokens._T["property"]
    assert (row, key_col, len("over"), kw) in toks
    assert (row, key_col + 5, len("base.onset"), prop) in toks


def test_hover_spread_dotted_over_key():
    text = _spread("      over.base.onset.values: [0, 1, 2]\n")
    doc, m = _doc_model(text)
    lines = text.splitlines()
    row = next(i for i, l in enumerate(lines) if "over.base.onset.values" in l)
    col = lines[row].index("over.base.onset.values")
    h = hover.hover(doc, m, row, col)
    assert h is not None
    v = h.contents.value
    assert "base.onset" in v and "values" in v and "dotted" in v


def test_completion_in_spread_offers_dotted_over():
    text = _spread("      n: 3\n      \n")
    doc, m = _doc_model(text)
    lines = text.splitlines()
    row = next(i for i, l in enumerate(lines) if "n: 3" in l)
    items = completion.complete(doc, m, row + 1, 6)
    labels = {i.label for i in items}
    assert "over" in labels  # la forma annidata resta la principale
    assert any(l.startswith("over.base.") for l in labels)
