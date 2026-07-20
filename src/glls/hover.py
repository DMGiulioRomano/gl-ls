"""Hover: documentazione della chiave + arricchimenti dinamici.

Oltre alla doc dello schema, l'hover porta il sapere del dominio dove serve:
bounds engine sul valore, zona percettiva della density, conversioni
hz/s/bpm sui valori della camminata-X, tempi normalizzati resi in secondi,
riepilogo di un asse (generatore, n, camminata, unit risolta).
"""
from __future__ import annotations

from typing import Any, List, Optional

from lsprotocol import types

from . import engine_info as EI
from . import schema
from .convert import as_num as _num, fmt_num
from .model import (AXES_RESERVED, STACK_RESERVED, StudyModel, split_over_key,
                    split_spread_over_key)
from .yamlpos import Document, KeyPath


def _md(value: str, rng: Optional[types.Range] = None) -> types.Hover:
    return types.Hover(
        contents=types.MarkupContent(kind=types.MarkupKind.Markdown, value=value),
        range=rng,
    )



def _bounds_line(dotted: str) -> str:
    info = EI.PARAMS.get(dotted)
    if not info:
        return ""
    hi = "∞" if info.max is None else f"{info.max:g}"
    dflt = "—" if info.default is None else f"{info.default:g}"
    return (f"\n\n`{dotted}` — bounds **[{info.min:g}, {hi}]** {info.unit} · "
            f"default {dflt}")


def _axis_summary(m: StudyModel, name: str) -> str:
    ax = m.axes.get(name)
    if ax is None:
        return ""
    origin = "" if ax.explicit_path else " *(path derivato dalla chiave)*"
    parts: List[str] = [f"**Asse `{name}`** → `{ax.path or '?'}`{origin}"]
    gen = {"values": "lista esplicita", "ramp": "rampa",
           "band": "banda [base, base+range]"}.get(ax.generator or "", "nessun generatore")
    n = f"n={ax.n}" if ax.n else ("n dalla camminata-X" if ax.defers_n else "n=?")
    parts.append(f"Y: {gen} · {n} · interpolation `{ax.interpolation}`")
    walk = m.walk_for(name)
    if walk is not None:
        parts.append(f"X: camminata in `{walk.unit}` (la X possiede n)")
    else:
        parts.append("X: linear (tempi equispaziati, la Y possiede n)")
    if ax.path:
        parts.append(_bounds_line(ax.path).strip())
    return "\n\n".join(p for p in parts if p)


def _unit_conversions(v: float, unit: str) -> str:
    outs = []
    for dst in ("hz", "s", "bpm"):
        if dst == unit:
            continue
        try:
            outs.append(f"{fmt_num(EI.unit_convert_value(v, unit, dst))} {dst}")
        except ZeroDivisionError:
            continue
    return f"**{fmt_num(v)} {unit}** ≈ " + " ≈ ".join(outs)


def hover(doc: Document, m: StudyModel, line: int, character: int) -> Optional[types.Hover]:
    path, where = doc.path_at(line, character)
    if not path:
        return None
    entry = doc.entry(path)
    rng = None
    if entry is not None:
        span = entry.key_span if where == "key" and entry.key_span else entry.value_span
        rng = types.Range(
            start=types.Position(span.start_line, span.start_col),
            end=types.Position(span.end_line, span.end_col),
        )

    if where == "key":
        return _hover_key(doc, m, path, rng)
    return _hover_value(doc, m, path, rng)


def _hover_over_key(doc: Document, path: KeyPath, dotted: str,
                    rng: Optional[types.Range],
                    intro: str = "") -> Optional[types.Hover]:
    """Hover di una entry di ``over``: chiave del contesto annidato oppure
    resto di una dotted ``over.<path>`` al primo livello di ``spread:``."""
    split = split_over_key(dotted, doc.get(path))
    if split is not None:
        head, marker = split
        mk = schema.key_in("spread_strategy", marker)
        text = (f"{intro}path `{head}` + strategy `{marker}` "
                f"(equivale a `{head}:` con `{marker}:` annidato).")
        if not intro:
            text = "Chiave puntata: " + text
        if mk is not None:
            text += f"\n\n**`{marker}`** — {mk.doc}"
        info = EI.PARAMS.get(head[5:]) if head.startswith("base.") else None
        return _md(text + (_bounds_line(head[5:]) if info else ""), rng)
    info = EI.PARAMS.get(dotted[5:]) if dotted.startswith("base.") else None
    base = (f"{intro}i valori della strategy finiscono in `{dotted}` di ogni "
            "stream generato." if intro else
            f"Path puntato nel documento: i valori della strategy finiscono "
            f"in `{dotted}` di ogni stream generato.")
    return _md(base + (_bounds_line(dotted[5:]) if info else ""), rng)


def _hover_key(doc: Document, m: StudyModel, path: KeyPath,
               rng: Optional[types.Range]) -> Optional[types.Hover]:
    name = path[-1]
    parent = path[:-1]
    ctx = schema.context_for_path(parent, frozenset(m.axes))

    # nomi dinamici: assi e stream
    if ctx == "axes" and name not in AXES_RESERVED:
        return _md(_axis_summary(m, str(name)), rng)
    if ctx == "stack" and name not in STACK_RESERVED:
        summary = _axis_summary(m, str(name))
        walk = m.walk_for(str(name))
        extra = ""
        if walk is not None:
            extra = (f"\n\nCamminata-X: unit **{walk.unit}** — "
                     + EI.X_UNITS.get(walk.unit, ""))
        return _md((summary or f"Camminata-X per l'asse `{name}`.") + extra, rng)
    if ctx == "streams":
        si = m.streams.get(str(name))
        if si and si.is_spread:
            n = si.spread_n or "?"
            return _md(f"**Entry-spread `{name}`**: genera **{n}** stream "
                       f"(`{name}_1` … `{name}_{n}`), ascolto verticale "
                       "(sweep spento salvo blocco `sweep:` esplicito).", rng)
        return _md(f"Stream `{name}`: override parziale del documento "
                   "(deep-merge; le liste rimpiazzano).", rng)
    if ctx == "spread":
        rest = split_spread_over_key(name)
        if rest is not None:
            return _hover_over_key(doc, path, rest, rng,
                                   intro="Forma dotted di `over`: ")
    if ctx == "over":
        return _hover_over_key(doc, path, str(name), rng)

    k = schema.key_in(ctx, str(name))
    if k is None:
        return None
    text = f"**`{name}`** — {k.doc}"
    # arricchimenti
    if ctx in ("engine_stream", "grain", "pointer", "pitch", "voices"):
        dotted = _dotted_engine_path(path)
        if dotted:
            text += _bounds_line(dotted)
    if str(name) == "unit" and ctx == "walk" and len(path) >= 2:
        walk = m.walk_for(str(path[-2]))
        if walk:
            text += f"\n\nUnit risolta per quest'asse: **{walk.unit}**"
    if str(name) == "duration" and ctx == "root":
        text += ("\n\nCode action disponibile dopo una modifica: *riscala i "
                 "breakpoint assoluti degli envelope al nuovo valore*.")
    return _md(text, rng)


def _dotted_engine_path(path: KeyPath) -> Optional[str]:
    """Path engine dotted da un key-path sotto base (o streams.*.base)."""
    parts = list(path)
    while parts and parts[0] in ("streams",):
        parts = parts[2:]
    if not parts or parts[0] != "base":
        return None
    dotted = ".".join(str(p) for p in parts[1:] if isinstance(p, str))
    return dotted if dotted in EI.PARAMS else None


def _hover_value(doc: Document, m: StudyModel, path: KeyPath,
                 rng: Optional[types.Range]) -> Optional[types.Hover]:
    value = doc.get(path)
    parent_key = path[-1] if path and isinstance(path[-1], str) else None
    n = _num(value)

    # valori della camminata-X: conversioni di unita'
    walk_axis = _walk_axis_of(path)
    if walk_axis and n is not None and n > 0:
        walk = m.walk_for(walk_axis)
        unit = walk.unit if walk else "hz"
        text = _unit_conversions(n, unit)
        if unit in ("hz", "bpm"):
            text += f"\n\nPasso medio tra breakpoint: ~{fmt_num(EI.unit_convert_value(n, unit, 's'))} s"
        return _md(text, rng)

    # enum documentati
    if isinstance(value, str):
        if value in EI.WINDOWS and parent_key in ("envelope", "from", "to"):
            return _md(f"**{value}** — {EI.WINDOWS[value]}", rng)
        if value in EI.X_UNITS and parent_key == "unit":
            return _md(f"**{value}** — {EI.X_UNITS[value]}", rng)
        if parent_key == "path" and value in EI.PARAMS:
            return _md(f"`{value}` — {EI.PARAMS[value].doc}{_bounds_line(value)}", rng)

    # density: zona percettiva
    if n is not None and _is_density_value(m, path):
        return _md(f"**density {fmt_num(n)} g/s** — {EI.density_zone(n)}"
                   + _bounds_line("density"), rng)

    # tempo normalizzato -> secondi
    if n is not None and 0 <= n <= 1 and _is_env_time(doc, path):
        dur = m.duration or m.base_duration
        if dur:
            return _md(f"t = **{fmt_num(n)}** → {fmt_num(n * dur)} s "
                       f"(su duration {fmt_num(dur)} s)", rng)

    # valore di un parametro engine noto
    dotted = _dotted_engine_path(path[:-1] if isinstance(path[-1], int) else path)
    if dotted and n is not None:
        text = f"`{dotted}` = {fmt_num(n)}" + _bounds_line(dotted)
        if dotted == "density":
            text += f"\n\n{EI.density_zone(n)}"
        return _md(text, rng)
    return None


def _walk_axis_of(path: KeyPath) -> Optional[str]:
    """Nome dell'asse se il path vive dentro stack.<asse>.{base,range}."""
    parts = list(path)
    while parts and parts[0] == "streams":
        parts = parts[2:]
    if len(parts) >= 3 and parts[0] == "stack" and parts[1] not in STACK_RESERVED:
        if parts[2] in ("base", "range"):
            return str(parts[1])
    return None


def _is_density_value(m: StudyModel, path: KeyPath) -> bool:
    parts = list(path)
    while parts and parts[0] == "streams":
        parts = parts[2:]
    if len(parts) >= 2 and parts[0] == "axes":
        ax = m.axes.get(str(parts[1]))
        return bool(ax and ax.path == "density" and len(parts) > 2)
    return False


def _is_env_time(doc: Document, path: KeyPath) -> bool:
    """True se il valore e' il primo elemento di un breakpoint [t, v]."""
    if not path or not isinstance(path[-1], int) or path[-1] != 0:
        return False
    pair = doc.get(path[:-1])
    return (isinstance(pair, (list, tuple)) and len(pair) in (2, 3)
            and all(_num(x) is not None for x in pair[:2]))
