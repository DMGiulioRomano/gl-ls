"""Code action: i ricalcoli che altrimenti si fanno a mano con la calcolatrice.

- **Conversione unita' della camminata-X** (`stack.<asse>`): hz <-> s <-> bpm
  con ricalcolo di ``base``/``range`` nello spazio di destinazione (il
  passaggio rate<->periodo inverte i bordi della banda).
- **Riscala al cambio di duration**: quando ``duration:`` (o ``base.duration``)
  cambia, i breakpoint a tempi assoluti negli envelope di ``base.*`` vengono
  riscalati del fattore nuovo/vecchio (i normalized si riscalano da soli).
- **Conversione time_mode** absolute <-> normalized con ricalcolo dei tempi.
- **Quick fix** dalle diagnostiche (rename, rimozioni, migrazione rand:/cps:).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from lsprotocol import types

from . import engine_info as EI
from .convert import ConversionError, convert_band, fmt_num, yaml_flow
from .model import STACK_RESERVED, StudyModel
from .yamlpos import Document, Entry, KeyPath, Span


def _pos(line: int, col: int) -> types.Position:
    return types.Position(line, col)


def _edit(span: Span, new_text: str) -> types.TextEdit:
    return types.TextEdit(
        range=types.Range(start=_pos(span.start_line, span.start_col),
                          end=_pos(span.end_line, span.end_col)),
        new_text=new_text,
    )


def _insert(line: int, col: int, text: str) -> types.TextEdit:
    return types.TextEdit(
        range=types.Range(start=_pos(line, col), end=_pos(line, col)),
        new_text=text,
    )


def _block_end(entry: Entry) -> Tuple[int, int]:
    """Fine "sicura" di un blocco: i mark YAML di fine di una collezione block
    puntano spesso alla colonna 0 della riga del token successivo."""
    s = entry.value_span
    if s.end_col == 0 and s.end_line > s.start_line:
        return s.end_line, 0
    return s.end_line + 1, 0


def _action(title: str, uri: str, edits: List[types.TextEdit],
            kind: types.CodeActionKind,
            diagnostics: Optional[List[types.Diagnostic]] = None
            ) -> types.CodeAction:
    return types.CodeAction(
        title=title, kind=kind,
        edit=types.WorkspaceEdit(changes={uri: edits}),
        diagnostics=diagnostics or None,
    )


def _intersects(span: Span, rng: types.Range) -> bool:
    return not (
        span.end_line < rng.start.line
        or span.start_line > rng.end.line
    )


# ---------------------------------------------------------------------------
# Conversione unita' della camminata-X


def unit_actions(doc: Document, m: StudyModel, uri: str,
                 rng: types.Range) -> List[types.CodeAction]:
    out: List[types.CodeAction] = []
    for name, walk in m.walks.items():
        entry = doc.entry(("stack", name))
        if entry is None:
            continue
        key_span = entry.key_span or entry.value_span
        whole = Span(key_span.start_line, key_span.start_col,
                     entry.value_span.end_line, entry.value_span.end_col)
        if not _intersects(whole, rng):
            continue
        for dst in sorted(EI.X_UNITS):
            if dst == walk.unit:
                continue
            edits = _convert_walk_edits(doc, ("stack", name), walk.cfg,
                                        walk.unit, dst)
            if edits is None:
                continue
            out.append(_action(
                f"gl-ls: converti la camminata '{name}' in unit: {dst} "
                f"(ricalcola base/range da {walk.unit})",
                uri, edits, types.CodeActionKind.RefactorRewrite,
            ))
    return out


def _convert_walk_edits(doc: Document, epath: KeyPath, cfg: Dict[str, Any],
                        src: str, dst: str) -> Optional[List[types.TextEdit]]:
    try:
        new_base, new_range = convert_band(cfg.get("base"), cfg.get("range"),
                                           src, dst)
    except ConversionError:
        return None
    edits: List[types.TextEdit] = []
    base_entry = doc.entry(epath + ("base",))
    if base_entry is None:
        return None
    edits.append(_edit(base_entry.value_span, yaml_flow(new_base)))

    range_entry = doc.entry(epath + ("range",))
    if range_entry is not None and new_range is not None:
        edits.append(_edit(range_entry.value_span, yaml_flow(new_range)))
    elif range_entry is None and new_range is not None:
        indent = " " * (base_entry.key_span.start_col if base_entry.key_span else 0)
        edits.append(_insert(base_entry.value_span.end_line + 1, 0,
                             f"{indent}range: {yaml_flow(new_range)}\n"))

    unit_entry = doc.entry(epath + ("unit",))
    if unit_entry is not None:
        edits.append(_edit(unit_entry.value_span, dst))
    else:
        indent = " " * (base_entry.key_span.start_col if base_entry.key_span else 0)
        line = base_entry.key_span.start_line if base_entry.key_span else base_entry.value_span.start_line
        edits.append(_insert(line, 0, f"{indent}unit: {dst}\n"))
    return edits


# ---------------------------------------------------------------------------
# Riscala al cambio di duration


def _envelope_time_edits(doc: Document, root: KeyPath, factor: float,
                         stream_time_mode: str,
                         include_normalized: bool = False) -> List[types.TextEdit]:
    """TextEdit che riscalano i tempi X degli envelope sotto ``root``.

    Considera: liste di breakpoint ``[t, v]``/``[t, v, type]``, dict con
    ``points`` (rispettando il ``time_mode`` locale), ``end_time`` dei blocchi
    compatti nelle liste miste. ``include_normalized`` serve alla conversione
    absolute<->normalized (che riscala anche i normalized).
    """
    edits: List[types.TextEdit] = []
    skip_words = ("envelope", "let", "values")
    for entry in doc.iter_entries():
        path = entry.path
        if len(path) <= len(root) or path[:len(root)] != tuple(root):
            continue
        rel = path[len(root):]
        if any(isinstance(p, str) and p in skip_words for p in rel):
            continue
        value = doc.get(path)
        if not isinstance(value, list) or not value:
            continue
        local_mode = stream_time_mode
        parent = doc.get(path[:-1])
        if isinstance(path[-1], str) and path[-1] == "points" and isinstance(parent, dict):
            lm = parent.get("time_mode") or parent.get("time_unit")
            if lm in ("absolute", "normalized"):
                local_mode = lm
        elif isinstance(path[-1], str):
            # envelope in forma lista diretta: vale il time_mode dello stream
            pass
        else:
            continue  # gli elementi interni li gestiamo dal padre
        if local_mode == "normalized" and not include_normalized:
            continue
        edits.extend(_scale_env_list(doc, path, value, factor))
    return edits


def _scale_env_list(doc: Document, path: KeyPath, value: list,
                    factor: float) -> List[types.TextEdit]:
    edits: List[types.TextEdit] = []
    for i, item in enumerate(value):
        if not isinstance(item, list) or not item:
            continue
        # breakpoint [t, v] o [t, v, type]
        if len(item) in (2, 3) and _num(item[0]) is not None and _num(item[1]) is not None:
            t_entry = doc.entry(path + (i, 0))
            if t_entry is not None:
                edits.append(_edit(t_entry.value_span,
                                   fmt_num(_num(item[0]) * factor)))
        # blocco compatto [pattern, end_time, n_reps, ...]
        elif (len(item) >= 3 and isinstance(item[0], list)
              and _num(item[1]) is not None and isinstance(item[2], int)):
            et_entry = doc.entry(path + (i, 1))
            if et_entry is not None:
                edits.append(_edit(et_entry.value_span,
                                   fmt_num(_num(item[1]) * factor)))
    return edits


def _num(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def duration_actions(doc: Document, m: StudyModel, uri: str, rng: types.Range,
                     pending: Dict[str, Tuple[float, float]]
                     ) -> List[types.CodeAction]:
    """Riscala i tempi assoluti quando duration e' cambiata (memoria server)."""
    out: List[types.CodeAction] = []
    for key, (old, new) in pending.items():
        if old <= 0 or new <= 0 or old == new:
            continue
        dpath: KeyPath = ("duration",) if key == "duration" else ("base", "duration")
        entry = doc.entry(dpath)
        if entry is None:
            continue
        span = Span(
            (entry.key_span or entry.value_span).start_line, 0,
            entry.value_span.end_line, entry.value_span.end_col,
        )
        if not _intersects(span, rng):
            continue
        factor = new / old
        edits: List[types.TextEdit] = []
        for base_root in _base_roots(doc):
            edits.extend(_envelope_time_edits(doc, base_root, factor,
                                              m.time_mode))
        if not edits:
            continue
        out.append(_action(
            f"gl-ls: riscala i breakpoint assoluti degli envelope "
            f"({fmt_num(old)}s → {fmt_num(new)}s, ×{fmt_num(round(factor, 6))})",
            uri, edits, types.CodeActionKind.RefactorRewrite,
        ))
    return out


def _base_roots(doc: Document) -> List[KeyPath]:
    roots: List[KeyPath] = []
    if isinstance(doc.get(("base",)), dict):
        roots.append(("base",))
    streams = doc.get(("streams",))
    if isinstance(streams, dict):
        for name, cfg in streams.items():
            if isinstance(cfg, dict) and isinstance(cfg.get("base"), dict):
                roots.append(("streams", name, "base"))
    return roots


# ---------------------------------------------------------------------------
# Conversione time_mode absolute <-> normalized


def time_mode_actions(doc: Document, m: StudyModel, uri: str,
                      rng: types.Range) -> List[types.CodeAction]:
    out: List[types.CodeAction] = []
    base_entry = doc.entry(("base",))
    if base_entry is None:
        return out
    dur = m.base_duration or m.duration
    if not dur or dur <= 0:
        return out
    tm_entry = doc.entry(("base", "time_mode"))
    anchor = tm_entry or doc.entry(("base", "duration"))
    if anchor is None:
        return out
    span = anchor.key_span or anchor.value_span
    if not _intersects(Span(span.start_line, 0, anchor.value_span.end_line,
                            anchor.value_span.end_col), rng):
        return out

    if m.time_mode == "absolute":
        dst, factor = "normalized", 1.0 / dur
    else:
        dst, factor = "absolute", dur
    edits = _envelope_time_edits(doc, ("base",), factor, m.time_mode,
                                 include_normalized=(m.time_mode == "normalized"))
    if tm_entry is not None:
        edits.append(_edit(tm_entry.value_span, dst))
    else:
        indent = " " * (base_entry.key_span.start_col + 2 if base_entry.key_span else 2)
        line = (base_entry.key_span.start_line if base_entry.key_span
                else base_entry.value_span.start_line) + 1
        edits.append(_insert(line, 0, f"{indent}time_mode: {dst}\n"))
    if not edits:
        return out
    out.append(_action(
        f"gl-ls: converti gli envelope di base a time_mode: {dst} "
        f"(ricalcola i tempi su duration {fmt_num(dur)}s)",
        uri, edits, types.CodeActionKind.RefactorRewrite,
    ))
    return out


# ---------------------------------------------------------------------------
# Quick fix dalle diagnostiche


def quickfixes(doc: Document, uri: str,
               diagnostics: List[types.Diagnostic]) -> List[types.CodeAction]:
    out: List[types.CodeAction] = []
    for diag in diagnostics:
        data = diag.data if isinstance(diag.data, dict) else None
        fix = data.get("fix") if data else None
        if not isinstance(fix, dict):
            continue
        kind = fix.get("kind")
        if kind == "rename" and fix.get("new"):
            out.append(_action(f"Rinomina in '{fix['new']}'", uri,
                               [types.TextEdit(range=diag.range, new_text=str(fix["new"]))],
                               types.CodeActionKind.QuickFix, [diag]))
        elif kind == "rename-value" and fix.get("new"):
            out.append(_action(f"Sostituisci con '{fix['new']}'", uri,
                               [types.TextEdit(range=diag.range, new_text=str(fix["new"]))],
                               types.CodeActionKind.QuickFix, [diag]))
        elif kind == "clear-value":
            out.append(_action("Rendi la chiave presente-vuota", uri,
                               [types.TextEdit(range=diag.range, new_text="")],
                               types.CodeActionKind.QuickFix, [diag]))
        elif kind == "remove-key":
            path = tuple(fix.get("path") or ())
            entry = doc.entry(path)
            if entry is None:
                continue
            start_line = (entry.key_span or entry.value_span).start_line
            end_line, end_col = _block_end(entry)
            out.append(_action(
                f"Rimuovi '{path[-1]}'", uri,
                [types.TextEdit(
                    range=types.Range(start=_pos(start_line, 0),
                                      end=_pos(end_line, end_col)),
                    new_text="")],
                types.CodeActionKind.QuickFix, [diag]))
        elif kind == "flatten-wrapper":
            path = tuple(fix.get("path") or ())
            action = _flatten_wrapper_action(doc, uri, path, diag)
            if action:
                out.append(action)
        elif kind == "add-n":
            path = tuple(fix.get("path") or ())
            action = _insert_first_key(doc, uri, path, "n: 8",
                                       "Aggiungi 'n' alla banda", diag)
            if action:
                out.append(action)
        elif kind == "add-baseline":
            path = tuple(fix.get("path") or ())
            action = _insert_first_key(doc, uri, path, "baseline: 0",
                                       "Aggiungi 'baseline'", diag)
            if action:
                out.append(action)
        elif kind == "add-duration":
            first = doc.entry(("study_id",))
            line = (first.value_span.end_line + 1) if first else 0
            out.append(_action("Aggiungi 'duration:' top-level", uri,
                               [_insert(line, 0, "duration: 30\n")],
                               types.CodeActionKind.QuickFix, [diag]))
    return out


def _insert_first_key(doc: Document, uri: str, path: KeyPath, text: str,
                      title: str, diag: types.Diagnostic
                      ) -> Optional[types.CodeAction]:
    entry = doc.entry(path)
    if entry is None:
        return None
    value = doc.get(path)
    if isinstance(value, dict) and value:
        first_child = doc.entry(path + (next(iter(value)),))
        if first_child is not None and first_child.key_span is not None:
            ks = first_child.key_span
            return _action(title, uri,
                           [_insert(ks.start_line, 0,
                                    " " * ks.start_col + text + "\n")],
                           types.CodeActionKind.QuickFix, [diag])
    return None


def _flatten_wrapper_action(doc: Document, uri: str, path: KeyPath,
                            diag: types.Diagnostic) -> Optional[types.CodeAction]:
    cfg = doc.get(path)
    entry = doc.entry(path)
    if not isinstance(cfg, dict) or entry is None or entry.key_span is None:
        return None
    inner: Any = cfg.get("rand", cfg.get("cps"))
    if isinstance(inner, dict) and "cps" in inner:
        inner = inner["cps"]
    if not isinstance(inner, dict):
        return None
    merged = {k: v for k, v in cfg.items() if k not in ("rand", "cps")}
    for k, v in inner.items():
        merged.setdefault(k, v)
    indent = " " * (entry.key_span.start_col + 2)
    lines = []
    for k, v in merged.items():
        if isinstance(v, dict):
            return None  # annidamenti ulteriori: meglio a mano
        lines.append(f"{indent}{k}: {yaml_flow(v)}")
    new_text = "\n" + "\n".join(lines) + "\n"
    end_line, end_col = _block_end(entry)
    return _action(
        "Migra al modello piatto (base/range diretti)", uri,
        [types.TextEdit(
            range=types.Range(start=_pos(entry.key_span.start_line,
                                         entry.key_span.end_col + 1),
                              end=_pos(end_line, end_col)),
            new_text=new_text)],
        types.CodeActionKind.QuickFix, [diag])


# ---------------------------------------------------------------------------


def collect(doc: Document, m: StudyModel, uri: str, rng: types.Range,
            diagnostics: List[types.Diagnostic],
            pending_durations: Dict[str, Tuple[float, float]]
            ) -> List[types.CodeAction]:
    out: List[types.CodeAction] = []
    if doc.data is None:
        return out
    out.extend(quickfixes(doc, uri, diagnostics))
    out.extend(unit_actions(doc, m, uri, rng))
    out.extend(duration_actions(doc, m, uri, rng, pending_durations))
    out.extend(time_mode_actions(doc, m, uri, rng))
    return out
