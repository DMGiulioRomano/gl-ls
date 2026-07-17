"""Unit test di exprlang: parita' con la grammatica di granstudies.expr.

La diagnostica expr dell'editor deve coincidere con il runtime: operatori
``// %``, costanti ``pi``/``e`` ombreggiabili, funzioni primitive elementwise
sugli Env, ``mix`` come unica porta Env con Env, risultati arrotondati.
"""
import math

import pytest

from glls.exprlang import eval_expr, parse_expr_node


ENV = [[0, 0], [1, 10]]


def test_floordiv_and_mod():
    assert eval_expr("7 // 2", {}) == 3
    assert eval_expr("7 % 3", {}) == 1


def test_constants_pi_e():
    assert eval_expr("pi", {}) == round(math.pi, 9)
    assert eval_expr("e", {}) == round(math.e, 9)


def test_scope_shadows_constants():
    assert eval_expr("pi", {"pi": 3}) == 3


def test_unknown_name_lists_constants():
    with pytest.raises(ValueError, match="nome ignoto"):
        eval_expr("foo", {})
    try:
        eval_expr("foo", {})
    except ValueError as e:
        assert "pi" in str(e)


def test_functions_on_scalars():
    assert eval_expr("floor(3.7)", {}) == 3
    assert eval_expr("ceil(3.2)", {}) == 4
    assert eval_expr("sqrt(16)", {}) == 4
    assert eval_expr("abs(-2)", {}) == 2
    assert eval_expr("min(3, 1, 2)", {}) == 1
    assert eval_expr("max(3, 1)", {}) == 3
    assert eval_expr("log(100, 10)", {}) == 2


def test_function_on_env_is_elementwise():
    out = eval_expr("min(env, 5)", {"env": ENV})
    assert out == [[0, 0], [1, 5]]


def test_two_env_in_call_error():
    with pytest.raises(ValueError, match="due Env"):
        eval_expr("min(a, b)", {"a": ENV, "b": ENV})


def test_unknown_function():
    with pytest.raises(ValueError, match="funzione ignota"):
        eval_expr("clamp(1, 2)", {})


def test_arity_check():
    with pytest.raises(ValueError, match="argomenti"):
        eval_expr("min(1)", {})
    with pytest.raises(ValueError, match="argomenti"):
        eval_expr("floor(1, 2)", {})


def test_keyword_args_rejected():
    with pytest.raises(ValueError, match="keyword"):
        eval_expr("log(8, base=2)", {})


def test_function_domain_error():
    with pytest.raises(ValueError, match="fuori dominio"):
        eval_expr("sqrt(-1)", {})


def test_mix_scalars():
    assert eval_expr("mix(0, 10, 0.5)", {}) == 5


def test_mix_env_with_scalar_weight():
    out = eval_expr("mix(a, 10, 0.5)", {"a": ENV})
    assert out == [[0, 5], [1, 10]]


def test_mix_step_with_linear_error():
    step = {"type": "step", "points": [[0, 1], [1, 2]]}
    with pytest.raises(ValueError, match="step"):
        eval_expr("mix(a, b, 0.5)", {"a": step, "b": ENV})


def test_mix_arity():
    with pytest.raises(ValueError, match="argomenti"):
        eval_expr("mix(1, 2)", {})


def test_complex_result_rejected():
    with pytest.raises(ValueError, match="complesso"):
        eval_expr("(-1) ** 0.5", {})


def test_results_rounded_to_9_decimals():
    assert eval_expr("1 / 3", {}) == round(1 / 3, 9)


def test_zero_division_message_covers_mod():
    with pytest.raises(ValueError, match="divisione o modulo per zero"):
        eval_expr("1 % 0", {})


def test_env_scalar_still_elementwise():
    assert eval_expr("env * 2", {"env": ENV}) == [[0, 0], [1, 20]]


def test_env_env_still_error():
    with pytest.raises(ValueError, match="due Env"):
        eval_expr("a + b", {"a": ENV, "b": ENV})


def test_parse_expr_node_unchanged():
    text, let = parse_expr_node({"expr": "v * 2", "let": {"v": 3}})
    assert text == "v * 2"
    assert let == {"v": 3}
    with pytest.raises(ValueError, match="chiavi non ammesse"):
        parse_expr_node({"expr": "1", "n": 4})


def test_pow_guard_still_active():
    # guardia server-side (assente nel runtime): potenze fuori scala rifiutate
    with pytest.raises(ValueError, match="potenza fuori scala"):
        eval_expr("10 ** 1000", {})
