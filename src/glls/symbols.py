"""Outline del documento: studio, base, assi, sweep, stack, stream."""
from __future__ import annotations

from typing import List, Optional

from lsprotocol import types

from .model import AXES_RESERVED, STACK_RESERVED, StudyModel
from .yamlpos import Document, KeyPath, Span


def _rng(span: Span) -> types.Range:
    return types.Range(
        start=types.Position(span.start_line, span.start_col),
        end=types.Position(span.end_line, span.end_col),
    )


def _sym(doc: Document, path: KeyPath, name: str, kind: types.SymbolKind,
         detail: str = "", children: Optional[List[types.DocumentSymbol]] = None
         ) -> Optional[types.DocumentSymbol]:
    e = doc.entry(path)
    if e is None:
        return None
    full = Span(
        e.key_span.start_line if e.key_span else e.value_span.start_line,
        e.key_span.start_col if e.key_span else e.value_span.start_col,
        e.value_span.end_line, e.value_span.end_col,
    )
    return types.DocumentSymbol(
        name=name, kind=kind, range=_rng(full),
        selection_range=_rng(e.key_span or e.value_span),
        detail=detail or None, children=children or [],
    )


def symbols(doc: Document, m: StudyModel) -> List[types.DocumentSymbol]:
    out: List[types.DocumentSymbol] = []

    if doc.entry(("base",)):
        s = _sym(doc, ("base",), "base", types.SymbolKind.Namespace,
                 detail=f"sample: {m.base.get('sample', '?')}")
        if s:
            out.append(s)

    axes_children: List[types.DocumentSymbol] = []
    for name, ax in m.axes.items():
        gen = ax.generator or "?"
        n = f"n={ax.n}" if ax.n else ("n←X" if ax.defers_n else "")
        s = _sym(doc, ("axes", name), name, types.SymbolKind.Variable,
                 detail=" · ".join(x for x in (ax.path or "?", gen, n) if x))
        if s:
            axes_children.append(s)
    if doc.entry(("axes",)):
        s = _sym(doc, ("axes",), "axes", types.SymbolKind.Namespace,
                 detail=f"{len(m.axes)} assi", children=axes_children)
        if s:
            out.append(s)

    if doc.entry(("sweep",)):
        counts = m.sweep_counts()
        detail = ""
        if counts:
            detail = " · ".join(f"e{o}: {c}" for o, c in sorted(counts.items()))
        s = _sym(doc, ("sweep",), "sweep", types.SymbolKind.Namespace, detail=detail)
        if s:
            out.append(s)

    if doc.entry(("stack",)):
        walk_children: List[types.DocumentSymbol] = []
        for name, w in m.walks.items():
            s = _sym(doc, ("stack", name), name, types.SymbolKind.Function,
                     detail=f"camminata-X · {w.unit}")
            if s:
                walk_children.append(s)
        s = _sym(doc, ("stack",), "stack", types.SymbolKind.Namespace,
                 detail="documento multi-stream", children=walk_children)
        if s:
            out.append(s)

    stream_children: List[types.DocumentSymbol] = []
    for name, si in m.streams.items():
        kind = types.SymbolKind.Array if si.is_spread else types.SymbolKind.Object
        detail = f"spread ×{si.spread_n or '?'}" if si.is_spread else ""
        s = _sym(doc, ("streams", name), name, kind, detail=detail)
        if s:
            stream_children.append(s)
    if doc.entry(("streams",)):
        s = _sym(doc, ("streams",), "streams", types.SymbolKind.Namespace,
                 detail=f"{len(m.streams)} entry", children=stream_children)
        if s:
            out.append(s)
    return out
