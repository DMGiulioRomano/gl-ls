"""Diagnostica di ``study.yml``: le regole di granstudies + engine, a editor.

Ogni check rispecchia una regola reale del runtime (``study_spec``,
``value_generators``, ``x_strategies``, bounds engine): l'obiettivo e' vedere
nell'editor lo stesso errore che darebbe ``make sweep``/``make stack``, prima
di lanciarlo. I quick fix viaggiano nel campo ``data`` della diagnostica e
vengono materializzati da ``actions.py``.
"""
from __future__ import annotations

import difflib
from typing import Any, Dict, List, Optional, Sequence, Tuple

from lsprotocol import types

from . import engine_info as EI
from .convert import as_num as _num
from . import exprlang, schema
from .model import (
    AXES_RESERVED,
    GEN_MARKERS,
    STACK_RESERVED,
    StudyModel,
    expand_over,
    ramp_count,
)
from .yamlpos import Document, KeyPath, Span

SOURCE = "gl-ls"

_WALK_ALLOWED = frozenset({"base", "range", "seed", "unit", "distribution", "drift"})
_SPREAD_MARKERS = ("values", "ramp", "base", "expr")
MAX_WALK_POINTS = 10_000


def _rng(span: Span) -> types.Range:
    return types.Range(
        start=types.Position(line=span.start_line, character=span.start_col),
        end=types.Position(line=span.end_line, character=span.end_col),
    )


def _range_for(doc: Document, path: KeyPath, prefer_value: bool = False) -> types.Range:
    e = doc.entry(path)
    if e is None:
        return types.Range(start=types.Position(0, 0), end=types.Position(0, 1))
    if prefer_value or e.key_span is None:
        return _rng(e.value_span)
    return _rng(e.key_span)


def _suggest(name: str, options: Sequence[str]) -> Optional[str]:
    close = difflib.get_close_matches(name, options, n=1, cutoff=0.6)
    return close[0] if close else None


class Bag:
    def __init__(self, doc: Document):
        self.doc = doc
        self.items: List[types.Diagnostic] = []

    def add(
        self,
        path: KeyPath,
        message: str,
        severity: types.DiagnosticSeverity = types.DiagnosticSeverity.Error,
        code: str = "",
        data: Optional[dict] = None,
        prefer_value: bool = False,
        span: Optional[Span] = None,
    ) -> None:
        rng = _rng(span) if span else _range_for(self.doc, path, prefer_value)
        self.items.append(
            types.Diagnostic(
                range=rng,
                message=message,
                severity=severity,
                source=SOURCE,
                code=code or None,
                data=data,
            )
        )


# ---------------------------------------------------------------------------


def collect(doc: Document, m: StudyModel) -> List[types.Diagnostic]:
    bag = Bag(doc)
    if doc.syntax_error is not None:
        bag.add((), doc.syntax_error.message, span=doc.syntax_error.span,
                code="yaml-syntax")
        return bag.items
    if not isinstance(doc.data, dict):
        return bag.items

    for path, span in doc.duplicates:
        bag.add(path, f"Chiave duplicata '{path[-1]}': YAML tiene solo l'ultima.",
                types.DiagnosticSeverity.Warning, code="duplicate-key", span=span)

    _check_root(bag, doc, m)
    _check_axes(bag, doc, m)
    _check_sweep(bag, doc, m, ("sweep",))
    _check_stack(bag, doc, m, ())
    _check_streams(bag, doc, m)
    _check_engine_block(bag, doc, m, ("base",))
    _check_unknown_keys(bag, doc)
    _check_expr_nodes(bag, doc, m)
    return bag.items


# ---------------------------------------------------------------------------


def _check_root(bag: Bag, doc: Document, m: StudyModel) -> None:
    if m.has_stack and m.duration is None:
        bag.add(("stack",),
                "stack: serve 'duration:' top-level (la durata condivisa su cui "
                "il processo normalizza i tempi).",
                code="stack-duration",
                data={"fix": {"kind": "add-duration"}})
    axes = doc.get(("axes",))
    if axes is None:
        bag.add(("study_id",) if doc.entry(("study_id",)) else (),
                "Lo studio deve definire almeno un asse in 'axes'.",
                types.DiagnosticSeverity.Warning, code="no-axes")



# Parametri che l'engine riscala da campioni a secondi (fattore 1/output_sr)
# quando ``grain.duration_unit: samples`` (``stream._pre_normalize_grain_params``).
_SAMPLES_SCALED = frozenset({"grain.duration", "grain.duration_range"})


def _samples_unit(doc: Document, bpath: KeyPath) -> bool:
    """True se il blocco engine ``bpath`` lavora in campioni: vale l'override
    per-stream se dichiarato, altrimenti l'unita' ereditata dal base root
    (semantica del deep-merge stream su documento)."""
    u = doc.get(bpath + ("grain", "duration_unit"))
    if u is None and bpath != ("base",):
        u = doc.get(("base", "grain", "duration_unit"))
    return u == "samples"


def _check_bounds_value(
    bag: Bag, path: KeyPath, engine_path: str, v: Any, label: str,
    in_samples: bool = False,
) -> None:
    b = EI.bounds_for(engine_path)
    n = _num(v)
    if b is None or n is None:
        return
    note = ""
    if in_samples and engine_path in _SAMPLES_SCALED:
        note = f" ({n:g} campioni a {EI.OUTPUT_SR} Hz)"
        n = n / EI.OUTPUT_SR
    lo, hi = b
    if (lo is not None and n < lo) or (hi is not None and n > hi):
        hi_s = "∞" if hi is None else f"{hi:g}"
        bag.add(path,
                f"{label}: {n:g}{note} fuori bounds [{lo:g}, {hi_s}] "
                f"per '{engine_path}'.",
                code="out-of-bounds", prefer_value=True)


def _check_axes(bag: Bag, doc: Document, m: StudyModel) -> None:
    axes = doc.get(("axes",))
    if not isinstance(axes, dict):
        if axes is not None:
            bag.add(("axes",), "'axes' deve essere un mapping di assi.",
                    code="axes-type")
        return
    interp = axes.get("interpolation")
    if interp is not None and interp not in EI.INTERPOLATIONS:
        bag.add(("axes", "interpolation"),
                f"interpolation '{interp}' non valida (linear | cubic | step).",
                code="bad-enum", prefer_value=True)
    for name, cfg in axes.items():
        if name in AXES_RESERVED:
            continue
        apath: KeyPath = ("axes", name)
        if not isinstance(cfg, dict):
            hint = ("'plateau'/'transition' vivono in 'sweep:', non in 'axes:'."
                    if name in ("plateau", "transition")
                    else "un asse e' un dict con 'path' e un generatore Y.")
            bag.add(apath, f"Asse '{name}': config non valida, serve un dict. {hint}",
                    code="axis-type")
            continue
        if "path" not in cfg:
            bag.add(apath,
                    f"Asse '{name}': manca 'path' (il parametro engine da muovere). "
                    "Es. 'path: density' o 'path: grain.duration'.",
                    code="axis-no-path")
        else:
            p = cfg.get("path")
            if (isinstance(p, str) and p not in EI.PARAMS
                    and p != "pitch" and not p.startswith("pitch.")):
                sug = _suggest(p, EI.AXIS_PATHS)
                extra = f" Forse intendevi '{sug}'?" if sug else ""
                bag.add(apath + ("path",),
                        f"path '{p}' non riconosciuto tra i parametri engine noti.{extra}",
                        types.DiagnosticSeverity.Warning, code="unknown-path",
                        prefer_value=True,
                        data={"fix": {"kind": "rename-value", "new": sug}} if sug else None)

        interp_ax = cfg.get("interpolation")
        if interp_ax is not None and interp_ax not in EI.INTERPOLATIONS:
            bag.add(apath + ("interpolation",),
                    f"interpolation '{interp_ax}' non valida (linear | cubic | step).",
                    code="bad-enum", prefer_value=True)

        markers = [g for g in GEN_MARKERS if g in cfg]
        if len(markers) > 1:
            for extra_marker in markers:
                bag.add(apath + (extra_marker,),
                        f"Asse '{name}': generatori multipli {markers} — esattamente "
                        "una chiave tra values | ramp | base (banda).",
                        code="multi-generator",
                        data={"fix": {"kind": "remove-key",
                                      "path": list(apath + (extra_marker,))}})
        elif not markers:
            bag.add(apath,
                    f"Asse '{name}' senza valori di test: dichiara 'values', 'ramp' "
                    "o una banda ('base'/'range'/'n').",
                    code="no-generator")

        walk = m.walk_for(name)
        if markers == ["base"]:
            _check_band(bag, doc, apath, cfg, f"Asse '{name}'")
            if "n" not in cfg and walk is None:
                bag.add(apath,
                        f"Asse '{name}': banda senza 'n' richiede la camminata-X "
                        f"nel blocco 'stack:' (n-ownership: e' la X a possedere n). "
                        f"Dichiara 'n' oppure 'stack: {{{name}: {{base: ...}}}}'.",
                        code="n-ownership",
                        data={"fix": {"kind": "add-n", "path": list(apath)}})
        elif markers and walk is not None:
            bag.add(("stack", name),
                    f"Asse '{name}': la camminata-X possiede n, ma il generatore Y "
                    f"'{markers[0]}' enumera i valori. Usa la banda senza 'n' su "
                    f"axes.{name}, oppure togli la camminata (stack.{name}).",
                    code="n-ownership")

        if markers == ["ramp"]:
            _check_ramp(bag, apath + ("ramp",), cfg.get("ramp"), f"Asse '{name}'",
                        require_stop=True)

        # bounds su baseline e values espliciti; i valori di un asse atterrano
        # nel base root, quindi vale la sua duration_unit
        engine_path = cfg.get("path")
        if isinstance(engine_path, str):
            in_samples = _samples_unit(doc, ("base",))
            if "baseline" in cfg:
                _check_bounds_value(bag, apath + ("baseline",), engine_path,
                                    cfg.get("baseline"), f"Asse '{name}' baseline",
                                    in_samples=in_samples)
            elif EI.needs_baseline(engine_path):
                why = ("unit-driven (pitch)" if engine_path.startswith("pitch")
                       else "senza default engine")
                bag.add(apath,
                        f"Asse '{name}': path '{engine_path}' {why}, 'baseline' "
                        "e' obbligatorio.",
                        code="baseline-required",
                        data={"fix": {"kind": "add-baseline", "path": list(apath)}})
            vals = cfg.get("values")
            if isinstance(vals, list):
                for i, v in enumerate(vals):
                    _check_bounds_value(bag, apath + ("values", i), engine_path, v,
                                        f"Asse '{name}' values[{i}]",
                                        in_samples=in_samples)


def _check_band(bag: Bag, doc: Document, path: KeyPath, cfg: Dict[str, Any],
                label: str, locate=None) -> None:
    """``locate(*subkeys)`` mappa una sotto-chiave della banda alla sua
    posizione nel documento; il default e' ``path + subkeys`` (banda annidata
    canonica). Nello spread con chiavi puntate una banda vive su piu' righe
    (``.base``/``.range``/``.seed``): il locator punta ogni diagnostica alla
    riga giusta."""
    if locate is None:
        def locate(*ks: Any) -> KeyPath:
            return path + tuple(ks)
    n = cfg.get("n")
    if n is not None and (not isinstance(n, int) or isinstance(n, bool) or n < 1):
        bag.add(locate("n"), f"{label}: 'n' deve essere un intero >= 1.",
                code="bad-n", prefer_value=True)
    r = cfg.get("range")
    rn = _num(r)
    if rn is not None and rn < 0:
        bag.add(locate("range"),
                f"{label}: 'range' negativo ({rn:g}) — la banda e' "
                "[base, base+range], range >= 0.",
                code="negative-range", prefer_value=True)
    dist = cfg.get("distribution")
    if dist is not None and dist not in EI.DISTRIBUTIONS:
        bag.add(locate("distribution"),
                f"{label}: distribution '{dist}' non valida (uniform | gaussian).",
                code="bad-enum", prefer_value=True)
    drift = cfg.get("drift")
    if drift is not None:
        if not isinstance(drift, dict):
            bag.add(locate("drift"), f"{label}: 'drift' e' un dict {{step, seed?}}.",
                    code="drift-type")
        else:
            extra = set(drift) - {"step", "seed"}
            if extra:
                bag.add(locate("drift"),
                        f"{label}: drift, chiavi non ammesse {sorted(extra)} "
                        "(solo step/seed).",
                        code="drift-keys")
            st = _num(drift.get("step"))
            if st is not None and st < 0:
                bag.add(locate("drift", "step"),
                        f"{label}: drift.step negativo — 0 congela, > 0 cammina.",
                        code="drift-step", prefer_value=True)
    for border in ("base", "range"):
        _check_env_times(bag, locate(border), cfg.get(border), label)


def _check_env_times(bag: Bag, path: KeyPath, form: Any, label: str) -> None:
    """Nei breakpoint di banda i tempi vivono in [0, 1]."""
    pts = None
    if isinstance(form, list) and form and all(
        isinstance(p, (list, tuple)) and len(p) == 2 for p in form
    ):
        pts = form
    elif isinstance(form, dict) and isinstance(form.get("points"), list):
        pts = form.get("points")
        curve = form.get("curve")
        cn = _num(curve)
        if cn is not None and cn <= 0:
            bag.add(path + ("curve",), f"{label}: 'curve' deve essere > 0.",
                    code="bad-curve", prefer_value=True)
        if form.get("type") == "step" and cn is not None and cn != 1:
            bag.add(path + ("curve",),
                    f"{label}: con 'type: step' non c'e' rampa da piegare — "
                    "'curve' diverso da 1 e' un errore.",
                    code="curve-step", prefer_value=True)
    if not pts:
        return
    base_path = path if not isinstance(form, dict) else path + ("points",)
    for i, p in enumerate(pts):
        t = _num(p[0]) if isinstance(p, (list, tuple)) and len(p) == 2 else None
        if t is not None and not (0 <= t <= 1):
            bag.add(base_path + (i,),
                    f"{label}: breakpoint t={t:g} fuori da [0, 1] (i tempi di banda "
                    "sono normalizzati sulla sequenza).",
                    types.DiagnosticSeverity.Warning, code="band-time",
                    prefer_value=True)


def _check_ramp(bag: Bag, path: KeyPath, r: Any, label: str,
                require_stop: bool) -> None:
    if not isinstance(r, dict):
        bag.add(path, f"{label}: 'ramp' e' un dict {{start, stop, step}}.",
                code="ramp-type")
        return
    extra = set(r) - {"start", "stop", "step"}
    if extra:
        bag.add(path, f"{label}: ramp, chiavi non ammesse {sorted(extra)}.",
                code="ramp-keys")
    if "start" not in r:
        bag.add(path, f"{label}: ramp senza 'start'.", code="ramp-start")
    if require_stop and ("stop" not in r or "step" not in r):
        bag.add(path,
                f"{label}: la ramp di un asse richiede start, stop e step "
                "(le forme aperte valgono solo in spread).",
                code="ramp-incomplete")
    st = _num(r.get("step"))
    if st is not None and st <= 0:
        bag.add(path + ("step",),
                f"{label}: 'step' deve essere > 0 (la direzione la danno "
                "start/stop).",
                code="ramp-step", prefer_value=True)


def _check_sweep(bag: Bag, doc: Document, m: StudyModel, spath: KeyPath) -> None:
    sweep = doc.get(spath)
    if sweep is None:
        return
    if not isinstance(sweep, dict):
        bag.add(spath, "'sweep' deve essere un mapping.", code="sweep-type")
        return
    if "combine" in sweep:
        bag.add(spath + ("combine",),
                "sweep.combine non esiste piu': lo sweep fa solo il prodotto "
                "cartesiano. L'accoppiamento degli assi (ex parallel) vive nel "
                "processo stack — stessa strategy-X e stesso n.",
                code="sweep-combine",
                data={"fix": {"kind": "remove-key", "path": list(spath + ("combine",))}})
    mode = sweep.get("mode")
    if mode is not None and mode not in EI.SWEEP_MODES:
        bag.add(spath + ("mode",),
                f"mode '{mode}' non valido (discrete | envelope | both).",
                code="bad-enum", prefer_value=True)
    for k in ("plateau", "transition"):
        v = _num(sweep.get(k)) if sweep.get(k) is not None else None
        if sweep.get(k) is not None and (v is None or v <= 0):
            bag.add(spath + (k,), f"'{k}' deve essere un numero > 0 (secondi).",
                    code="bad-timing", prefer_value=True)
    n_axes = len(m.axes)
    orders = sweep.get("orders")
    if isinstance(orders, list):
        for i, o in enumerate(orders):
            if not isinstance(o, int) or o < 0 or (n_axes and o > n_axes):
                bag.add(spath + ("orders", i),
                        f"order {o!r} fuori range: con {n_axes} assi gli ordini "
                        f"validi sono 0..{n_axes}.",
                        code="bad-order", prefer_value=True)
    orderings = sweep.get("orderings")
    if isinstance(orderings, list):
        names = set(m.axes)
        for i, ordering in enumerate(orderings):
            if not isinstance(ordering, list):
                continue
            seen: set = set()
            for j, ax in enumerate(ordering):
                if names and ax not in names:
                    sug = _suggest(str(ax), sorted(names))
                    extra = f" Forse '{sug}'?" if sug else ""
                    bag.add(spath + ("orderings", i, j),
                            f"orderings: asse sconosciuto '{ax}' (dichiarati: "
                            f"{sorted(names)}).{extra}",
                            code="unknown-axis", prefer_value=True,
                            data={"fix": {"kind": "rename-value", "new": sug}} if sug else None)
                if ax in seen:
                    bag.add(spath + ("orderings", i, j),
                            f"orderings: asse duplicato '{ax}'.",
                            code="dup-axis", prefer_value=True)
                seen.add(ax)


def _check_stack(bag: Bag, doc: Document, m: StudyModel, prefix: KeyPath) -> None:
    spath = prefix + ("stack",)
    stack = doc.get(spath)
    if stack is None:
        return
    if not isinstance(stack, dict):
        bag.add(spath, "'stack' deve essere un mapping (anche vuoto: {}).",
                code="stack-type")
        return
    unit = stack.get("unit")
    if unit is not None and unit not in EI.X_UNITS:
        opts = " | ".join(sorted(EI.X_UNITS))
        bag.add(spath + ("unit",),
                f"stack: unit '{unit}' non ammessa ({opts}). 'hz' = frequenza di "
                "generazione, 's' = periodo in secondi, 'bpm' = battiti al minuto.",
                code="bad-unit", prefer_value=True)
    axis_names = set(m.axes)
    for name, cfg in stack.items():
        if name in STACK_RESERVED or cfg is None:
            continue
        epath = spath + (name,)
        if not prefix and axis_names and name not in axis_names:
            sug = _suggest(name, sorted(axis_names))
            extra = f" Forse '{sug}'?" if sug else ""
            bag.add(epath,
                    f"stack: asse sconosciuto '{name}' (dichiarati in 'axes:': "
                    f"{sorted(axis_names)}).{extra}",
                    code="unknown-axis",
                    data={"fix": {"kind": "rename", "new": sug}} if sug else None)
        if isinstance(cfg, dict) and ("rand" in cfg or "cps" in cfg):
            bag.add(epath,
                    f"stack: asse '{name}', i wrapper 'rand:'/'cps:' non esistono "
                    "piu': dichiara la camminata piatta (base/range/seed diretti).",
                    code="rand-wrapper",
                    data={"fix": {"kind": "flatten-wrapper", "path": list(epath)}})
            continue
        if not isinstance(cfg, dict) or "base" not in cfg:
            bag.add(epath,
                    f"stack: asse '{name}' deve avere una camminata con 'base' "
                    "(banda nell'unita' di 'unit': hz, default | s | bpm). Un asse "
                    "assente dal blocco 'stack:' resta 'linear' (n dalla Y).",
                    code="walk-no-base")
            continue
        extra = set(cfg) - _WALK_ALLOWED
        if extra:
            bag.add(epath,
                    f"stack: asse '{name}', chiavi non ammesse {sorted(extra)} "
                    "(solo base/range/seed/unit/distribution/drift). 'curve' va "
                    "dentro l'Env di base/range.",
                    code="walk-keys")
        u = cfg.get("unit")
        if u is not None and u not in EI.X_UNITS:
            opts = " | ".join(sorted(EI.X_UNITS))
            bag.add(epath + ("unit",),
                    f"stack: asse '{name}', unit '{u}' non ammessa ({opts}).",
                    code="bad-unit", prefer_value=True)
        _check_band(bag, doc, epath, cfg, f"stack.{name}")
        _check_walk_runaway(bag, doc, m, epath, cfg, name)


def _check_walk_runaway(bag: Bag, doc: Document, m: StudyModel,
                        epath: KeyPath, cfg: Dict[str, Any], name: str) -> None:
    """Stima anti-runaway: banda che genererebbe troppi breakpoint."""
    from . import convert

    if m.duration is None or m.duration <= 0:
        return
    walk = m.walk_for(name) if not epath[:1] == ("streams",) else None
    unit = (cfg.get("unit") if isinstance(cfg.get("unit"), str)
            else (walk.unit if walk else (m.stack_unit or "hz")))
    if unit not in EI.X_UNITS:
        return
    bpts = convert.env_points(cfg.get("base"))
    rpts = convert.env_points(cfg.get("range")) if cfg.get("range") is not None else [(0.0, 0.0)]
    if bpts is None or rpts is None:
        return
    mids = []
    nonpos = None
    for t in sorted({t for t, _ in bpts} | {t for t, _ in rpts}):
        lo = convert.env_eval(bpts, t)
        w = convert.env_eval(rpts, t)
        if lo <= 0 or lo + w <= 0:
            nonpos = (t, lo)
        mids.append(lo + w / 2.0)
    if nonpos is not None:
        label = {"hz": "frequenza", "s": "periodo", "bpm": "bpm"}[unit]
        bag.add(epath + ("base",),
                f"stack.{name}: {label} non positiva ({nonpos[1]:g}) nella banda — "
                "passo infinito o nullo, il walk andrebbe in errore.",
                code="walk-nonpositive", prefer_value=True)
        return
    mean = sum(mids) / len(mids)
    steps = {"hz": lambda v: 1.0 / v, "s": lambda v: v, "bpm": lambda v: 60.0 / v}
    step = steps[unit](mean)
    if step <= 0:
        return
    est = m.duration / step
    if est > MAX_WALK_POINTS:
        bag.add(epath + ("base",),
                f"stack.{name}: ~{int(est)} breakpoint stimati (> {MAX_WALK_POINTS}) "
                f"su duration={m.duration:g}s — il walk andrebbe in errore "
                "anti-runaway.",
                types.DiagnosticSeverity.Warning, code="walk-runaway",
                prefer_value=True)


def _check_streams(bag: Bag, doc: Document, m: StudyModel) -> None:
    streams = doc.get(("streams",))
    if streams is None:
        return
    if not isinstance(streams, dict):
        bag.add(("streams",), "'streams' deve essere un mapping di entry.",
                code="streams-type")
        return
    for name, cfg in streams.items():
        if cfg is None:
            continue
        spath: KeyPath = ("streams", name)
        if not isinstance(cfg, dict):
            bag.add(spath, f"Stream '{name}': override non valido, serve un dict "
                    "(anche vuoto: {}).", code="stream-type")
            continue
        _check_stack(bag, doc, m, spath)
        _check_sweep(bag, doc, m, spath + ("sweep",))
        if isinstance(cfg.get("base"), dict):
            _check_engine_block(bag, doc, m, spath + ("base",))
        spread = cfg.get("spread")
        if spread is not None:
            _check_spread(bag, doc, m, spath + ("spread",), spread, name)


def _over_entry_kp(spath: KeyPath, oe) -> KeyPath:
    """Key-path documento rappresentativo di una entry-over (per span a livello
    di path): la chiave annidata se c'e', altrimenti la prima chiave puntata."""
    key = oe.whole_key if oe.whole_key is not None else oe.doc_keys[0]
    return spath + ("over", key)


def _over_marker_kp(spath: KeyPath, oe, marker: str) -> KeyPath:
    """Key-path documento del valore di un marcatore della strategy: la chiave
    puntata del frammento se il marcatore arriva da li', altrimenti il campo
    annidato sotto la chiave-path."""
    if marker in oe.marker_keys:
        return spath + ("over", oe.marker_keys[marker])
    return spath + ("over", oe.whole_key, marker)


def _check_spread(bag: Bag, doc: Document, m: StudyModel, spath: KeyPath,
                  spread: Any, entry: str) -> None:
    if not isinstance(spread, dict):
        bag.add(spath, "'spread' e' un dict {n?, over, sweep?}.", code="spread-type")
        return
    n_decl = _check_spread_n(bag, spath, spread.get("n"))
    over = spread.get("over")
    if not isinstance(over, dict) or not over:
        bag.add(spath, f"Entry-spread '{entry}': manca 'over' "
                "({path puntato: strategy}).", code="spread-no-over")
        return

    entries = expand_over(over)
    owned: List[Tuple[str, int]] = []
    expr_entries: List[Any] = []
    for oe in entries.values():
        _check_over_path(bag, m, _over_entry_kp(spath, oe), oe.path)
        strat = oe.strategy
        if not isinstance(strat, dict):
            bag.add(_over_entry_kp(spath, oe),
                    f"spread.over['{oe.path}']: serve una strategy (dict: values "
                    "| ramp | banda | expr), non un valore nudo.",
                    code="spread-strategy")
            continue
        markers = [k for k in _SPREAD_MARKERS if k in strat]
        if len(markers) != 1:
            _report_strategy_count(bag, spath, oe, markers)
            continue
        mk = markers[0]
        if mk == "values":
            vals = strat.get("values")
            if isinstance(vals, list):
                owned.append((oe.path, len(vals)))
            else:
                bag.add(_over_marker_kp(spath, oe, "values"),
                        f"spread.over['{oe.path}']: 'values' deve essere una lista.",
                        code="spread-strategy", prefer_value=True)
        elif mk == "ramp":
            r = strat.get("ramp")
            _check_ramp(bag, _over_marker_kp(spath, oe, "ramp"), r,
                        f"spread.over['{oe.path}']", require_stop=False)
            if isinstance(r, dict) and {"start", "stop", "step"} <= set(r):
                c = ramp_count(r)
                if c is not None:
                    owned.append((oe.path, c))
        elif mk == "base":
            _check_band(bag, doc, _over_entry_kp(spath, oe), strat,
                        f"spread.over['{oe.path}']",
                        locate=lambda *ks, _oe=oe: (_over_entry_kp(spath, _oe) if not ks
                                                    else _over_marker_kp(spath, _oe, ks[0]) + tuple(ks[1:])))
            nn = strat.get("n")
            if isinstance(nn, int) and not isinstance(nn, bool):
                owned.append((oe.path, nn))
        elif mk == "expr":
            expr_entries.append(oe)

    counts = {c for _, c in owned}
    if n_decl is not None:
        counts.add(n_decl)

    # gli expr non possiedono il conteggio: si valutano con la n risolta
    if expr_entries:
        n_eff = n_decl if n_decl is not None else (
            next(iter(counts)) if len(counts) == 1 else 2)
        for oe in expr_entries:
            _check_spread_expr(bag, doc, m, spath, oe, n_eff)

    if len(counts) > 1:
        det = ", ".join(f"{p}: {c}" for p, c in owned)
        if n_decl is not None:
            det = f"n: {n_decl}" + (f", {det}" if det else "")
        bag.add(spath,
                f"Entry-spread '{entry}': conteggi discordanti ({det}) — "
                "spread.n e i conteggi posseduti devono coincidere.",
                code="spread-count")
    elif not counts:
        bag.add(spath,
                f"Entry-spread '{entry}': nessuna fonte per n — dichiara "
                "'n:' oppure una strategy che possiede il conteggio "
                "(values, ramp piena, banda con n).",
                code="spread-no-n")


def _report_strategy_count(bag: Bag, spath: KeyPath, oe, markers: List[str]) -> None:
    if markers:
        srcs = ", ".join(oe.marker_keys.get(mk, oe.whole_key or oe.path)
                         for mk in markers)
        bag.add(_over_entry_kp(spath, oe),
                f"spread.over['{oe.path}']: piu' strategy sullo stesso path "
                f"({srcs}) — esattamente una tra values | ramp | banda | expr.",
                code="spread-strategy")
    else:
        bag.add(_over_entry_kp(spath, oe),
                f"spread.over['{oe.path}']: serve esattamente una strategy tra "
                "values | ramp | banda (base/range) | expr (nessuna trovata).",
                code="spread-strategy")


def _check_spread_n(bag: Bag, spath: KeyPath, raw_n: Any) -> Optional[int]:
    """``spread.n`` normalizzato: intero >= 1, o nodo-expr valutato (percorso-v1).

    Nel nodo-expr il runtime non inietta ``i``/``n`` (li possiede lo spread):
    lo scope e' il solo ``let``, e il risultato deve essere un intero >= 1."""
    if raw_n is None:
        return None
    if exprlang.is_expr_node(raw_n):
        try:
            text, let = exprlang.parse_expr_node(raw_n)
            out = exprlang.eval_expr(text, dict(let))
        except ValueError as e:
            bag.add(spath + ("n",), str(e), code="expr", prefer_value=True)
            return None
        if isinstance(out, float) and out.is_integer():
            out = int(out)
        if not isinstance(out, int) or isinstance(out, bool) or out < 1:
            bag.add(spath + ("n",),
                    f"spread.n: l'espressione deve dare un intero >= 1 "
                    f"(valutato {out!r}).",
                    code="bad-n", prefer_value=True)
            return None
        return out
    if not isinstance(raw_n, int) or isinstance(raw_n, bool) or raw_n < 1:
        bag.add(spath + ("n",),
                "spread.n deve essere un intero >= 1 (o un nodo-expr).",
                code="bad-n", prefer_value=True)
        return None
    return raw_n


_LET_BAND_KEYS = frozenset({"base", "range", "seed", "distribution", "drift"})


def _check_spread_expr(bag: Bag, doc: Document, m: StudyModel, spath: KeyPath,
                       oe, n_eff: int) -> None:
    """Valida la strategy expr di uno spread come il runtime: estrae le
    bande-let (pescaggi random per-stream) prima del parse, poi valuta
    l'espressione con ``i``/``n`` iniettati."""
    strat = oe.strategy
    node = strat
    rand_let: Dict[str, Any] = {}
    let = strat.get("let")
    let_kp = _over_marker_kp(spath, oe, "let")
    if isinstance(let, dict):
        for var, v in let.items():
            if isinstance(v, dict) and any(k in v for k in GEN_MARKERS):
                rand_let[var] = v
                _check_let_band(bag, let_kp, var, v, oe.path)
        if rand_let:
            static = {k: v for k, v in let.items() if k not in rand_let}
            node = {**strat, "let": static}

    expr_kp = _over_marker_kp(spath, oe, "expr")
    try:
        text, static_let = exprlang.parse_expr_node(node)
    except ValueError as e:
        bag.add(expr_kp, str(e), code="expr", prefer_value=True)
        return
    reserved = sorted({"i", "n"} & (set(static_let) | set(rand_let)))
    if reserved:
        bag.add(let_kp,
                f"spread.over['{oe.path}'] expr: {reserved} riservati (indice e "
                "conteggio degli stream generati) — ridefinirli in 'let' e' errore.",
                code="expr-reserved")
        return
    scope: Dict[str, Any] = dict(static_let)
    for var in rand_let:
        scope[var] = 1.0  # un pescaggio-banda vale uno scalare, ai fini del check
    scope["i"] = 0
    scope["n"] = n_eff
    try:
        exprlang.eval_expr(text, scope)
    except ValueError as e:
        bag.add(expr_kp, str(e), code="expr", prefer_value=True)


def _check_let_band(bag: Bag, kp: KeyPath, var: str, node: Dict[str, Any],
                    path: str) -> None:
    """Regole della banda-let (runtime ``spread._let_band``): unico generatore
    ammesso la banda (``base``), senza ``n`` proprio, solo chiavi-banda."""
    markers = sorted(k for k in GEN_MARKERS if k in node)
    if markers != ["base"]:
        bag.add(kp,
                f"spread.over['{path}'] expr, 'let.{var}' usa {markers} — in "
                "'let' l'unico generatore ammesso e' la banda ('base').",
                code="expr-let-band")
        return
    if "n" in node:
        bag.add(kp,
                f"spread.over['{path}'] expr, 'let.{var}' dichiara 'n' — il "
                "conteggio e' dello spread, la banda-let pesca un valore per stream.",
                code="expr-let-band")
        return
    extra = set(node) - _LET_BAND_KEYS
    if extra:
        bag.add(kp,
                f"spread.over['{path}'] expr, 'let.{var}': chiavi non ammesse "
                f"{sorted(extra)} (solo {sorted(_LET_BAND_KEYS)}).",
                code="expr-let-band")


def _check_over_path(bag: Bag, m: StudyModel, opath: KeyPath, dotted: str) -> None:
    parts = dotted.split(".")
    head = parts[0]
    if head not in ("base", "axes", "stack", "sweep"):
        bag.add(opath,
                f"spread.over: path '{dotted}' non punta a base./axes./stack./sweep.",
                types.DiagnosticSeverity.Warning, code="over-path")
        return
    if head in ("axes", "stack") and len(parts) >= 2 and m.axes:
        if parts[1] not in m.axes:
            sug = _suggest(parts[1], list(m.axes))
            extra = f" Forse '{sug}'?" if sug else ""
            bag.add(opath,
                    f"spread.over: asse sconosciuto '{parts[1]}' in '{dotted}'.{extra}",
                    code="unknown-axis")


# ---------------------------------------------------------------------------
# Blocco engine (base / streams.*.base)


def _check_engine_block(bag: Bag, doc: Document, m: StudyModel,
                        bpath: KeyPath) -> None:
    base = doc.get(bpath)
    if not isinstance(base, dict):
        return
    if "density" in base and "fill_factor" in base:
        bag.add(bpath + ("fill_factor",),
                "'density' e 'fill_factor' sono mutuamente esclusivi "
                "(fill_factor ha priorita').",
                types.DiagnosticSeverity.Warning, code="density-fill")
    tm = base.get("time_mode")
    if tm is not None and tm not in EI.TIME_MODES:
        bag.add(bpath + ("time_mode",),
                f"time_mode '{tm}' non valido (absolute | normalized).",
                code="bad-enum", prefer_value=True)
    pitch = base.get("pitch")
    if isinstance(pitch, dict):
        units = [k for k in ("semitones", "quarter_tone", "eighth_tone", "cents",
                             "edo", "ratio") if k in pitch]
        if len(units) > 1:
            bag.add(bpath + ("pitch",),
                    f"pitch: piu' chiavi-unita' {units} nello stesso blocco — "
                    "una sola (modello unit-driven).",
                    code="pitch-units")
        if "value" in pitch and "edo" not in pitch:
            bag.add(bpath + ("pitch", "value"),
                    "pitch.value e' ammesso solo con 'edo: N'.",
                    code="pitch-value")
    grain = base.get("grain")
    if isinstance(grain, dict):
        _check_window_value(bag, bpath + ("grain", "envelope"), grain.get("envelope"))
        if "reverse" in grain and grain.get("reverse") is not None:
            bag.add(bpath + ("grain", "reverse"),
                    "grain.reverse: chiave presente vuota = reverse forzato; "
                    "'true'/'false'/'auto' e' errore.",
                    code="grain-reverse", prefer_value=True,
                    data={"fix": {"kind": "clear-value",
                                  "path": list(bpath + ("grain", "reverse"))}})
        if grain.get("duration_unit") == "samples" and "duration" not in grain:
            bag.add(bpath + ("grain", "duration_unit"),
                    "Con duration_unit: samples la grain.duration va sempre "
                    "indicata esplicitamente (il default 0.05 e' in secondi).",
                    code="samples-duration")
    pointer = base.get("pointer")
    if isinstance(pointer, dict):
        if "loop_end" in pointer and "loop_dur" in pointer:
            bag.add(bpath + ("pointer", "loop_dur"),
                    "loop_end e loop_dur sono mutuamente esclusivi "
                    "(loop_end ha priorita').",
                    types.DiagnosticSeverity.Warning, code="loop-excl")
        le, ls = _num(pointer.get("loop_end")), _num(pointer.get("loop_start"))
        if le is not None and ls is not None and le <= ls:
            bag.add(bpath + ("pointer", "loop_end"),
                    f"loop_end ({le:g}) <= loop_start ({ls:g}): per un loop a "
                    "cavallo della fine del file usa loop_dur.",
                    code="loop-order", prefer_value=True)
    # bounds sui parametri noti (scalari ed envelope)
    in_samples = _samples_unit(doc, bpath)
    for dotted, info in EI.PARAMS.items():
        parts = tuple(dotted.split("."))
        if parts[0] in ("onset", "duration") and len(parts) == 1:
            continue
        v = doc.get(bpath + parts)
        if v is None:
            continue
        _check_param_bounds(bag, bpath + parts, dotted, v, m,
                            in_samples=in_samples)


def _check_param_bounds(bag: Bag, path: KeyPath, dotted: str, v: Any,
                        m: StudyModel, in_samples: bool = False) -> None:
    if _num(v) is not None:
        _check_bounds_value(bag, path, dotted, v, dotted, in_samples=in_samples)
        return
    pts: Optional[list] = None
    ppath = path
    if isinstance(v, list) and v and all(
        isinstance(p, (list, tuple)) and len(p) in (2, 3) for p in v
    ):
        pts = v
    elif isinstance(v, dict) and isinstance(v.get("points"), list):
        pts = v["points"]
        ppath = path + ("points",)
    if not pts:
        return
    for i, p in enumerate(pts):
        if isinstance(p, (list, tuple)) and len(p) in (2, 3):
            y = _num(p[1])
            if y is not None:
                _check_bounds_value(bag, ppath + (i,), dotted, y,
                                    f"{dotted} t={p[0]!r}", in_samples=in_samples)
            if len(p) == 3 and p[2] not in EI.INTERPOLATIONS:
                bag.add(ppath + (i,),
                        f"{dotted}: type per-punto '{p[2]}' non valido "
                        "(linear | cubic | step).",
                        code="bad-enum", prefer_value=True)


def _check_window_value(bag: Bag, path: KeyPath, env: Any) -> None:
    def check_name(p: KeyPath, name: Any) -> None:
        if isinstance(name, str) and name not in EI.WINDOWS:
            sug = _suggest(name, sorted(EI.WINDOWS))
            extra = f" Forse '{sug}'?" if sug else ""
            bag.add(p, f"Finestra '{name}' sconosciuta.{extra}",
                    code="unknown-window", prefer_value=True,
                    data={"fix": {"kind": "rename-value", "new": sug}} if sug else None)

    if env is None:
        return
    if isinstance(env, str):
        check_name(path, env)
    elif isinstance(env, list):
        for i, name in enumerate(env):
            check_name(path + (i,), name)
    elif isinstance(env, dict):
        check_name(path + ("from",), env.get("from"))
        check_name(path + ("to",), env.get("to"))
        states = env.get("states")
        if isinstance(states, list):
            for i, st in enumerate(states):
                if isinstance(st, (list, tuple)) and len(st) == 2:
                    check_name(path + ("states", i), st[1])


# ---------------------------------------------------------------------------
# Chiavi sconosciute (pass generico sui contesti chiusi)


def _check_unknown_keys(bag: Bag, doc: Document) -> None:
    for entry in list(doc.iter_entries()):
        if entry.kind != "mapping":
            continue
        ctx = schema.context_for_path(entry.path)
        if ctx not in schema.CLOSED_CONTEXTS:
            continue
        value = doc.get(entry.path)
        if not isinstance(value, dict):
            continue
        allowed = [k.name for k in schema.keys_for(ctx)]
        for key in value:
            if not isinstance(key, str) or key in allowed:
                continue
            # i contesti env/axis condividono il vocabolario banda: gia' coperti
            if ctx == "walk" or (ctx == "axis" and key in ("rand", "cps")):
                continue  # errori dedicati altrove
            sug = _suggest(key, allowed)
            extra = f" Forse intendevi '{sug}'?" if sug else ""
            bag.add(entry.path + (key,),
                    f"Chiave '{key}' non prevista nel contesto '{ctx}'.{extra}",
                    types.DiagnosticSeverity.Warning, code="unknown-key",
                    data={"fix": {"kind": "rename", "new": sug}} if sug else None)


# ---------------------------------------------------------------------------
# Nodi-expr: stessa diagnostica del runtime


def _check_expr_nodes(bag: Bag, doc: Document, m: StudyModel) -> None:
    for entry in list(doc.iter_entries()):
        if entry.kind != "mapping":
            continue
        # i nodi-expr dentro un blocco spread (spread.n e spread.over.*, in
        # forma annidata o puntata) sono validati da _check_spread, che gestisce
        # le bande-let e lo scope i/n: qui si saltano per non duplicarli.
        p = entry.path
        if len(p) >= 3 and p[0] == "streams" and p[2] == "spread":
            continue
        # un nodo-expr annidato dentro il 'let' di un altro nodo-expr non e'
        # standalone: lo valida (parse ricorsivo) e lo risolve (lazy, con i
        # fratelli in scope) il nodo contenitore — qui darebbe falsi 'nome
        # ignoto' sui riferimenti ai fratelli.
        if "let" in p:
            continue
        value = doc.get(p)
        if not exprlang.is_expr_node(value):
            continue
        try:
            text, let = exprlang.parse_expr_node(value)
        except ValueError as e:
            bag.add(p, str(e), code="expr", prefer_value=False)
            continue
        try:
            exprlang.eval_expr(text, dict(let))
        except ValueError as e:
            bag.add(p + ("expr",), str(e), code="expr", prefer_value=True)
