"""Unit test dell'espansione delle chiavi puntate di ``spread.over``.

Sintassi introdotta in granulation-studies (``_expand_over_dotted``): una
chiave di ``over`` che termina con un marcatore di strategy e ha valore
non-dict viene splittata in ``{path: {marcatore: valore}}``; piu' frammenti
sullo stesso path si fondono in un'unica strategy.
"""
from glls import model, yamlpos
from glls.model import OVER_MARKERS, expand_over, split_over_key


# ---------------------------------------------------------------------------
# split_over_key


def test_split_marker_with_non_dict_value():
    assert split_over_key("base.pointer.start.values", [0.1, 0.25, 0.4]) == (
        "base.pointer.start", "values",
    )


def test_no_split_when_value_is_dict():
    # un valore-dict e' una strategy completa: la chiave resta un path intero,
    # anche se termina con un nome-marcatore (banda-base di un asse)
    assert split_over_key("axes.density.base", {"expr": "x"}) is None


def test_no_split_without_marker_suffix():
    assert split_over_key("base.pointer.start", 5) is None


def test_no_split_without_dot():
    assert split_over_key("values", [1, 2]) is None


def test_no_split_for_non_string_key():
    assert split_over_key(5, 1) is None


def test_all_markers_recognized_as_suffix():
    expected = {"values", "ramp", "base", "range", "seed", "distribution",
                "drift", "expr", "let", "n"}
    assert OVER_MARKERS == expected
    for mk in expected:
        assert split_over_key(f"base.onset.{mk}", 1) == ("base.onset", mk)


# ---------------------------------------------------------------------------
# expand_over


def test_nested_form_passes_through():
    out = expand_over({"base.onset": {"values": [0, 1]}})
    assert set(out) == {"base.onset"}
    e = out["base.onset"]
    assert e.strategy == {"values": [0, 1]}
    assert e.doc_keys == ["base.onset"]
    assert e.marker_keys == {}
    assert e.whole_key == "base.onset"


def test_dotted_form_splits():
    out = expand_over({"base.pointer.start.values": [0.1, 0.25, 0.4]})
    assert set(out) == {"base.pointer.start"}
    e = out["base.pointer.start"]
    assert e.strategy == {"values": [0.1, 0.25, 0.4]}
    assert e.marker_keys == {"values": "base.pointer.start.values"}
    assert e.whole_key is None


def test_band_on_three_lines_merges():
    out = expand_over({
        "base.onset.base": 2,
        "base.onset.range": 3,
        "base.onset.seed": 42,
    })
    assert set(out) == {"base.onset"}
    e = out["base.onset"]
    assert e.strategy == {"base": 2, "range": 3, "seed": 42}
    assert e.doc_keys == ["base.onset.base", "base.onset.range", "base.onset.seed"]


def test_mixed_dotted_and_nested_merge():
    out = expand_over({
        "base.onset.expr": "v * i",
        "base.onset": {"let": {"v": 2}},
    })
    e = out["base.onset"]
    assert e.strategy == {"expr": "v * i", "let": {"v": 2}}
    assert e.marker_keys == {"expr": "base.onset.expr"}
    assert e.whole_key == "base.onset"


def test_non_dict_without_marker_stays_raw():
    # lista nuda su un path senza marcatore: non e' una strategy (errore a valle)
    e = expand_over({"base.onset": [0, 1, 2]})["base.onset"]
    assert e.strategy == [0, 1, 2]


def test_conflicting_generator_markers_merge_into_one_strategy():
    # due marcatori-generatore sullo stesso path si fondono: la strategy a due
    # marcatori e' errore, diagnosticato a valle
    e = expand_over({"base.onset.values": [1, 2], "base.onset.expr": "i"})["base.onset"]
    assert e.strategy == {"values": [1, 2], "expr": "i"}
    assert set(e.marker_keys) == {"values", "expr"}


def test_paths_stay_distinct():
    out = expand_over({
        "base.onset.values": [1, 2],
        "base.volume.values": [-6, -3],
    })
    assert set(out) == {"base.onset", "base.volume"}


# ---------------------------------------------------------------------------
# build: conteggio spread_n dalle strategy espanse


def _model_of(text):
    return model.build(yamlpos.parse(text))


def test_build_spread_n_from_dotted_values():
    m = _model_of(
        "streams:\n"
        "  fan:\n"
        "    spread:\n"
        "      over:\n"
        "        base.onset.values: [0, 1, 2]\n"
    )
    si = m.streams["fan"]
    assert si.is_spread
    assert si.spread_n == 3


def test_build_spread_n_from_merged_dotted_band():
    m = _model_of(
        "streams:\n"
        "  fan:\n"
        "    spread:\n"
        "      over:\n"
        "        base.onset.base: 2\n"
        "        base.onset.range: 3\n"
        "        base.onset.n: 5\n"
    )
    assert m.streams["fan"].spread_n == 5


def test_build_spread_n_none_for_bare_list():
    # la lista nuda non e' mai stata una strategy valida nel runtime:
    # il conteggio non e' posseduto
    m = _model_of(
        "streams:\n"
        "  fan:\n"
        "    spread:\n"
        "      over:\n"
        "        base.onset: [0, 1, 2]\n"
    )
    assert m.streams["fan"].spread_n is None


def test_build_spread_n_from_expr_node():
    # percorso-v1: n come nodo-expr, valutato col let statico
    m = _model_of(
        "streams:\n"
        "  fan:\n"
        "    spread:\n"
        '      n: {expr: "k * 2", let: {k: 3}}\n'
        "      over:\n"
        "        base.onset:\n"
        "          ramp: {start: 0, step: 2}\n"
    )
    assert m.streams["fan"].spread_n == 6


def test_build_spread_n_expr_unresolvable_falls_back_to_over():
    m = _model_of(
        "streams:\n"
        "  fan:\n"
        "    spread:\n"
        '      n: {expr: "voci"}\n'
        "      over:\n"
        "        base.onset.values: [0, 1]\n"
    )
    assert m.streams["fan"].spread_n == 2


def test_build_spread_n_ignores_bool():
    m = _model_of(
        "streams:\n"
        "  fan:\n"
        "    spread:\n"
        "      n: true\n"
        "      over:\n"
        "        base.onset.values: [0]\n"
    )
    assert m.streams["fan"].spread_n == 1
