from glls import yamlpos


def test_parse_positions_and_data():
    text = "axes:\n  density:\n    path: density\n    values: [5, 10]\n"
    doc = yamlpos.parse(text)
    assert doc.syntax_error is None
    assert doc.get(("axes", "density", "path")) == "density"
    e = doc.entry(("axes", "density", "path"))
    assert e.key_span.start_line == 2
    assert e.key_span.start_col == 4
    v0 = doc.entry(("axes", "density", "values", 0))
    assert v0.scalar_raw == "5"


def test_syntax_error_reported():
    doc = yamlpos.parse("axes:\n  density\n    path: density\n")
    assert doc.syntax_error is not None
    assert doc.data is None


def test_duplicate_keys_detected():
    doc = yamlpos.parse("base:\n  volume: -6\n  volume: -3\n")
    assert len(doc.duplicates) == 1
    assert doc.duplicates[0][0] == ("base", "volume")


def test_path_at():
    text = "stack:\n  density:\n    base: 20\n"
    doc = yamlpos.parse(text)
    path, where = doc.path_at(2, 5)   # sulla chiave "base"
    assert path == ("stack", "density", "base")
    assert where == "key"
    path, where = doc.path_at(2, 10)  # sul valore 20
    assert path == ("stack", "density", "base")
    assert where == "value"
