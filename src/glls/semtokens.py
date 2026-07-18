"""Token semantici: la struttura del linguaggio sopra l'highlight YAML.

Classi: sezioni axes/stack/base (struct), sezione streams (namespace),
chiave spread (decorator), altre chiavi radice (keyword), nomi d'asse
(type), nomi di stream (class), chiavi engine (property), marcatori di
generatore/banda (macro), valori enum (enumMember), path puntati
(property), contenuto dei nodi-expr tokenizzato (variable/operator/number).
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from . import engine_info as EI
from . import schema
from .model import AXES_RESERVED, STACK_RESERVED, StudyModel, split_over_key
from .yamlpos import Document

TOKEN_TYPES = [
    "keyword",     # 0: sezioni del linguaggio
    "type",        # 1: nomi d'asse
    "class",       # 2: nomi di stream
    "property",    # 3: chiavi engine / path puntati
    "macro",       # 4: marcatori generatore/banda/env
    "enumMember",  # 5: valori enum (finestre, unit, interpolation, ...)
    "variable",    # 6: nomi dentro expr
    "operator",    # 7: operatori dentro expr
    "number",      # 8: numeri dentro expr
    "string",      # 9: espressione expr (fallback)
    "struct",      # 10: sezioni axes/stack/base
    "namespace",   # 11: sezione streams
    "decorator",   # 12: chiave spread
]
_T = {name: i for i, name in enumerate(TOKEN_TYPES)}

_ENUM_VALUES = (
    set(EI.WINDOWS) | set(EI.X_UNITS) | set(EI.INTERPOLATIONS)
    | set(EI.SWEEP_MODES) | set(EI.DISTRIBUTIONS) | set(EI.TIME_MODES)
    | set(EI.CLIP_STRATEGIES) | set(EI.DURATION_UNITS) | set(EI.CHORDS)
)

_EXPR_TOKEN = re.compile(r"(?P<num>\d+(?:\.\d+)?)|(?P<name>[A-Za-z_]\w*)|(?P<op>\*\*|[+\-*/()])")


def _classify_key(path, ctx: str, name: str) -> Optional[int]:
    if name == "spread":
        return _T["decorator"]
    if ctx == "root":
        if name in ("axes", "stack", "base"):
            return _T["struct"]
        if name == "streams":
            return _T["namespace"]
        return _T["keyword"]
    if ctx == "stream_override" or name == "over":
        return _T["keyword"]
    if ctx == "axes" and name not in AXES_RESERVED:
        return _T["type"]
    if ctx == "stack" and name not in STACK_RESERVED:
        return _T["type"]
    if ctx == "streams":
        return _T["class"]
    if ctx == "over":
        return _T["property"]
    k = schema.key_in(ctx, name)
    if k is not None:
        if k.kind == "macro":
            return _T["macro"]
        if k.kind == "keyword":
            return _T["keyword"]
        return _T["property"]
    return None


def tokens(doc: Document, m: StudyModel) -> List[int]:
    raw: List[Tuple[int, int, int, int]] = []  # line, col, length, type
    lines = doc.text.splitlines()

    for entry in doc.iter_entries():
        path = entry.path
        if not path:
            continue
        # chiavi
        if entry.key_span is not None and isinstance(path[-1], str):
            ctx = schema.context_for_path(path[:-1], frozenset(m.axes))
            key = path[-1]
            ks = entry.key_span
            split = (split_over_key(key, doc.get(path)) if ctx == "over" else None)
            if split is not None and ks.start_line == ks.end_line:
                # chiave puntata splittata: path come property, marcatore come
                # macro (il '.' di separazione resta senza token)
                head, marker = split
                raw.append((ks.start_line, ks.start_col, len(head), _T["property"]))
                raw.append((ks.start_line, ks.start_col + len(head) + 1,
                            len(marker), _T["macro"]))
            else:
                tok = _classify_key(path, ctx, key)
                if tok is not None and ks.start_line == ks.end_line:
                    raw.append((ks.start_line, ks.start_col,
                                ks.end_col - ks.start_col, tok))
        # valori scalari
        if entry.kind == "scalar" and entry.scalar_raw:
            value = entry.scalar_raw
            vs = entry.value_span
            if vs.start_line != vs.end_line:
                continue
            parent_key = path[-1] if isinstance(path[-1], str) else (
                path[-2] if len(path) >= 2 and isinstance(path[-2], str) else None
            )
            if parent_key == "expr":
                raw.extend(_expr_tokens(lines, vs.start_line, vs.start_col,
                                        vs.end_col))
            elif value in _ENUM_VALUES and isinstance(path[-1], str):
                raw.append((vs.start_line, vs.start_col,
                            vs.end_col - vs.start_col, _T["enumMember"]))
            elif isinstance(path[-1], int) and value in set(m.axes):
                # item di orderings
                raw.append((vs.start_line, vs.start_col,
                            vs.end_col - vs.start_col, _T["type"]))

    raw.sort(key=lambda t: (t[0], t[1]))
    data: List[int] = []
    prev_line, prev_col = 0, 0
    for line, col, length, tok in raw:
        if length <= 0:
            continue
        d_line = line - prev_line
        d_col = col - prev_col if d_line == 0 else col
        data.extend([d_line, d_col, length, tok, 0])
        prev_line, prev_col = line, col
    return data


def _expr_tokens(lines: List[str], line: int, start: int, end: int):
    if line >= len(lines):
        return
    text = lines[line][start:end]
    for mo in _EXPR_TOKEN.finditer(text):
        if mo.group("num"):
            tok = _T["number"]
        elif mo.group("name"):
            tok = _T["variable"]
        else:
            tok = _T["operator"]
        yield (line, start + mo.start(), mo.end() - mo.start(), tok)
