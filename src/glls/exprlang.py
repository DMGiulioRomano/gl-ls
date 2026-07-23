"""Valutatore del nodo-expr, allineato a ``granstudies.expr``.

Replica la grammatica whitelist del nodo-expr di granulation-studies per dare
all'editor la **stessa** diagnostica del runtime, a tempo di digitazione:
numeri, nomi, ``+ - * / // % **``, meno unario, parentesi, le costanti
``pi``/``e`` (ombreggiabili dallo scope) e le chiamate alle funzioni
primitive di ``_FUNCTIONS`` (``abs``/``floor``/``ceil``/``sqrt``/``exp``/
``log``/``sin``/``cos``/``tan``/``atan``/``min``/``max``/``mix``). Una
chiamata con un argomento-Env agisce elementwise sulle y; due Env nella
stessa operazione o chiamata sono un errore — tranne ``mix(A, B, w)``,
l'unica porta Env con Env (morphing pesato, campionato sull'unione dei
tempi). Modulo puro, solo stdlib.

I valori di ``let`` sono scalari, forme statiche di Env, oppure altri
nodi-expr (granulation-studies #28): un nodo annidato si risolve *lazy* alla
prima referenza, contro lo scope che lo contiene — i fratelli dello stesso
``let`` piu' i nomi esterni (``i``/``n``, bande-let). L'ordine di
dichiarazione non conta; un ``let`` proprio del nodo annidato apre uno scope
figlio lessicale (i nomi interni ombreggiano gli esterni); i cicli sono un
errore esplicito, con guardia di profondita' ``_MAX_LET_DEPTH`` sia
sull'annidamento sintattico (parse) sia sulla catena di dipendenze (eval).

Unica divergenza voluta dal runtime: la guardia ``_safe_pow`` (potenze fuori
scala rifiutate) protegge il processo del server; il runtime usa la potenza
nuda.
"""
from __future__ import annotations

import ast
import math
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
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: _safe_pow,
}

# Costanti note alle espressioni; un nome uguale nello scope (``let``) le
# ombreggia.
_CONSTANTS = {"pi": math.pi, "e": math.e}

# Funzioni primitive: nome -> (fn, arieta' minima, arieta' massima o None).
_FUNCTIONS = {
    "abs": (abs, 1, 1),
    "floor": (math.floor, 1, 1),
    "ceil": (math.ceil, 1, 1),
    "sqrt": (math.sqrt, 1, 1),
    "exp": (math.exp, 1, 1),
    "log": (math.log, 1, 2),
    "sin": (math.sin, 1, 1),
    "cos": (math.cos, 1, 1),
    "tan": (math.tan, 1, 1),
    "atan": (math.atan, 1, 1),
    "min": (min, 2, None),
    "max": (max, 2, None),
    # ``mix`` ha un ramo dedicato in ``_call`` (accetta Env multipli: e'
    # l'unica porta Env con Env); qui vive per la whitelist e l'arieta'.
    "mix": (None, 3, 3),
}

# Nomi che un'espressione risolve senza scope (funzioni primitive e costanti):
# non sono manopole, quindi vanno esclusi quando si cercano i riferimenti a
# nomi di ``let``.
FUNCTION_NAMES = frozenset(_FUNCTIONS)
CONSTANT_NAMES = frozenset(_CONSTANTS)

_NODE_KEYS = frozenset({"expr", "let"})

# Guardia di profondita' degli expr annidati in ``let`` (granulation-studies
# #28): vale sia per l'annidamento sintattico (let dentro let, al parse) sia
# per la catena di dipendenze in risoluzione (all'eval). Stessa soglia del
# runtime (= MAX_ENV_DEPTH dei generatori annidati).
_MAX_LET_DEPTH = 8


def is_expr_node(spec: Any) -> bool:
    return isinstance(spec, dict) and "expr" in spec


def names_in(text: Any) -> set:
    """I nomi (identificatori) referenziati da ``text``, esclusi funzioni e
    costanti primitive: i candidati a manopole di ``let`` che l'espressione usa.

    Tollerante: una stringa non valida sintatticamente ritorna l'insieme vuoto
    (l'errore lo segnala la valutazione vera e propria)."""
    if not isinstance(text, str):
        return set()
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        return set()
    names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    return names - FUNCTION_NAMES - CONSTANT_NAMES


def parse_expr_node(
    spec: Dict[str, Any], *, _depth: int = 0
) -> Tuple[str, Dict[str, Any]]:
    """``(testo, let)`` del nodo-expr, validati.

    ``let`` e' opzionale; i suoi valori sono scalari, forme statiche di Env,
    oppure altri nodi-expr (validati qui ricorsivamente, risolti all'eval) —
    un nodo-generatore dentro ``let`` resta vietato (eccezione: le bande-let
    della strategy expr dello spread, estratte prima di questo parse).
    """
    if _depth > _MAX_LET_DEPTH:
        raise ValueError(
            f"nodo-expr: profondita' di annidamento in 'let' oltre "
            f"{_MAX_LET_DEPTH} — config degenere (alias YAML ricorsivo?)."
        )
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
        if is_expr_node(value):
            try:
                parse_expr_node(value, _depth=_depth + 1)
            except ValueError as exc:
                raise _let_error(name, exc) from None
        else:
            _checked(name, value)
    return text, dict(let)


def eval_expr(text: str, scope: Mapping[str, Any]) -> Any:
    """Valuta ``text`` nello ``scope``: scalare o Env (elementwise sulle y).

    I valori di scope che sono nodi-expr si risolvono alla prima referenza
    (vedi ``_LetScope``).
    """
    if not isinstance(scope, _LetScope):
        scope = _LetScope(scope)
    return _rebuild(_eval_text(text, scope))


def _eval_text(text: str, scope: "_LetScope") -> Any:
    """Il valore grezzo di ``text`` (senza rebuild: usato anche dai nodi annidati)."""
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"expr: sintassi non valida in {text!r}: {exc.msg}.") from exc
    try:
        return _eval(tree.body, scope)
    except ZeroDivisionError:
        raise ValueError(f"expr: divisione o modulo per zero in {text!r}.") from None


def _let_error(name: str, exc: ValueError) -> ValueError:
    """L'errore di un nodo annidato, col nome della variabile di ``let``."""
    msg = str(exc)
    for prefix in ("expr: ", "nodo-expr: "):
        if msg.startswith(prefix):
            msg = msg[len(prefix):]
            break
    return ValueError(f"expr: let.{name}: {msg}")


class _LetScope:
    """Scope con risoluzione lazy dei nodi-expr legati in ``let``.

    Port di ``granstudies.expr._LetScope``: un valore di scope che e' a sua
    volta un nodo-expr si valuta alla prima referenza, contro lo scope che lo
    contiene (fratelli dello stesso ``let`` piu' la catena esterna, compresi
    i nomi dinamici come ``i``/``n`` e le bande-let). Un ``let`` proprio del
    nodo annidato apre uno scope figlio lessicale. Lo stack di risoluzione,
    condiviso lungo la catena, rileva i cicli — chiave ``(scope, nome)``,
    cosi' l'ombreggiatura tra livelli diversi non produce falsi cicli — e fa
    da guardia di profondita'. I risultati sono memoizzati per binding.
    """

    def __init__(
        self, bindings: Mapping[str, Any], parent: "_LetScope | None" = None
    ):
        self._bindings = bindings
        self._parent = parent
        self._cache: Dict[str, Any] = {}
        self._stack: list = parent._stack if parent is not None else []

    def __contains__(self, name: object) -> bool:
        return name in self._bindings or (
            self._parent is not None and name in self._parent
        )

    def __iter__(self):
        # L'unione dei nomi visibili, per gli elenchi nei messaggi d'errore.
        yield from self._bindings
        if self._parent is not None:
            for name in self._parent:
                if name not in self._bindings:
                    yield name

    def __getitem__(self, name: str) -> Any:
        if name not in self._bindings:
            if self._parent is None:
                raise KeyError(name)
            return self._parent[name]
        if name in self._cache:
            return self._cache[name]
        value = self._bindings[name]
        if is_expr_node(value):
            value = self._resolve(name, value)
        self._cache[name] = value
        return value

    def _resolve(self, name: str, node: Dict[str, Any]) -> Any:
        key = (id(self), name)
        if key in self._stack:
            chain = [n for _, n in self._stack[self._stack.index(key):]]
            chain.append(name)
            raise ValueError(f"expr: ciclo nel let ({' -> '.join(chain)}).")
        if len(self._stack) >= _MAX_LET_DEPTH:
            chain = " -> ".join([n for _, n in self._stack] + [name])
            raise ValueError(
                f"expr: profondita' della catena di let oltre {_MAX_LET_DEPTH} "
                f"({chain}) — config degenere."
            )
        self._stack.append(key)
        try:
            text, let = parse_expr_node(node)
            return _eval_text(text, _LetScope(let, parent=self))
        except ValueError as exc:
            raise _let_error(name, exc) from None
        finally:
            self._stack.pop()


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
        if node.id in scope:
            return _checked(node.id, scope[node.id])
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        names = ", ".join(sorted(set(scope) | set(_CONSTANTS))) or "nessuno"
        raise ValueError(f"expr: nome ignoto '{node.id}' (disponibili: {names}).")
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
    if isinstance(node, ast.Call):
        return _call(node, scope)
    raise ValueError(
        f"expr: costrutto non ammesso {ast.unparse(node)!r} "
        "(solo numeri, nomi, + - * / // % **, funzioni primitive, parentesi)."
    )


def _call(node: ast.Call, scope: Mapping[str, Any]) -> Any:
    """Una chiamata a funzione primitiva, elementwise se un argomento e' Env."""
    if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS:
        got = ast.unparse(node.func)
        names = ", ".join(sorted(_FUNCTIONS))
        raise ValueError(f"expr: funzione ignota '{got}' (disponibili: {names}).")
    name = node.func.id
    if node.keywords:
        raise ValueError(
            f"expr: '{name}' non accetta argomenti keyword (solo posizionali)."
        )
    fn, lo, hi = _FUNCTIONS[name]
    args = [_eval(a, scope) for a in node.args]
    count = len(args)
    if count < lo or (hi is not None and count > hi):
        span = str(lo) if hi == lo else (f"{lo}-{hi}" if hi else f"almeno {lo}")
        raise ValueError(
            f"expr: '{name}' vuole {span} argomenti (ricevuti {count})."
        )
    if name == "mix":
        return _mix(*args)

    def apply(*xs):
        try:
            return fn(*xs)
        except (ValueError, OverflowError):
            frag = ", ".join(repr(x) for x in xs)
            raise ValueError(f"expr: {name}({frag}) fuori dominio.") from None

    env_pos = [k for k, a in enumerate(args) if not _is_scalar(a)]
    if not env_pos:
        return apply(*args)
    if len(env_pos) > 1:
        raise ValueError(
            "expr: operazione tra due Env non supportata (solo Env con scalare)."
        )
    (k,) = env_pos

    def on_y(y):
        xs = list(args)
        xs[k] = y
        return apply(*xs)

    return _map_y(args[k], on_y)


# --- mix(A, B, w): il morphing tra due forme ---------------------------------
#
# Port di ``granstudies.expr._mix``: ricampiona A e B sull'unione dei tempi e
# interpola le y col peso ``w`` (a sua volta Env ammesso). Fast-path esatti
# dove il risultato resta piecewise-linear; altrove campionamento adattivo.

_MIX_REL_TOL = 1e-3
_MIX_MAX_DEPTH = 12


def _mix_form(v: Any) -> Tuple[str, Any, float]:
    """``(kind, data, curve)`` di un argomento di mix."""
    if _is_scalar(v):
        return "scalar", v, 1.0
    if isinstance(v, dict):
        kind = v.get("type", "linear")
        curve = v.get("curve", 1.0)
        pts = sorted(v["points"], key=lambda p: p[0])
        if kind == "step":
            if curve != 1.0:
                raise ValueError(
                    "expr: mix, 'curve' non ha effetto con 'type: step' "
                    "(nessuna rampa da piegare)."
                )
            return "step", pts, 1.0
        if kind != "linear":
            raise ValueError(
                f"expr: mix, type '{kind}' non campionabile (linear | step)."
            )
        if curve <= 0:
            raise ValueError(
                f"expr: mix, curve deve essere > 0 (ricevuto {curve})."
            )
        return "linear", pts, curve
    if _is_pairs(v):
        return "linear", sorted(([t, y] for t, y in v), key=lambda p: p[0]), 1.0
    a, b = v  # shorthand [a, b] == [[0, a], [1, b]]
    return "linear", [[0.0, a], [1.0, b]], 1.0


def _form_at(form: Tuple[str, Any, float], t: float) -> float:
    """La forma campionata al tempo ``t``, con hold fuori dai bordi."""
    kind, data, curve = form
    if kind == "scalar":
        return data
    pts = data
    if t <= pts[0][0]:
        return pts[0][1]
    if t >= pts[-1][0]:
        return pts[-1][1]
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if t0 <= t <= t1:
            if kind == "step" or t1 == t0:
                return v0
            u = (t - t0) / (t1 - t0)
            if curve != 1.0:
                u = u ** curve
            return v0 + (v1 - v0) * u
    return pts[-1][1]  # irraggiungibile: t e' tra primo e ultimo tempo


def _mix(a: Any, b: Any, w: Any) -> Any:
    """``A*(1-w) + B*w``: morphing pesato tra due forme."""
    forms = [_mix_form(x) for x in (a, b, w)]
    kinds = {kind for kind, _, _ in forms if kind != "scalar"}
    if not kinds:
        return a + (b - a) * w
    if "step" in kinds and "linear" in kinds:
        raise ValueError(
            "expr: mix tra una forma step e una continua non e' supportato "
            "(discontinuita' pesata, fuori dal v1) — dichiara le forme "
            "entrambe step o entrambe continue."
        )

    def value(t: float) -> float:
        va = _form_at(forms[0], t)
        vb = _form_at(forms[1], t)
        vw = _form_at(forms[2], t)
        return va + (vb - va) * vw

    times = sorted({
        t for kind, data, _ in forms if kind != "scalar" for t, _ in data
    })
    if kinds == {"step"}:
        return {"type": "step", "points": [[t, value(t)] for t in times]}
    exact = all(
        curve == 1.0 for kind, _, curve in forms if kind == "linear"
    ) and (
        forms[2][0] == "scalar"
        or (forms[0][0] == "scalar" and forms[1][0] == "scalar")
    )
    if exact or len(times) < 2:
        return [[t, value(t)] for t in times]
    return _mix_adaptive(value, times)


def _mix_adaptive(value, times: list) -> list:
    """Breakpoint lineari adattivi di ``value`` sui segmenti di ``times``."""
    samples = [(t, value(t)) for t in times]
    mids = [
        ((t0 + t1) / 2, value((t0 + t1) / 2))
        for (t0, _), (t1, _) in zip(samples, samples[1:])
    ]
    ys = [y for _, y in samples] + [y for _, y in mids]
    span = max(ys) - min(ys)
    tol = max(span * _MIX_REL_TOL, 1e-9)
    out = [samples[0]]

    def refine(t0, y0, t1, y1, depth):
        tm = (t0 + t1) / 2
        ym = value(tm)
        if abs(ym - (y0 + y1) / 2) <= tol or depth >= _MIX_MAX_DEPTH:
            out.append((t1, y1))
            return
        refine(t0, y0, tm, ym, depth + 1)
        refine(tm, ym, t1, y1, depth + 1)

    for (t0, y0), (t1, y1) in zip(samples, samples[1:]):
        refine(t0, y0, t1, y1, 0)
    return [[t, y] for t, y in out]


def _rebuild(v: Any) -> Any:
    """Copia del risultato con i float arrotondati a 9 decimali."""
    if isinstance(v, complex):
        raise ValueError(
            "expr: risultato complesso (potenza frazionaria di un negativo?) "
            "— le espressioni producono solo reali."
        )
    if isinstance(v, float):
        return round(v, 9)
    if isinstance(v, int):
        return v
    if isinstance(v, dict):
        return {**v, "points": [[_rebuild(t), _rebuild(y)] for t, y in v["points"]]}
    return [_rebuild(x) for x in v]
