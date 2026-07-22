"""Parsing YAML con posizioni: dati + tabella ``{key-path -> span}``.

``yaml.safe_load`` scarta i mark; qui il documento viene composto anche come
albero di nodi (``yaml.compose``) e se ne ricava una tabella laterale
``{tupla di chiavi -> Entry}`` con gli span (0-based, stile LSP) di chiave e
valore. Gli indici di lista entrano nel path come interi. Le chiavi duplicate
in una mapping (safe_load tiene l'ultima, silenziosamente) vengono raccolte a
parte per la diagnostica, con lo span della ripetizione e quello della prima
occorrenza (a cui la diagnostica rimanda).

Su errore di sintassi il parse ritorna comunque un ``Document`` con
``syntax_error`` valorizzato e ``data=None``: le feature che possono lavorare
sul testo grezzo (completion) restano operative.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple

import yaml

KeyPath = Tuple[Any, ...]


@dataclass(frozen=True)
class Span:
    """Intervallo di testo 0-based (riga, colonna), convenzione LSP."""

    start_line: int
    start_col: int
    end_line: int
    end_col: int

    def contains(self, line: int, col: int) -> bool:
        if (line, col) < (self.start_line, self.start_col):
            return False
        return (line, col) <= (self.end_line, self.end_col)


def node_span(node: yaml.Node) -> Span:
    return Span(
        node.start_mark.line,
        node.start_mark.column,
        node.end_mark.line,
        node.end_mark.column,
    )


@dataclass(frozen=True)
class Entry:
    """Un nodo del documento: chiave (se figlia di mapping) e valore."""

    path: KeyPath
    key_span: Optional[Span]  # None per gli item di lista e per la radice
    value_span: Span
    kind: str  # "mapping" | "sequence" | "scalar"
    scalar_raw: Optional[str] = None  # testo grezzo per gli scalari


@dataclass(frozen=True)
class SyntaxIssue:
    message: str
    span: Span


@dataclass
class Document:
    """Il risultato del parse: dati, posizioni, problemi."""

    text: str
    data: Any = None
    entries: Dict[KeyPath, Entry] = field(default_factory=dict)
    # (key-path, span della ripetizione, span della prima occorrenza)
    duplicates: List[Tuple[KeyPath, Span, Span]] = field(default_factory=list)
    syntax_error: Optional[SyntaxIssue] = None

    # ------------------------------------------------------------------
    def get(self, path: KeyPath, default: Any = None) -> Any:
        """Naviga ``data`` lungo ``path`` (chiavi str, indici int)."""
        cur = self.data
        for part in path:
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            elif isinstance(cur, (list, tuple)) and isinstance(part, int) and 0 <= part < len(cur):
                cur = cur[part]
            else:
                return default
        return cur

    def entry(self, path: KeyPath) -> Optional[Entry]:
        return self.entries.get(tuple(path))

    def iter_entries(self) -> Iterator[Entry]:
        return iter(self.entries.values())

    # ------------------------------------------------------------------
    def path_at(self, line: int, col: int) -> Tuple[KeyPath, str]:
        """(path, dove) del nodo piu' profondo che contiene la posizione.

        ``dove`` e' ``"key"`` se la posizione cade sulla chiave, ``"value"``
        se cade nel valore, ``""`` se fuori da tutto (path radice).
        """
        best: Tuple[KeyPath, str] = ((), "")
        best_depth = -1
        for e in self.entries.values():
            if e.key_span is not None and e.key_span.contains(line, col):
                if len(e.path) > best_depth:
                    best, best_depth = (e.path, "key"), len(e.path)
        if best_depth >= 0:
            return best
        for e in self.entries.values():
            if e.value_span.contains(line, col) and e.kind == "scalar":
                if len(e.path) > best_depth:
                    best, best_depth = (e.path, "value"), len(e.path)
        if best_depth >= 0:
            return best
        # fallback: container piu' profondo che contiene la posizione
        for e in self.entries.values():
            if e.value_span.contains(line, col):
                if len(e.path) > best_depth:
                    best, best_depth = (e.path, "value"), len(e.path)
        return best


def _walk(node: yaml.Node, path: KeyPath, doc: Document) -> None:
    if isinstance(node, yaml.MappingNode):
        # prima occorrenza di ogni chiave (per rimandare la diagnostica alla
        # riga originale); le ripetizioni successive puntano sempre a questa
        first_seen: Dict[str, Span] = {}
        for key_node, value_node in node.value:
            key = getattr(key_node, "value", None)
            if not isinstance(key, str):
                continue
            kspan = node_span(key_node)
            if key in first_seen:
                doc.duplicates.append((path + (key,), kspan, first_seen[key]))
            else:
                first_seen[key] = kspan
            child = path + (key,)
            doc.entries[child] = Entry(
                path=child,
                key_span=kspan,
                value_span=node_span(value_node),
                kind=_kind(value_node),
                scalar_raw=value_node.value if isinstance(value_node, yaml.ScalarNode) else None,
            )
            _walk(value_node, child, doc)
    elif isinstance(node, yaml.SequenceNode):
        for i, item in enumerate(node.value):
            child = path + (i,)
            doc.entries[child] = Entry(
                path=child,
                key_span=None,
                value_span=node_span(item),
                kind=_kind(item),
                scalar_raw=item.value if isinstance(item, yaml.ScalarNode) else None,
            )
            _walk(item, child, doc)


def _kind(node: yaml.Node) -> str:
    if isinstance(node, yaml.MappingNode):
        return "mapping"
    if isinstance(node, yaml.SequenceNode):
        return "sequence"
    return "scalar"


def parse(text: str) -> Document:
    """Parse tollerante: dati + posizioni, o ``syntax_error`` valorizzato."""
    doc = Document(text=text)
    try:
        doc.data = yaml.safe_load(text)
        node = yaml.compose(text, Loader=yaml.SafeLoader)
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark or exc.context_mark
        line = mark.line if mark else 0
        col = mark.column if mark else 0
        msg = (exc.problem or exc.context or "errore di sintassi YAML").strip()
        doc.data = None
        doc.syntax_error = SyntaxIssue(
            message=f"Sintassi YAML: {msg}",
            span=Span(line, col, line, col + 1),
        )
        return doc
    except yaml.YAMLError as exc:  # pragma: no cover - errori senza mark
        doc.data = None
        doc.syntax_error = SyntaxIssue(
            message=f"Sintassi YAML: {exc}", span=Span(0, 0, 0, 1)
        )
        return doc
    if node is not None:
        root = Entry(path=(), key_span=None, value_span=node_span(node), kind=_kind(node))
        doc.entries[()] = root
        _walk(node, (), doc)
    return doc
