"""Valutatore del nodo-expr, allineato a ``granstudies.expr``.

Replica la grammatica whitelist del nodo-expr di granulation-studies (numeri,
nomi, ``+ - * / **``, meno unario, parentesi; Env⊙scalare sulle y, Env⊙Env
errore) per dare all'editor la **stessa** diagnostica del runtime, a tempo di
digitazione. Modulo puro, solo stdlib.
"""
from __future__ import annotations

import ast
import operator
from typing import Any, Dict, Mapping, Tuple

_MAX_POW_EXP = 128
_MAX_POW_BASE = 1e9


def _safe_pow(base: Any, exp: Any) -> Any:
    if abs(exp) > _MAX_POW_EXP or abs(base) > _MAX_POW_BASE:
        raise ValueError(
            f"expr: potenza fuori scala ({base!r} ** {exp!r}) — esponente "
            f"massimo {_MAX_POW_EXP}, base massima {_MAX_POW_BASE:g}."
        )
    return operator.pow(base, exp)


_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: _safe_pow,
}

_NODE_KEYS = frozenset({"expr", "let"})


def is_expr_node(spec: Any) -> bool:
    return isinstance(spec, dict) and "expr" in spec


def parse_expr_node(spec: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    extra = set(spec) - _NODE_KEYS
    if extra:
        raise ValueError(
            f"nodo-expr: chiavi non ammesse {sorted(extra)} (solo expr/let)."
        )
    text = spec["expr"]
    if not isinstance(text, str):
        raise ValueError(
            f"nodo-expr: 'expr' deve essere una stringa (ricevuto {text!r}) — "
            "l'espressione va sempre tra virgolette."
        )
    let = spec.get("let") or {}
    if not isinstance(let, dict):
        raise ValueError(f"nodo-expr: 'let' deve essere un dict (ricevuto {let!r}).")
    for name, value in let.items():
        _checked(name, value)
    return text, dict(let)


def eval_expr(text: str, scope: Mapping[str, Any]) -> Any:
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"expr: sintassi non valida in {text!r}: {exc.msg}.") from exc
    try:
        return _eval(tree.body, scope)
    except ZeroDivisionError:
        raise ValueError(f"expr: divisione per zero in {text!r}.") from None


def _is_scalar(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_pairs(v: Any) -> bool:
    return (
        isinstance(v, (list, tuple))
        and len(v) > 0
        and all(
            isinstance(p, (list, tuple)) and len(p) == 2
            and _is_scalar(p[0]) and _is_scalar(p[1])
            for p in v
        )
    )


def _checked(name: str, v: Any) -> Any:
    if _is_scalar(v) or _is_pairs(v):
        return v
    if (
        isinstance(v, (list, tuple)) and len(v) == 2
        and _is_scalar(v[0]) and _is_scalar(v[1])
    ):
        return v
    if isinstance(v, dict) and _is_pairs(v.get("points")):
        return v
    raise ValueError(
        f"expr: '{name}' ha una forma non riconosciuta — in scope solo scalari "
        "o forme statiche di Env (niente nodi-generatore)."
    )


def _map_y(env: Any, fn) -> Any:
    if isinstance(env, dict):
        return {**env, "points": [[t, fn(y)] for t, y in env["points"]]}
    if _is_pairs(env):
        return [[t, fn(y)] for t, y in env]
    a, b = env
    return [fn(a), fn(b)]


def _eval(node: ast.AST, scope: Mapping[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        if not _is_scalar(node.value):
            raise ValueError(f"expr: costante non numerica {node.value!r}.")
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in scope:
            names = ", ".join(sorted(scope)) or "nessuno"
            raise ValueError(f"expr: nome ignoto '{node.id}' (disponibili: {names}).")
        return _checked(node.id, scope[node.id])
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _eval(node.operand, scope)
        if isinstance(node.op, ast.UAdd):
            return v
        return _map_y(v, operator.neg) if not _is_scalar(v) else -v
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        op = _BINOPS[type(node.op)]
        left = _eval(node.left, scope)
        right = _eval(node.right, scope)
        left_env, right_env = not _is_scalar(left), not _is_scalar(right)
        if left_env and right_env:
            raise ValueError(
                "expr: operazione tra due Env non supportata (solo Env con scalare)."
            )
        if left_env:
            return _map_y(left, lambda y: op(y, right))
        if right_env:
            return _map_y(right, lambda y: op(left, y))
        return op(left, right)
    raise ValueError(
        f"expr: costrutto non ammesso {ast.unparse(node)!r} "
        "(solo numeri, nomi, + - * / **, parentesi)."
    )
