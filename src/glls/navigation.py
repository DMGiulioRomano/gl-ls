"""Navigazione: definition/references sui nomi d'asse, link ai sample.

Un nome d'asse e' *definito* in ``axes:`` e *riferito* in ``stack:``, negli
item di ``sweep.orderings`` e nei path puntati di ``spread.over``
(``axes.<asse>.*`` / ``stack.<asse>.*``). ``sample:`` diventa un DocumentLink
verso il file in ``samples_dir`` (risolto risalendo le directory).
"""
from __future__ import annotations

import os
from typing import List, Optional, Tuple
from urllib.parse import quote
from urllib.request import url2pathname

from lsprotocol import types

from .model import AXES_RESERVED, STACK_RESERVED, StudyModel
from .yamlpos import Document, KeyPath, Span


def _rng(span: Span) -> types.Range:
    return types.Range(
        start=types.Position(span.start_line, span.start_col),
        end=types.Position(span.end_line, span.end_col),
    )


def _axis_at(doc: Document, m: StudyModel, line: int, col: int) -> Optional[str]:
    """Nome d'asse sotto il cursore (definizione o riferimento)."""
    path, where = doc.path_at(line, col)
    if not path:
        return None
    # definizione: axes.<name> / riferimento diretto: stack.<name>
    if where == "key" and len(path) == 2 and isinstance(path[-1], str):
        if path[0] == "axes" and path[1] not in AXES_RESERVED:
            return str(path[1])
        if path[0] == "stack" and path[1] not in STACK_RESERVED:
            return str(path[1])
    # item di orderings
    value = doc.get(path)
    if isinstance(value, str) and value in m.axes:
        return value
    # path puntati di spread.over: axes.<name>.* | stack.<name>.*
    if where == "key" and isinstance(path[-1], str) and "." in str(path[-1]):
        parts = str(path[-1]).split(".")
        if len(parts) >= 2 and parts[0] in ("axes", "stack") and parts[1] in m.axes:
            return parts[1]
    return None


def _axis_locations(doc: Document, m: StudyModel, name: str,
                    include_definition: bool) -> List[Span]:
    spans: List[Span] = []
    def_entry = doc.entry(("axes", name))
    if include_definition and def_entry is not None and def_entry.key_span:
        spans.append(def_entry.key_span)
    stack_entry = doc.entry(("stack", name))
    if stack_entry is not None and stack_entry.key_span:
        spans.append(stack_entry.key_span)
    for entry in doc.iter_entries():
        p = entry.path
        # item di orderings (in root e negli override)
        if (entry.kind == "scalar" and entry.scalar_raw == name
                and len(p) >= 3 and "orderings" in p):
            spans.append(entry.value_span)
        # chiavi puntate di spread.over e override stack negli stream
        if entry.key_span and isinstance(p[-1], str):
            last = str(p[-1])
            if "." in last:
                parts = last.split(".")
                if len(parts) >= 2 and parts[0] in ("axes", "stack") and parts[1] == name:
                    spans.append(entry.key_span)
            elif last == name and len(p) >= 3 and p[0] == "streams" and p[-2] in ("axes", "stack"):
                spans.append(entry.key_span)
    return spans


def definition(doc: Document, m: StudyModel, uri: str, line: int,
               col: int) -> Optional[types.Location]:
    name = _axis_at(doc, m, line, col)
    if name is None or name not in m.axes:
        return None
    entry = doc.entry(("axes", name))
    if entry is None or entry.key_span is None:
        return None
    return types.Location(uri=uri, range=_rng(entry.key_span))


def references(doc: Document, m: StudyModel, uri: str, line: int,
               col: int, include_declaration: bool) -> List[types.Location]:
    name = _axis_at(doc, m, line, col)
    if name is None:
        return []
    return [types.Location(uri=uri, range=_rng(s))
            for s in _axis_locations(doc, m, name, include_declaration)]


# ---------------------------------------------------------------------------


def _find_samples_dir(file_dir: Optional[str], samples_dir: str) -> Optional[str]:
    if not file_dir:
        return None
    d = file_dir
    for _ in range(6):
        cand = os.path.join(d, samples_dir)
        if os.path.isdir(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent
    return None


def document_links(doc: Document, m: StudyModel, uri: str) -> List[types.DocumentLink]:
    out: List[types.DocumentLink] = []
    if doc.data is None:
        return out
    file_dir = None
    if uri.startswith("file://"):
        file_dir = os.path.dirname(url2pathname(uri[len("file://"):]))
    samples_dir = doc.get(("samples_dir",), "samples") or "samples"
    root = _find_samples_dir(file_dir, str(samples_dir))
    if root is None:
        return out
    for entry in doc.iter_entries():
        p = entry.path
        if (entry.kind == "scalar" and p and p[-1] == "sample"
                and isinstance(entry.scalar_raw, str)):
            target = os.path.join(root, entry.scalar_raw)
            if os.path.isfile(target):
                out.append(types.DocumentLink(
                    range=_rng(entry.value_span),
                    target="file://" + quote(target),
                    tooltip="apri il sample",
                ))
    return out
