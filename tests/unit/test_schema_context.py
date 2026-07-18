"""``context_for_path`` sui path con segmenti puntati degli override (issue #9).

La notazione a chiave puntata degli override di stream (granstudies
``study_spec._expand_dotted_keys``) equivale alla forma annidata: il contesto
di un path che contiene segmenti puntati deve essere quello della forma
espansa. Il sottoalbero ``spread`` resta fuori: viene consumato prima
dell'espansione runtime e le chiavi di ``over`` sono path-nome interi.
"""
from glls import schema


def test_stream_override_top_level():
    assert schema.context_for_path(("streams", "s")) == "stream_override"


def test_dotted_segment_resolves_to_nested_context():
    assert schema.context_for_path(("streams", "s", "axes.density.ramp")) == "ramp"
    assert schema.context_for_path(("streams", "s", "base.grain")) == "grain"
    assert schema.context_for_path(("streams", "s", "base.pointer")) == "pointer"


def test_dotted_segment_children_recurse():
    # dentro ramp.step vive un Env: contesto env come nella forma annidata
    assert schema.context_for_path(("streams", "s", "axes.density.ramp", "step")) == "env"


def test_dotted_spread_prefix_follows_spread_branch():
    # ``spread.n`` puntata: stesso contesto della forma annidata spread: {n: ...}
    assert schema.context_for_path(("streams", "s", "spread.n")) == "value"


def test_over_dotted_keys_are_not_expanded():
    # le chiavi puntate di ``spread.over`` sono nomi-path, non forme annidate
    assert schema.context_for_path(
        ("streams", "s", "spread", "over", "base.pointer.start")
    ) == "spread_strategy"


def test_dotted_outside_streams_untouched():
    # fuori dagli override il runtime non espande: contesto invariato (root)
    assert schema.context_for_path(("base.grain.duration",)) == "root"
