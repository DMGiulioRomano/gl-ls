"""Code lens: i conteggi derivati del processo, sopra le sezioni.

- sweep: quante varianti per ordine e durata stimata di una variante envelope;
- ogni asse: n valori, curva, strategy-X;
- ogni camminata-X: breakpoint stimati sulla banda media;
- ogni entry-spread: quanti stream genera e con che nomi.
"""
from __future__ import annotations

from typing import Any, List, Optional

from lsprotocol import types

from . import engine_info as EI
from .convert import env_eval, env_points, fmt_num
from .model import StudyModel
from .yamlpos import Document, KeyPath


def _num(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _lens(doc: Document, path: KeyPath, title: str) -> Optional[types.CodeLens]:
    e = doc.entry(path)
    if e is None:
        return None
    span = e.key_span or e.value_span
    return types.CodeLens(
        range=types.Range(
            start=types.Position(span.start_line, span.start_col),
            end=types.Position(span.end_line, span.end_col),
        ),
        command=types.Command(title=title, command="glls.noop"),
    )


def lenses(doc: Document, m: StudyModel) -> List[types.CodeLens]:
    out: List[types.CodeLens] = []
    if doc.data is None:
        return out

    counts = m.sweep_counts()
    if counts and doc.entry(("sweep",)):
        parts = [f"e{o}: {c} variant{'e' if c == 1 else 'i'}"
                 for o, c in sorted(counts.items())]
        plateau = _num(m.sweep.get("plateau")) or 5.0
        transition = _num(m.sweep.get("transition")) or 5.0
        ns = [ax.n for ax in m.axes.values() if ax.n]
        est = ""
        if ns:
            n = max(ns)
            est = f" · e1 envelope ≈ {fmt_num(n * plateau + (n - 1) * transition)}s"
        lens = _lens(doc, ("sweep",), "sweep: " + " · ".join(parts) + est)
        if lens:
            out.append(lens)

    for name, ax in m.axes.items():
        walk = m.walk_for(name)
        if walk is not None:
            x = f"X: camminata ({walk.unit})"
        else:
            x = "X: linear"
        n = f"{ax.n} valori" if ax.n else ("n dalla camminata-X" if ax.defers_n else "n ?")
        lens = _lens(doc, ("axes", name),
                     f"{ax.path or '?'} · {n} · {ax.interpolation} · {x}")
        if lens:
            out.append(lens)

    for name, walk in m.walks.items():
        est = _walk_estimate(m, walk.cfg, walk.unit)
        title = f"camminata-X in {walk.unit}"
        if est is not None:
            title += f" · ~{est} breakpoint su {fmt_num(m.duration)}s"
        lens = _lens(doc, ("stack", name), title)
        if lens:
            out.append(lens)

    for name, si in m.streams.items():
        if not si.is_spread:
            continue
        if si.spread_n:
            width = len(str(si.spread_n))
            first = f"{name}_{1:0{width}d}" if si.spread_n > 9 else f"{name}_1"
            last = (f"{name}_{si.spread_n}" if si.spread_n <= 9
                    else f"{name}_{si.spread_n:0{width}d}")
            title = f"spread: genera {si.spread_n} stream ({first} … {last})"
        else:
            title = "spread: n non determinabile staticamente"
        lens = _lens(doc, ("streams", name), title)
        if lens:
            out.append(lens)
    return out


def _walk_estimate(m: StudyModel, cfg: dict, unit: str) -> Optional[int]:
    if not m.duration or m.duration <= 0:
        return None
    bpts = env_points(cfg.get("base"))
    rpts = env_points(cfg.get("range")) if cfg.get("range") is not None else [(0.0, 0.0)]
    if bpts is None or rpts is None:
        return None
    times = sorted({t for t, _ in bpts} | {t for t, _ in rpts})
    mids = []
    for t in times:
        lo = env_eval(bpts, t)
        w = env_eval(rpts, t)
        if lo <= 0 or lo + w <= 0:
            return None
        mids.append(lo + w / 2.0)
    mean = sum(mids) / len(mids)
    step = {"hz": lambda v: 1.0 / v, "s": lambda v: v,
            "bpm": lambda v: 60.0 / v}.get(unit, lambda v: 1.0 / v)(mean)
    if step <= 0:
        return None
    return int(m.duration / step)
