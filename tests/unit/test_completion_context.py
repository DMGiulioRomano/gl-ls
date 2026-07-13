"""Inferenza del contesto dal testo (documenti anche sintatticamente rotti)."""
from glls.completion import infer_context

TEXT = """study_id: t
base:
  grain:
    envelope: hanning
axes:
  density:
    path: density
stack:
  density:
    base: 5
"""


def test_key_at_root():
    path, mode, key, _ = infer_context("stu", 0, 3)
    assert path == () and mode == "key"


def test_key_inside_axis():
    lines = TEXT.splitlines()
    text = "\n".join(lines[:7] + ["    val"])
    path, mode, key, _ = infer_context(text, 7, 7)
    assert path == ("axes", "density")
    assert mode == "key"


def test_value_position():
    path, mode, key, _ = infer_context(TEXT, 3, 14)
    assert path == ("base", "grain")
    assert mode == "value"
    assert key == "envelope"


def test_nested_grain_key():
    lines = TEXT.splitlines()
    text = "\n".join(lines[:4] + ["    dur"])
    path, mode, _, _ = infer_context(text, 4, 7)
    assert path == ("base", "grain")


def test_stack_walk_key():
    text = TEXT + "    ran"
    path, mode, _, _ = infer_context(text, 10, 7)
    assert path == ("stack", "density")
    assert mode == "key"


def test_empty_line_key_context():
    text = TEXT + "  "
    path, mode, _, _ = infer_context(text, 10, 2)
    assert path == ("stack",)
    assert mode == "key"
