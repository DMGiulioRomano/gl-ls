"""Completamento contestuale per ``study.yml``.

Il contesto si inferisce dal testo (indentazione), non dal parse: mentre si
digita una chiave nuova il documento e' quasi sempre sintatticamente rotto.
La catena delle chiavi antenate si ricostruisce risalendo le righe con indent
minore; se il documento (senza la riga corrente) parsa, le chiavi gia'
presenti nel mapping vengono escluse dalle proposte.
"""
from __future__ import annotations

import os
import re
from typing import Any, List, Optional, Tuple

from lsprotocol import types

from . import engine_info as EI
from . import schema, yamlpos
from .model import StudyModel, build

_KEY_RE = re.compile(r"^(\s*)(?:-\s+)?([^\s#][^:#]*?):(\s|$)")
_ITEM_RE = re.compile(r"^(\s*)-\s")

_KIND = {
    "keyword": types.CompletionItemKind.Module,
    "property": types.CompletionItemKind.Property,
    "macro": types.CompletionItemKind.Function,
    "string": types.CompletionItemKind.File,
    "internal": types.CompletionItemKind.Text,
}


def infer_context(text: str, line: int, character: int) -> Tuple[Tuple[str, ...], str, Optional[str], str]:
    """(path antenati, modo, chiave corrente, prefisso digitato).

    ``modo`` e' ``"key"`` (si sta scrivendo una chiave) o ``"value"`` (il
    cursore e' dopo i due punti di ``chiave:``).
    """
    lines = text.splitlines()
    cur = lines[line][:character] if line < len(lines) else ""
    stripped = cur.lstrip()
    indent = len(cur) - len(stripped)

    in_item = False
    m_item = _ITEM_RE.match(cur) or re.match(r"^(\s*)-$", cur)
    if m_item:
        in_item = True
        indent = len(m_item.group(1))

    mode = "key"
    key: Optional[str] = None
    prefix = stripped
    m = _KEY_RE.match(cur)
    if m and ":" in cur[len(m.group(1)):]:
        colon = cur.index(":", len(m.group(1)))
        if character > colon:
            mode = "value"
            key = m.group(2).strip()
            prefix = cur[colon + 1:].lstrip()
    if mode == "key" and in_item:
        mode = "item"
        prefix = stripped.lstrip("- ").strip()

    # risale gli antenati: chiavi con indent strettamente minore
    path: List[str] = []
    want = indent
    for i in range(line - 1, -1, -1):
        raw = lines[i]
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        km = _KEY_RE.match(raw)
        if not km:
            continue
        k_indent = len(km.group(1))
        # un item di lista sopra abbassa il livello effettivo
        if _ITEM_RE.match(raw) and k_indent < want:
            continue
        if k_indent < want:
            path.append(km.group(2).strip())
            want = k_indent
            if want == 0:
                break
    path.reverse()
    return tuple(path), mode, key, prefix


def _existing_keys(text: str, line: int, path: Tuple[str, ...]) -> set:
    """Chiavi gia' presenti nel mapping (parse col la riga corrente rimossa)."""
    lines = text.splitlines()
    if line < len(lines):
        lines = lines[:line] + [""] + lines[line + 1:]
    doc = yamlpos.parse("\n".join(lines))
    value = doc.get(path) if doc.data is not None else None
    return set(value) if isinstance(value, dict) else set()


def _samples(root_hint: Optional[str], samples_dir: str) -> List[str]:
    if not root_hint:
        return []
    d = root_hint
    for _ in range(6):
        cand = os.path.join(d, samples_dir)
        if os.path.isdir(cand):
            try:
                return sorted(
                    f for f in os.listdir(cand)
                    if f.lower().endswith((".wav", ".aif", ".aiff", ".flac"))
                )
            except OSError:
                return []
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return []


def _item(label: str, doc: str = "", kind: types.CompletionItemKind = types.CompletionItemKind.Value,
          snippet: Optional[str] = None, sort: str = "5") -> types.CompletionItem:
    return types.CompletionItem(
        label=label,
        kind=kind,
        sort_text=sort + label,
        documentation=types.MarkupContent(kind=types.MarkupKind.Markdown, value=doc) if doc else None,
        insert_text=snippet if snippet else None,
        insert_text_format=types.InsertTextFormat.Snippet if snippet else None,
        filter_text=label,
    )


def complete(
    doc: yamlpos.Document,
    m: StudyModel,
    line: int,
    character: int,
    file_dir: Optional[str] = None,
) -> List[types.CompletionItem]:
    path, mode, key, _prefix = infer_context(doc.text, line, character)
    if mode == "value" and key:
        return _complete_value(doc, m, path, key, file_dir)
    if mode == "item":
        return _complete_item(m, path)
    return _complete_key(doc, m, path, line)


def _complete_key(doc: yamlpos.Document, m: StudyModel,
                  path: Tuple[str, ...], line: int) -> List[types.CompletionItem]:
    ctx = schema.context_for_path(path)
    items: List[types.CompletionItem] = []
    present = _existing_keys(doc.text, line, path)

    for k in schema.keys_for(ctx):
        if k.name in present or k.kind == "internal":
            continue
        snippet = k.snippet
        insert = snippet if snippet else (k.name + ": ")
        items.append(_item(
            k.name, k.doc, _KIND.get(k.kind, types.CompletionItemKind.Property),
            snippet=insert if snippet else None, sort="2",
        ))
        if not snippet:
            items[-1].insert_text = insert

    # contesti a chiavi dinamiche
    if ctx == "stack":
        for name, ax in m.axes.items():
            if name in present:
                continue
            items.append(_item(
                name,
                f"Camminata-X per l'asse **{name}** (`{ax.path or '?'}`): la X "
                "possiede n, la Y va dichiarata come banda senza n.",
                types.CompletionItemKind.Class,
                snippet=f"{name}:\n  base: ${{1:5}}\n  range: ${{2:2}}",
                sort="1",
            ))
    elif ctx == "axes":
        items.append(_item(
            "nuovo_asse",
            "Snippet: nuovo asse con path e banda.",
            types.CompletionItemKind.Class,
            snippet="${1:density}:\n  path: ${2:density}\n  baseline: ${3:20}\n"
                    "  n: ${4:40}\n  base: ${5:5}\n  range: ${6:10}",
            sort="3",
        ))
    elif ctx == "over":
        for dotted in _over_paths(m):
            if dotted not in present:
                items.append(_item(dotted, "", types.CompletionItemKind.Reference,
                                   snippet=dotted + ":\n  ", sort="2"))
    elif ctx == "streams":
        items.append(_item(
            "ventaglio",
            "Snippet: entry-spread che genera n stream.",
            types.CompletionItemKind.Class,
            snippet="${1:ventaglio}:\n  spread:\n    n: ${2:8}\n    over:\n"
                    "      ${3:base.onset}:\n        ramp: {start: ${4:0}, step: ${5:2}}",
            sort="3",
        ))
    return items


def _over_paths(m: StudyModel) -> List[str]:
    out: List[str] = []
    for dotted in EI.AXIS_PATHS:
        out.append("base." + dotted)
    for name in m.axes:
        out += [f"axes.{name}.baseline", f"axes.{name}.base", f"axes.{name}.range",
                f"axes.{name}.n", f"axes.{name}.seed"]
    for name in m.walks:
        out += [f"stack.{name}.seed", f"stack.{name}.base", f"stack.{name}.range"]
    return out


def _complete_value(doc: yamlpos.Document, m: StudyModel, path: Tuple[str, ...],
                    key: str, file_dir: Optional[str]) -> List[types.CompletionItem]:
    ctx = schema.context_for_path(path)
    k = schema.key_in(ctx, key)
    items: List[types.CompletionItem] = []
    if k and k.values:
        for v in k.values:
            doc_md = EI.WINDOWS.get(v, "") if key == "envelope" else ""
            if key == "unit" and v in EI.X_UNITS:
                doc_md = EI.X_UNITS[v]
            if key == "path" and v in EI.PARAMS:
                info = EI.PARAMS[v]
                doc_md = f"{info.doc} — bounds [{_b(info.min)}, {_b(info.max)}] {info.unit}"
            items.append(_item(v, doc_md, types.CompletionItemKind.EnumMember, sort="1"))
    if key == "sample":
        samples_dir = doc.get(("samples_dir",), "samples") or "samples"
        for f in _samples(file_dir, str(samples_dir)):
            items.append(_item(f, "", types.CompletionItemKind.File, sort="1"))
    return items


def _b(v: Optional[float]) -> str:
    return "∞" if v is None else f"{v:g}"


def _complete_item(m: StudyModel, path: Tuple[str, ...]) -> List[types.CompletionItem]:
    # item di lista: orderings -> nomi d'asse
    if path and path[-1] == "orderings":
        return [
            _item(f"[{', '.join(m.axes)}]", "Permutazione completa degli assi.",
                  types.CompletionItemKind.Value, sort="1")
        ] + [_item(name, "", types.CompletionItemKind.Class, sort="2") for name in m.axes]
    if path and path[-1] == "orders":
        return [_item(str(i), f"Ordine {i}: {'un asse alla volta' if i == 1 else f'{i}-uple di assi'}.",
                      types.CompletionItemKind.Value, sort="1")
                for i in range(1, max(2, len(m.axes) + 1))]
    return []
