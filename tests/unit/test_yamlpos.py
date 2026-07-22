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
    path, dup_span, first_span = doc.duplicates[0]
    assert path == ("base", "volume")
    # la ripetizione e' a riga 2, la prima occorrenza a riga 1 (0-based)
    assert dup_span.start_line == 2
    assert first_span.start_line == 1


def test_duplicate_keys_reference_first_occurrence():
    # tre occorrenze: entrambe le ripetizioni rimandano sempre alla prima
    doc = yamlpos.parse("a: 1\na: 2\na: 3\n")
    assert len(doc.duplicates) == 2
    assert all(first.start_line == 0 for _, _, first in doc.duplicates)
    assert [dup.start_line for _, dup, _ in doc.duplicates] == [1, 2]


def test_path_at():
    text = "stack:\n  density:\n    base: 20\n"
    doc = yamlpos.parse(text)
    path, where = doc.path_at(2, 5)   # sulla chiave "base"
    assert path == ("stack", "density", "base")
    assert where == "key"
    path, where = doc.path_at(2, 10)  # sul valore 20
    assert path == ("stack", "density", "base")
    assert where == "value"
