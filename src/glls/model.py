"""Modello semantico di uno ``study.yml`` gia' parsato.

Estrae dal :class:`glls.yamlpos.Document` la vista che serve alle feature:
assi con il loro generatore Y, camminate-X del blocco stack con unit risolta
per precedenza, stream (incluse le entry-spread), durata condivisa. Tutto
tollerante: il modello si costruisce anche da documenti incompleti.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .convert import as_num as _num
from .yamlpos import Document, KeyPath

AXES_RESERVED = ("interpolation", "seed")
STACK_RESERVED = ("seed", "unit")
GEN_MARKERS = ("values", "ramp", "base")
BAND_KEYS = frozenset({"base", "range", "n", "seed", "distribution", "drift"})


@dataclass
class AxisInfo:
    name: str
    path: Optional[str]
    cfg: Dict[str, Any]
    doc_path: KeyPath                     # path nel documento
    generator: Optional[str] = None       # values | ramp | band | None
    n: Optional[int] = None               # conteggio posseduto dalla Y, se noto
    interpolation: str = "linear"

    @property
    def defers_n(self) -> bool:
        return self.generator == "band" and "n" not in self.cfg


@dataclass
class WalkInfo:
    axis: str
    cfg: Dict[str, Any]
    doc_path: KeyPath
    unit: str = "hz"                      # unit risolta (per-asse > globale > hz)


@dataclass
class StreamInfo:
    name: str
    cfg: Dict[str, Any]
    doc_path: KeyPath
    is_spread: bool = False
    spread_n: Optional[int] = None


@dataclass
class StudyModel:
    doc: Document
    study_id: Optional[str] = None
    duration: Optional[float] = None
    base: Dict[str, Any] = field(default_factory=dict)
    time_mode: str = "absolute"
    base_duration: Optional[float] = None
    axes: Dict[str, AxisInfo] = field(default_factory=dict)
    axes_seed: Optional[int] = None
    study_interpolation: str = "linear"
    sweep: Dict[str, Any] = field(default_factory=dict)
    has_stack: bool = False
    stack_unit: Optional[str] = None
    walks: Dict[str, WalkInfo] = field(default_factory=dict)
    streams: Dict[str, StreamInfo] = field(default_factory=dict)

    # ------------------------------------------------------------------
    def axis_names(self) -> List[str]:
        return list(self.axes)

    def walk_for(self, axis: str) -> Optional[WalkInfo]:
        return self.walks.get(axis)

    def sweep_counts(self) -> Optional[Dict[int, int]]:
        """{ordine: numero varianti} per gli orders dichiarati (se calcolabile)."""
        from math import comb

        counts: Dict[int, int] = {}
        n = len(self.axes)
        if n == 0:
            return None
        orders = self.sweep.get("orders", list(range(1, n + 1)))
        if not isinstance(orders, list):
            return None
        for o in orders:
            if isinstance(o, int) and 0 <= o <= n:
                counts[o] = comb(n, o)
        return counts or None



def ramp_count(cfg: Dict[str, Any]) -> Optional[int]:
    """Numero di punti di una ``ramp`` scalare piena (None se non statico)."""
    start, stop, step = cfg.get("start"), cfg.get("stop"), cfg.get("step")
    s0, s1, st = _num(start), _num(stop), _num(step)
    if s0 is None or s1 is None or st is None or st <= 0:
        return None
    import math

    span = abs(s1 - s0)
    return int(math.floor(span / st + 1e-9)) + 1


def y_generator_of(cfg: Dict[str, Any]) -> Tuple[Optional[str], Optional[int]]:
    """(generatore, n posseduto) di un dict-asse/strategy: values | ramp | band."""
    markers = [m for m in GEN_MARKERS if m in cfg]
    if len(markers) != 1:
        return (None, None)
    m = markers[0]
    if m == "values":
        vals = cfg.get("values")
        return ("values", len(vals) if isinstance(vals, list) else None)
    if m == "ramp":
        r = cfg.get("ramp")
        return ("ramp", ramp_count(r) if isinstance(r, dict) else None)
    n = cfg.get("n")
    return ("band", n if isinstance(n, int) and not isinstance(n, bool) else None)


def build(doc: Document) -> StudyModel:
    m = StudyModel(doc=doc)
    data = doc.data
    if not isinstance(data, dict):
        return m
    m.study_id = data.get("study_id") if isinstance(data.get("study_id"), str) else None
    m.duration = _num(data.get("duration"))

    base = data.get("base")
    if isinstance(base, dict):
        m.base = base
        tm = base.get("time_mode")
        if tm in ("absolute", "normalized"):
            m.time_mode = tm
        m.base_duration = _num(base.get("duration"))

    axes = data.get("axes")
    if isinstance(axes, dict):
        interp = axes.get("interpolation")
        if isinstance(interp, str):
            m.study_interpolation = interp
        seed = axes.get("seed")
        if isinstance(seed, int):
            m.axes_seed = seed
        for name, cfg in axes.items():
            if name in AXES_RESERVED or not isinstance(cfg, dict):
                continue
            gen, n = y_generator_of(cfg)
            m.axes[name] = AxisInfo(
                name=name,
                path=cfg.get("path") if isinstance(cfg.get("path"), str) else None,
                cfg=cfg,
                doc_path=("axes", name),
                generator=gen,
                n=n,
                interpolation=cfg.get("interpolation", m.study_interpolation),
            )

    sweep = data.get("sweep")
    if isinstance(sweep, dict):
        m.sweep = sweep

    if "stack" in data:
        m.has_stack = True
        stack = data.get("stack")
        if isinstance(stack, dict):
            unit = stack.get("unit")
            m.stack_unit = unit if isinstance(unit, str) else None
            for name, cfg in stack.items():
                if name in STACK_RESERVED or cfg is None or not isinstance(cfg, dict):
                    continue
                per_axis = cfg.get("unit")
                resolved = per_axis if isinstance(per_axis, str) else (m.stack_unit or "hz")
                m.walks[name] = WalkInfo(
                    axis=name, cfg=cfg, doc_path=("stack", name), unit=resolved
                )

    streams = data.get("streams")
    if isinstance(streams, dict):
        for name, cfg in streams.items():
            cfg = cfg if isinstance(cfg, dict) else {}
            spread = cfg.get("spread")
            is_spread = isinstance(spread, dict)
            n = None
            if is_spread:
                n = spread.get("n") if isinstance(spread.get("n"), int) else None
                if n is None:
                    over = spread.get("over")
                    if isinstance(over, dict):
                        for strat in over.values():
                            if isinstance(strat, dict):
                                _, owned = y_generator_of(strat)
                                if owned:
                                    n = owned
                                    break
                            elif isinstance(strat, list):
                                n = len(strat)
                                break
            m.streams[name] = StreamInfo(
                name=name, cfg=cfg, doc_path=("streams", name),
                is_spread=is_spread, spread_n=n,
            )
    return m
