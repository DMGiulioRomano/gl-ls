"""Trasformazioni numeriche pure per le code action di ricalcolo.

- conversione della banda della camminata-X tra le unita' ``hz``/``s``/``bpm``
  (il "rand di X in stack"): ricalcola ``base``/``range`` nello spazio di
  destinazione, ricordando che il passaggio rate<->periodo **inverte i bordi**
  della banda (`[lo, lo+w]` in hz diventa `[1/(lo+w), 1/lo]` in s);
- riscala dei tempi (breakpoint X) al cambio di ``duration``;
- serializzazione YAML flow compatta dei risultati.

Tutto deterministico e senza dipendenze: unit-testabile in isolamento.
"""
from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple


class ConversionError(ValueError):
    """Forma di Env non convertibile staticamente (generatore, expr, curve...)."""


# ---------------------------------------------------------------------------
# Formattazione numeri / YAML flow


def fmt_num(x: Any) -> str:
    if isinstance(x, bool):
        return str(x).lower()
    if isinstance(x, int):
        return str(x)
    r = round(float(x), 9)
    if r == int(r) and abs(r) < 1e15:
        return str(int(r))
    s = repr(r)
    return s


def yaml_flow(value: Any) -> str:
    """Serializza scalari e liste annidate in YAML flow (`[[0, 20], [1, 4]]`)."""
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(yaml_flow(v) for v in value) + "]"
    if isinstance(value, str):
        return value
    if value is None:
        return "null"
    return fmt_num(value)


# ---------------------------------------------------------------------------
# Env statici -> breakpoint


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def as_num(v: Any) -> Optional[float]:
    """Il valore come float, o None se non e' un numero (bool escluso)."""
    return float(v) if _is_num(v) else None


def env_points(form: Any) -> Optional[List[Tuple[float, float]]]:
    """Breakpoint ``[(t, v), ...]`` di una forma *statica* di Env.

    Forme accettate: scalare (costante), ``[a, b]`` (rampa 0->1),
    ``[[t, v], ...]``, ``{type: linear, points: [[t, v], ...]}`` senza curve.
    Ritorna ``None`` per ogni altra forma (generatore annidato, expr, step,
    curve, punti a 3 elementi): il chiamante decide se rifiutare.
    """
    if _is_num(form):
        return [(0.0, float(form)), (1.0, float(form))]
    if isinstance(form, (list, tuple)):
        if len(form) == 2 and all(_is_num(v) for v in form):
            return [(0.0, float(form[0])), (1.0, float(form[1]))]
        pts: List[Tuple[float, float]] = []
        for p in form:
            if not (isinstance(p, (list, tuple)) and len(p) == 2
                    and all(_is_num(v) for v in p)):
                return None
            pts.append((float(p[0]), float(p[1])))
        return sorted(pts) if pts else None
    if isinstance(form, dict):
        if form.get("type", "linear") != "linear":
            return None
        if "curve" in form and form.get("curve") not in (None, 1, 1.0):
            return None
        if set(form) - {"type", "points", "curve"}:
            return None
        return env_points(form.get("points"))
    return None


def env_eval(points: Sequence[Tuple[float, float]], t: float) -> float:
    """Valutazione lineare con hold fuori dai bordi."""
    if t <= points[0][0]:
        return points[0][1]
    if t >= points[-1][0]:
        return points[-1][1]
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        if t0 <= t <= t1:
            if t1 == t0:
                return v1
            u = (t - t0) / (t1 - t0)
            return v0 + (v1 - v0) * u
    return points[-1][1]


def _shape_of(form: Any) -> str:
    if _is_num(form):
        return "scalar"
    if isinstance(form, (list, tuple)) and len(form) == 2 and all(_is_num(v) for v in form):
        return "pair"
    return "points"


def _repack(points: List[Tuple[float, float]], shape_hint: str) -> Any:
    """Rende i punti nella forma piu' compatta coerente con l'input."""
    ys = [round(v, 9) for _, v in points]
    if all(y == ys[0] for y in ys):
        return ys[0]
    if shape_hint in ("scalar", "pair") and len(points) == 2:
        return [ys[0], ys[1]]
    return [[round(t, 9), y] for (t, _), y in zip(points, ys)]


# ---------------------------------------------------------------------------
# Unita' X

_TO_HZ = {"hz": lambda v: v, "bpm": lambda v: v / 60.0, "s": lambda v: 1.0 / v}
_FROM_HZ = {"hz": lambda h: h, "bpm": lambda h: h * 60.0, "s": lambda h: 1.0 / h}
RATE = {"hz", "bpm"}


def _endpoints(lo: float, w: float, src: str, dst: str) -> Tuple[float, float]:
    """Nuovi (lo, w) dell'intervallo ``[lo, lo+w]`` convertito da src a dst."""
    a, b = lo, lo + w
    if a <= 0 or b <= 0:
        raise ConversionError(
            f"banda non positiva [{fmt_num(a)}, {fmt_num(b)}]: la conversione "
            "rate<->periodo richiede valori > 0."
        )
    a2 = _FROM_HZ[dst](_TO_HZ[src](a))
    b2 = _FROM_HZ[dst](_TO_HZ[src](b))
    lo2, hi2 = (a2, b2) if a2 <= b2 else (b2, a2)
    return lo2, hi2 - lo2


def convert_band(
    base_form: Any,
    range_form: Any,
    src: str,
    dst: str,
) -> Tuple[Any, Any]:
    """Converte la banda ``[base, base+range]`` della camminata-X tra unita'.

    Ritorna ``(nuovo_base, nuovo_range)`` nelle forme piu' compatte; il nuovo
    range e' ``None`` se resta identicamente nullo (camminata deterministica,
    la chiave puo' restare assente). Solleva :class:`ConversionError` per
    forme non statiche (nodo generatore, expr, step, curve) o valori non
    positivi nel passaggio rate<->periodo.

    Nota semantica: la conversione preserva la **banda** punto per punto, non
    la distribuzione dentro la banda — uniforme in periodo non e' uniforme in
    frequenza (vedi doc study-yml, blocco stack).
    """
    if src == dst:
        return base_form, range_form
    if src not in _TO_HZ or dst not in _TO_HZ:
        raise ConversionError(f"unit sconosciuta: {src!r} -> {dst!r}")

    same_family = src in RATE and dst in RATE
    if same_family:
        k = _TO_HZ[src](1.0) * _FROM_HZ[dst](1.0)  # bpm->hz->bpm: fattore lineare
        new_base = _scale_y(base_form, k)
        new_range = _scale_y(range_form, k) if range_form is not None else None
        return new_base, new_range

    bpts = env_points(base_form)
    if bpts is None:
        raise ConversionError(
            "forma di 'base' non convertibile staticamente (nodo generatore, "
            "expr, type: step o curve): converti a mano o semplifica la forma."
        )
    if range_form is None:
        rpts: List[Tuple[float, float]] = [(0.0, 0.0), (1.0, 0.0)]
    else:
        rpts = env_points(range_form)
        if rpts is None:
            raise ConversionError(
                "forma di 'range' non convertibile staticamente (nodo "
                "generatore, expr, type: step o curve)."
            )
    times = sorted({t for t, _ in bpts} | {t for t, _ in rpts})
    new_b: List[Tuple[float, float]] = []
    new_r: List[Tuple[float, float]] = []
    for t in times:
        lo = env_eval(bpts, t)
        w = env_eval(rpts, t)
        if w < 0:
            raise ConversionError(f"range negativo ({fmt_num(w)}) a t={fmt_num(t)}.")
        lo2, w2 = _endpoints(lo, w, src, dst)
        new_b.append((t, lo2))
        new_r.append((t, w2))
    base_out = _repack(new_b, _shape_of(base_form))
    range_out = _repack(new_r, _shape_of(range_form) if range_form is not None else "scalar")
    if _is_num(range_out) and abs(float(range_out)) < 1e-12:
        range_out = None if range_form is None else 0
    return base_out, range_out


def _scale_y(form: Any, k: float) -> Any:
    """Y * k su una forma statica (shape-preserving, dict incluso)."""
    if _is_num(form):
        return round(form * k, 9)
    if isinstance(form, (list, tuple)):
        if len(form) == 2 and all(_is_num(v) for v in form):
            return [round(form[0] * k, 9), round(form[1] * k, 9)]
        out = []
        for p in form:
            if not (isinstance(p, (list, tuple)) and len(p) == 2
                    and all(_is_num(v) for v in p)):
                raise ConversionError("breakpoint non numerico nella banda.")
            out.append([p[0], round(p[1] * k, 9)])
        return out
    if isinstance(form, dict):
        if set(form) - {"type", "points", "curve"}:
            raise ConversionError(
                "nodo non statico dentro base/range: conversione manuale."
            )
        pts = form.get("points")
        if not isinstance(pts, list):
            raise ConversionError("dict senza 'points' nella banda.")
        return {**form, "points": _scale_y(pts, k)}
    raise ConversionError(f"forma di banda non riconosciuta: {form!r}")


# ---------------------------------------------------------------------------
# Riscala tempi al cambio di duration


def rescale_time(t: float, factor: float) -> float:
    return round(t * factor, 9)
