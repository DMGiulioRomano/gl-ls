"""Inlay hint: il numero che leggi, tradotto nello spazio che ti serve.

- valori della camminata-X: conversione nell'altra unita' (`20` con unit s ->
  `≈ 0.05 hz`), cosi' il "rand di X in stack" si legge in entrambi gli spazi;
- tempi normalizzati dei breakpoint: resi in secondi sulla duration;
- duty factor accanto a grain.duration quando density e grain.duration sono
  scalari (`duty ≈ density × grain.duration`).
"""
from __future__ import annotations

from typing import Any, List, Optional

from lsprotocol import types

from . import engine_info as EI
from .convert import fmt_num
from .model import STACK_RESERVED, StudyModel
from .yamlpos import Document, KeyPath

MAX_HINTS = 60


def _num(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _hint(line: int, col: int, label: str) -> types.InlayHint:
    return types.InlayHint(
        position=types.Position(line, col),
        label=label,
        kind=types.InlayHintKind.Type,
        padding_left=True,
    )


def hints(doc: Document, m: StudyModel, start_line: int, end_line: int
          ) -> List[types.InlayHint]:
    out: List[types.InlayHint] = []
    if doc.data is None:
        return out

    # 1) conversioni sulle bande della camminata-X
    for name, walk in m.walks.items():
        alt = "s" if walk.unit in ("hz", "bpm") else "hz"
        for border in ("base", "range"):
            form = walk.cfg.get(border)
            n = _num(form)
            if n is None or n <= 0:
                continue
            e = doc.entry(("stack", name, border))
            if e is None or not (start_line <= e.value_span.end_line <= end_line):
                continue
            if border == "base":
                label = f"≈ {fmt_num(EI.unit_convert_value(n, walk.unit, alt))} {alt}"
            else:
                from .convert import env_points

                bpts = env_points(walk.cfg.get("base"))
                if bpts is None:
                    continue
                base_n = bpts[0][1]  # banda all'inizio della camminata
                if base_n <= 0:
                    continue
                hi = base_n + n
                a = EI.unit_convert_value(base_n, walk.unit, alt)
                b = EI.unit_convert_value(hi, walk.unit, alt)
                lo2, hi2 = (a, b) if a <= b else (b, a)
                label = f"banda(t=0) ≈ [{fmt_num(lo2)}, {fmt_num(hi2)}] {alt}"
            out.append(_hint(e.value_span.end_line, e.value_span.end_col, label))

    # 2) duty factor
    dens = _num(m.base.get("density"))
    grain = m.base.get("grain")
    gdur = _num(grain.get("duration")) if isinstance(grain, dict) else None
    if dens is not None and gdur is not None:
        e = doc.entry(("base", "grain", "duration"))
        if e is not None and start_line <= e.value_span.end_line <= end_line:
            duty = dens * gdur
            state = "buchi" if duty < 1 else "sovrapposti"
            out.append(_hint(e.value_span.end_line, e.value_span.end_col,
                             f"duty ≈ {fmt_num(round(duty, 3))} ({state})"))

    # 3) tempi normalizzati -> secondi (env di banda e stack)
    dur = m.duration or m.base_duration
    if dur:
        for entry in doc.iter_entries():
            if len(out) >= MAX_HINTS:
                break
            path = entry.path
            if (len(path) >= 2 and isinstance(path[-1], int) and path[-1] == 0
                    and entry.kind == "scalar"):
                if not _in_env_context(path):
                    continue
                pair = doc.get(path[:-1])
                if not (isinstance(pair, (list, tuple)) and len(pair) in (2, 3)):
                    continue
                t = _num(pair[0])
                if t is None or not (0 < t < 1):
                    continue
                vs = entry.value_span
                if not (start_line <= vs.end_line <= end_line):
                    continue
                out.append(_hint(vs.end_line, vs.end_col,
                                 f"→{fmt_num(round(t * dur, 3))}s"))
    return out


def _in_env_context(path: KeyPath) -> bool:
    """True per i breakpoint dentro base/range di banda Y o camminata-X."""
    parts = [p for p in path if isinstance(p, str)]
    if not parts:
        return False
    if parts[0] in ("axes", "stack") or (parts[0] == "streams" and
                                         any(p in ("axes", "stack") for p in parts)):
        return any(p in ("base", "range", "points", "step") for p in parts[1:])
    return False
