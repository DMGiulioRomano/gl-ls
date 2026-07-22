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


# --- versions: completion e hover della chiave riservata chunk (#17) -----

def test_versions_key_completion_offers_reserved():
    text = "versions:\n  d: {values: [1, 2]}\n  \n"
    labels = {i.label for i in _items(text, 2, 2)}
    assert {"onset", "duration", "chunk"} <= labels


def test_versions_chunk_hover_documented():
    from glls import hover
    text = "versions:\n  chunk: 10\n"
    doc = yamlpos.parse(text)
    m = model.build(doc)
    h = hover.hover(doc, m, 1, 3)
    assert h is not None and "chunk" in h.contents.value
    assert "diagonale" in h.contents.value


# --- gain_compensation: completion e hover (issue #19) -------------------

def test_root_completion_offers_gain_compensation_and_percorso():
    labels = {i.label for i in _items("study_id: t\n\n", 1, 0)}
    assert "gain_compensation" in labels
    assert "percorso" in labels


def test_gain_compensation_key_completion_offers_reserved():
    text = "gain_compensation:\n  \n"
    labels = {i.label for i in _items(text, 1, 2)}
    assert labels == {"alpha", "max_shift"}


def test_gain_compensation_block_hover_documented():
    from glls import hover
    text = "gain_compensation:\n  alpha: 0.5\n"
    doc = yamlpos.parse(text)
    m = model.build(doc)
    h = hover.hover(doc, m, 0, 3)
    assert h is not None and "gain_compensation" in h.contents.value
    assert "multi-stream" in h.contents.value


def test_gain_compensation_alpha_hover_documented():
    from glls import hover
    text = "gain_compensation:\n  alpha: 0.5\n"
    doc = yamlpos.parse(text)
    m = model.build(doc)
    h = hover.hover(doc, m, 1, 3)
    assert h is not None and "alpha" in h.contents.value
