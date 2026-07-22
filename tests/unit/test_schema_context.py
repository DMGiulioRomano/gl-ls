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


def test_dotted_axis_boundary_from_engine_registry():
    # 'grain.duration' e' un path engine noto: il nome d'asse resta intero
    assert schema.context_for_path(
        ("streams", "s", "axes.grain.duration.ramp")) == "ramp"
    assert schema.context_for_path(
        ("streams", "s", "axes.grain.duration.ramp", "step")) == "env"


def test_dotted_axis_boundary_from_declared_axes():
    # un asse dichiarato (anche non-engine) ha precedenza sul registro
    assert schema.context_for_path(
        ("streams", "s", "axes.mio.asse.ramp"),
        axis_names=frozenset({"mio.asse"})) == "ramp"


def test_dotted_child_of_axes_uses_boundary():
    # figlio diretto puntato di axes: negli override: asse + resto annidato
    assert schema.context_for_path(
        ("streams", "s", "axes", "grain.duration.ramp")) == "ramp"


# --- versions: contesto e chiavi riservate (issue #17) -------------------

def test_versions_block_context():
    assert schema.context_for_path(("versions",)) == "versions"


def test_versions_reserved_keys_are_scalars():
    assert schema.context_for_path(("versions", "chunk")) == "value"
    assert schema.context_for_path(("versions", "onset")) == "value"
    assert schema.context_for_path(("versions", "duration")) == "value"


def test_versions_variable_is_generator_env():
    # una chiave non riservata e' una variabile-generatore Y (contesto env)
    assert schema.context_for_path(("versions", "d")) == "env"
    assert schema.context_for_path(("versions", "d", "ramp")) == "ramp"


def test_versions_is_open_context():
    # nomi di variabile liberi: non deve essere un contesto chiuso
    assert "versions" not in schema.CLOSED_CONTEXTS


def test_versions_reserved_keys_available():
    names = [k.name for k in schema.keys_for("versions")]
    assert names == ["onset", "duration", "chunk"]


# --- gain_compensation: contesto chiuso (issue #19) ----------------------

def test_gain_compensation_block_context():
    assert schema.context_for_path(("gain_compensation",)) == "gain_compensation"


def test_gain_compensation_values_are_scalars():
    assert schema.context_for_path(("gain_compensation", "alpha")) == "value"
    assert schema.context_for_path(("gain_compensation", "max_shift")) == "value"


def test_gain_compensation_is_closed_context():
    # contesto chiuso: un refuso e' un unknown-key
    assert "gain_compensation" in schema.CLOSED_CONTEXTS


def test_gain_compensation_keys_available():
    names = [k.name for k in schema.keys_for("gain_compensation")]
    assert names == ["alpha", "max_shift"]


def test_gain_compensation_is_root_key():
    root_names = {k.name for k in schema.keys_for("root")}
    assert "gain_compensation" in root_names


# --- percorso: blocco top-level riconosciuto, interno aperto (issue #19) --

def test_percorso_block_context():
    assert schema.context_for_path(("percorso",)) == "percorso"
    # anche i figli restano nel contesto aperto (schema interno non modellato)
    assert schema.context_for_path(("percorso", "qualcosa")) == "percorso"


def test_percorso_is_open_context():
    assert "percorso" not in schema.CLOSED_CONTEXTS


def test_percorso_is_root_key():
    root_names = {k.name for k in schema.keys_for("root")}
    assert "percorso" in root_names
