"""Unit test di exprlang: parita' con la grammatica di granstudies.expr.

La diagnostica expr dell'editor deve coincidere con il runtime: operatori
``// %``, costanti ``pi``/``e`` ombreggiabili, funzioni primitive elementwise
sugli Env, ``mix`` come unica porta Env con Env, risultati arrotondati.
"""
import math

import pytest

from glls.exprlang import eval_expr, names_in, parse_expr_node


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


# --- expr annidati dentro let (granulation-studies #28) ------------------------
# parita' con tests/test_expr.py del runtime, commit 983efda


def _nested(levels: int):
    """Un nodo-expr annidato sintatticamente per ``levels`` livelli di let."""
    node = {"expr": "1"}
    for _ in range(levels):
        node = {"expr": "v", "let": {"v": node}}
    return node


def test_parse_expr_node_accepts_nested_expr_in_let():
    node = {"expr": "b * 2", "let": {"a": 2, "b": {"expr": "a + 1"}}}
    text, let = parse_expr_node(node)
    assert text == "b * 2"
    assert let["b"] == {"expr": "a + 1"}


def test_parse_expr_node_validates_nested_node():
    # le regole del nodo-expr valgono anche annidato: chiavi extra sono errore
    node = {"expr": "b", "let": {"b": {"expr": "1", "seed": 3}}}
    with pytest.raises(ValueError, match="seed"):
        parse_expr_node(node)


def test_parse_expr_node_nested_depth_guard():
    assert parse_expr_node(_nested(8))  # al limite: valido
    with pytest.raises(ValueError, match="profondit"):
        parse_expr_node(_nested(9))


def test_nested_expr_resolves_sibling():
    scope = {"a": 2, "b": {"expr": "a + 1"}}
    assert eval_expr("b * 2", scope) == 6


def test_nested_expr_order_independent():
    # 'b' dichiarato prima di 'a': la risoluzione e' per dipendenze, non
    # per ordine di dichiarazione
    scope = {"b": {"expr": "a * 2"}, "a": 3}
    assert eval_expr("b", scope) == 6


def test_nested_expr_chain():
    scope = {"a": 1, "b": {"expr": "a + 1"}, "c": {"expr": "b * 10"}}
    assert eval_expr("c + b", scope) == 22


def test_nested_expr_env_result_enters_arithmetic():
    scope = {"env": [[0, 1], [1, 2]], "s": {"expr": "env * 2"}}
    assert eval_expr("s + 1", scope) == [[0, 3], [1, 5]]


def test_nested_expr_own_let_shadows_outer():
    scope = {"a": 1, "v": {"expr": "a + 1", "let": {"a": 10}}}
    assert eval_expr("v", scope) == 11
    # l'ombreggiatura resta locale: fuori 'a' e' ancora quello esterno
    assert eval_expr("v + a", scope) == 12


def test_nested_expr_own_let_inherits_outer_scope():
    scope = {"k": 5, "v": {"expr": "k + w", "let": {"w": 2}}}
    assert eval_expr("v", scope) == 7


def test_nested_expr_same_name_at_different_levels_is_not_a_cycle():
    # 'x' esterno dipende da 'm', che ombreggia 'x' nel proprio let:
    # binding diversi con lo stesso nome, nessun ciclo
    scope = {
        "x": {
            "expr": "m",
            "let": {"m": {"expr": "x * 2", "let": {"x": {"expr": "5"}}}},
        },
    }
    assert eval_expr("x", scope) == 10


def test_nested_expr_cycle_raises():
    scope = {"a": {"expr": "b"}, "b": {"expr": "a"}}
    with pytest.raises(ValueError, match="ciclo"):
        eval_expr("a", scope)


def test_nested_expr_self_reference_raises():
    with pytest.raises(ValueError, match="ciclo"):
        eval_expr("a", {"a": {"expr": "a * 2"}})


def test_nested_expr_shadowing_cannot_reference_shadowed():
    # un nome ridefinito in un let interno non vede il nome esterno che
    # ombreggia: e' un auto-riferimento, quindi ciclo
    scope = {"a": 1, "v": {"expr": "a", "let": {"a": {"expr": "a + 1"}}}}
    with pytest.raises(ValueError, match="ciclo"):
        eval_expr("v", scope)


def test_nested_expr_dependency_chain_depth_guard():
    # catena piatta di dipendenze: 8 risoluzioni in volo passano, 9 no
    ok = {f"v{k}": {"expr": f"v{k + 1} + 1"} for k in range(8)}
    ok["v8"] = 1
    assert eval_expr("v0", ok) == 9
    deep = {f"v{k}": {"expr": f"v{k + 1} + 1"} for k in range(9)}
    deep["v9"] = 1
    with pytest.raises(ValueError, match="profondit"):
        eval_expr("v0", deep)


def test_nested_expr_error_names_the_variable():
    with pytest.raises(ValueError) as exc:
        eval_expr("v", {"v": {"expr": "boh"}})
    assert "let.v" in str(exc.value)
    assert "boh" in str(exc.value)


def test_nested_expr_two_env_results_still_rejected():
    scope = {
        "e1": {"expr": "env * 2"},
        "e2": {"expr": "env + 1"},
        "env": [[0, 1], [1, 2]],
    }
    with pytest.raises(ValueError, match="Env"):
        eval_expr("e1 * e2", scope)


def test_nested_expr_feeds_mix():
    scope = {
        "a": {"expr": "env"},
        "env": [[0, 0], [1, 10]],
    }
    assert eval_expr("mix(a, 0, 0.5)", scope) == [[0, 0], [1, 5]]


def test_nested_expr_generator_in_nested_let_raises():
    node = {
        "expr": "v",
        "let": {"v": {"expr": "w", "let": {"w": {"ramp": {"start": 0, "step": 1}}}}},
    }
    with pytest.raises(ValueError, match="statiche"):
        parse_expr_node(node)


def test_nested_expr_result_does_not_alias_scope():
    env = [[0, 1], [1, 2]]
    scope = {"env": env, "v": {"expr": "env"}}
    out = eval_expr("v", scope)
    assert out == env
    out[0][1] = 99
    assert env[0][1] == 1


def test_names_in_collects_knob_references():
    assert names_in("gain - 1") == {"gain"}
    assert names_in("a * b + c") == {"a", "b", "c"}


def test_names_in_excludes_functions_and_constants():
    # funzioni primitive e costanti non sono manopole
    assert names_in("floor(k / 2)") == {"k"}
    assert names_in("min(a, pi)") == {"a"}
    assert names_in("mix(a, b, w)") == {"a", "b", "w"}


def test_names_in_tolerant_on_garbage():
    assert names_in("1 +") == set()
    assert names_in(42) == set()
