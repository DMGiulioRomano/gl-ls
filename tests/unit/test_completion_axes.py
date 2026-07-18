"""Completion delle chiavi d'asse: i path engine come chiavi dirette (#12)."""
from glls import completion, model, yamlpos


def _items(text, line, col):
    doc = yamlpos.parse(text)
    m = model.build(doc)
    return completion.complete(doc, m, line, col)


def test_axes_key_completion_offers_engine_paths():
    labels = {i.label for i in _items("axes:\n  \n", 1, 2)}
    assert "grain.duration" in labels
    assert "density" in labels
    assert "nuovo_asse" in labels


def test_axes_key_completion_excludes_present():
    text = "axes:\n  density:\n    values: [10]\n  \n"
    labels = {i.label for i in _items(text, 3, 2)}
    assert "density" not in labels
    assert "grain.duration" in labels
