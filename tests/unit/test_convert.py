"""Unit test delle conversioni numeriche (il ricalcolo dei rand di X)."""
import pytest

from glls.convert import (
    ConversionError,
    convert_band,
    env_eval,
    env_points,
    fmt_num,
    yaml_flow,
)


def test_fmt_num():
    assert fmt_num(20) == "20"
    assert fmt_num(20.0) == "20"
    assert fmt_num(0.05) == "0.05"
    assert fmt_num(1 / 3) == "0.333333333"


def test_yaml_flow():
    assert yaml_flow([[0, 20], [1, 4]]) == "[[0, 20], [1, 4]]"
    assert yaml_flow(0.5) == "0.5"


def test_env_points_forms():
    assert env_points(5) == [(0.0, 5.0), (1.0, 5.0)]
    assert env_points([2, 8]) == [(0.0, 2.0), (1.0, 8.0)]
    assert env_points([[0, 1], [0.5, 3], [1, 2]]) == [(0.0, 1.0), (0.5, 3.0), (1.0, 2.0)]
    assert env_points({"type": "linear", "points": [[0, 1], [1, 2]]}) == [(0.0, 1.0), (1.0, 2.0)]
    # forme non statiche
    assert env_points({"n": 6, "base": 2, "range": 6}) is None
    assert env_points({"expr": "env * 2", "let": {}}) is None
    assert env_points({"type": "step", "points": [[0, 1], [1, 2]]}) is None
    assert env_points({"points": [[0, 1], [1, 2]], "curve": 2}) is None


def test_env_eval_hold():
    pts = [(0.0, 10.0), (1.0, 20.0)]
    assert env_eval(pts, -1) == 10.0
    assert env_eval(pts, 0.5) == 15.0
    assert env_eval(pts, 2) == 20.0


def test_hz_to_bpm_linear_scale():
    base, rng = convert_band(2, 4, "hz", "bpm")
    assert base == 120
    assert rng == 240


def test_bpm_to_hz_envelope_shape_preserved():
    base, rng = convert_band([[0, 60], [1, 120]], 30, "bpm", "hz")
    assert base == [[0, 1], [1, 2]]
    assert rng == 0.5


def test_hz_to_s_scalar_inverts_endpoints():
    # banda [4, 6] hz -> periodi [1/6, 1/4] s: base=1/6, range=1/4-1/6
    base, rng = convert_band(4, 2, "hz", "s")
    assert base == pytest.approx(1 / 6, abs=1e-9)
    assert rng == pytest.approx(1 / 4 - 1 / 6, abs=1e-9)


def test_s_to_hz_roundtrip():
    base, rng = convert_band(4, 2, "hz", "s")
    back_b, back_r = convert_band(base, rng, "s", "hz")
    assert back_b == pytest.approx(4, abs=1e-6)
    assert back_r == pytest.approx(2, abs=1e-6)


def test_hz_to_s_deterministic_walk_no_range():
    # range assente: camminata deterministica, resta senza range
    base, rng = convert_band(20, None, "hz", "s")
    assert base == pytest.approx(0.05)
    assert rng is None


def test_s_to_bpm():
    base, rng = convert_band(2, None, "s", "bpm")  # periodo 2s = 30 bpm
    assert base == 30
    assert rng is None


def test_envelope_band_to_period():
    # base [[0, 20], [1, 4]] hz, range 5 -> banda hz [20,25] .. [4,9]
    base, rng = convert_band([[0, 20], [1, 4]], 5, "hz", "s")
    assert base == [[0, pytest.approx(1 / 25)], [1, pytest.approx(1 / 9)]]
    # range scalare: la forma piu' compatta coerente e' la rampa [a, b]
    assert rng == [pytest.approx(1 / 20 - 1 / 25), pytest.approx(1 / 4 - 1 / 9)]


def test_union_of_breakpoint_times():
    base, rng = convert_band([[0, 10], [1, 10]], [[0, 0], [0.5, 10], [1, 0]],
                             "hz", "s")
    # base costante 10, range 0 -> 10 -> 0: tre tempi in uscita
    assert isinstance(base, list) and len(base) == 3
    assert base[0] == [0, 0.1]
    assert base[1][0] == 0.5


def test_nonpositive_band_rejected():
    with pytest.raises(ConversionError):
        convert_band([[0, 1], [1, 0]], None, "hz", "s")


def test_generator_node_rejected():
    with pytest.raises(ConversionError):
        convert_band({"n": 8, "base": 2, "range": 4}, 0.5, "hz", "s")


def test_same_unit_noop():
    assert convert_band(5, 1, "hz", "hz") == (5, 1)
