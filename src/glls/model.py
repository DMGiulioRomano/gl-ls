"""Modello semantico di uno ``study.yml`` gia' parsato.

Estrae dal :class:`glls.yamlpos.Document` la vista che serve alle feature:
assi con il loro generatore Y, camminate-X del blocco stack con unit risolta
per precedenza, stream (incluse le entry-spread), durata condivisa. Tutto
tollerante: il modello si costruisce anche da documenti incompleti.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .convert import as_num as _num
from .yamlpos import Document, KeyPath

AXES_RESERVED = ("interpolation", "seed")
STACK_RESERVED = ("seed", "unit")
VERSIONS_RESERVED = ("onset", "duration", "chunk")
GEN_MARKERS = ("values", "ramp", "base")
BAND_KEYS = frozenset({"base", "range", "n", "seed", "distribution", "drift"})

# Marcatori di strategy riconosciuti come suffisso terminale di una chiave
# puntata di ``spread.over`` (granstudies ``spread._STRATEGY_MARKERS``).
OVER_MARKERS = frozenset({
    "values", "ramp", "base", "range", "seed", "distribution", "drift",
    "expr", "let", "n",
})


@dataclass
class AxisInfo:
    name: str
    path: Optional[str]                   # path engine risolto (esplicito o = nome)
    cfg: Dict[str, Any]
    doc_path: KeyPath                     # path nel documento
    generator: Optional[str] = None       # values | ramp | band | None
    n: Optional[int] = None               # conteggio posseduto dalla Y, se noto
    interpolation: str = "linear"
    explicit_path: bool = False           # True se 'path:' e' dichiarato

    @property
    def defers_n(self) -> bool:
        return self.generator == "band" and "n" not in self.cfg


@dataclass
class WalkInfo:
    axis: str
    cfg: Dict[str, Any]
    doc_path: KeyPath
    unit: str = "hz"                      # unit risolta (per-asse > globale > hz)


@dataclass
class StreamInfo:
    name: str
    cfg: Dict[str, Any]
    doc_path: KeyPath
    is_spread: bool = False
    spread_n: Optional[int] = None


@dataclass
class StudyModel:
    doc: Document
    study_id: Optional[str] = None
    duration: Optional[float] = None
    base: Dict[str, Any] = field(default_factory=dict)
    time_mode: str = "absolute"
    base_duration: Optional[float] = None
    axes: Dict[str, AxisInfo] = field(default_factory=dict)
    axes_seed: Optional[int] = None
    study_interpolation: str = "linear"
    sweep: Dict[str, Any] = field(default_factory=dict)
    has_stack: bool = False
    stack_unit: Optional[str] = None
    walks: Dict[str, WalkInfo] = field(default_factory=dict)
    streams: Dict[str, StreamInfo] = field(default_factory=dict)

    # ------------------------------------------------------------------
    def axis_names(self) -> List[str]:
        return list(self.axes)

    def walk_for(self, axis: str) -> Optional[WalkInfo]:
        return self.walks.get(axis)

    def sweep_counts(self) -> Optional[Dict[int, int]]:
        """{ordine: numero varianti} per gli orders dichiarati (se calcolabile)."""
        from math import comb

        counts: Dict[int, int] = {}
        n = len(self.axes)
        if n == 0:
            return None
        # Default condizionato da ``orderings`` (study_spec): con orderings
        # popolato e ``orders`` assente il runtime non genera automatiche
        # ([]); senza orderings resta il default storico [1..n].
        orderings = self.sweep.get("orderings")
        has_orderings = (isinstance(orderings, list)
                         and any(isinstance(o, list) and o for o in orderings))
        default = [] if has_orderings else list(range(1, n + 1))
        orders = self.sweep.get("orders", default)
        if not isinstance(orders, list):
            return None
        for o in orders:
            if isinstance(o, int) and 0 <= o <= n:
                counts[o] = comb(n, o)
        return counts or None



def split_over_key(key: Any, value: Any) -> Optional[Tuple[str, str]]:
    """(path, marcatore) se una chiave di ``spread.over`` va splittata.

    Split solo se la chiave e' puntata, l'ultimo segmento e' un marcatore di
    strategy e il valore NON e' un dict: un valore-dict e' gia' una strategy
    completa e la chiave resta un path intero (cosi' ``axes.density.base:
    {expr: ...}`` — path che finisce davvero in ``base`` — non viene spezzato
    sul ``base`` finale).
    """
    if not isinstance(key, str) or "." not in key or isinstance(value, dict):
        return None
    head, _, last = key.rpartition(".")
    if head and last in OVER_MARKERS:
        return head, last
    return None


@dataclass
class OverEntry:
    """Una strategy di ``spread.over`` dopo l'espansione delle chiavi puntate.

    ``strategy`` e' il dict fuso dei frammenti; resta il valore grezzo quando
    il path porta un valore non-dict non splittabile (errore a valle).
    ``doc_keys`` sono le chiavi del documento che contribuiscono, in ordine;
    ``marker_keys`` mappa ogni marcatore portato da un frammento puntato alla
    sua chiave (per puntare le diagnostiche sulla riga giusta); ``whole_key``
    e' la chiave della forma non splittata (== path), se presente.
    """

    path: str
    strategy: Any = None
    doc_keys: List[str] = field(default_factory=list)
    marker_keys: Dict[str, str] = field(default_factory=dict)
    whole_key: Optional[str] = None
    # chiave documento -> key-path sotto ``spread`` (("over", chiave) per la
    # forma annidata, (chiave,) per una dotted ``over.<path>`` al primo livello)
    doc_key_paths: Dict[str, Tuple[str, ...]] = field(default_factory=dict)


def split_spread_over_key(key: Any) -> Optional[str]:
    """Il resto dopo ``over.`` se ``key`` e' una chiave puntata al primo
    livello di ``spread:`` (granstudies ``_expand_spread_dotted``): la chiave
    literal ``over`` e ogni altra chiave restano None."""
    if isinstance(key, str) and key.startswith("over.") and len(key) > len("over."):
        return key[len("over."):]
    return None


def over_items(spread: Dict[str, Any]) -> List[Tuple[str, Any, Tuple[str, ...]]]:
    """Le entry di ``over`` effettive di un blocco spread, in ordine di
    documento: ``(chiave-over, valore, key-path documento sotto spread)``.

    Copre sia la forma annidata ``over: {...}`` sia le chiavi puntate
    ``over.<path>`` al primo livello di ``spread:`` — le due forme sono
    equivalenti e si fondono nello stesso dict (``_expand_spread_dotted``).
    """
    items: List[Tuple[str, Any, Tuple[str, ...]]] = []
    for key, value in spread.items():
        rest = split_spread_over_key(key)
        if rest is not None:
            items.append((rest, value, (key,)))
        elif key == "over" and isinstance(value, dict):
            for ok, ov in value.items():
                items.append((str(ok), ov, ("over", str(ok))))
    return items


def _merge_strategy(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _merge_strategy(result[k], v)
        else:
            result[k] = v
    return result


def expand_over(over: Dict[str, Any]) -> Dict[str, OverEntry]:
    """Espande le chiavi puntate di ``spread.over`` fondendo i frammenti.

    Stessa semantica di granstudies ``spread._expand_over_dotted``: una chiave
    che termina con un marcatore e ha valore non-dict diventa ``{path:
    {marcatore: valore}}``; piu' frammenti sullo stesso path (es. la banda su
    tre righe ``.base``/``.range``/``.seed``) si fondono in un'unica strategy,
    nell'ordine di dichiarazione (l'ultimo vince sui conflitti di foglia).
    """
    return expand_over_items(
        [(str(k), v, ("over", str(k))) for k, v in over.items()])


def expand_over_items(
    items: List[Tuple[str, Any, Tuple[str, ...]]]
) -> Dict[str, OverEntry]:
    """Come ``expand_over``, su entry gia' raccolte da ``over_items`` — cosi'
    i frammenti dotted ``over.<path>`` al primo livello di ``spread:`` si
    fondono con la forma annidata, e ogni frammento conserva il key-path
    documento per ancorare le diagnostiche."""
    out: Dict[str, OverEntry] = {}
    for key, value, doc_kp in items:
        split = split_over_key(key, value)
        if split is not None:
            path, marker = split
            contribution: Any = {marker: value}
        else:
            path, marker = str(key), None
            contribution = value
        e = out.setdefault(path, OverEntry(path=path))
        doc_key = doc_kp[-1]
        e.doc_keys.append(doc_key)
        e.doc_key_paths[doc_key] = doc_kp
        if marker is not None:
            e.marker_keys[marker] = doc_key
        else:
            e.whole_key = doc_key
        if isinstance(contribution, dict):
            merged = e.strategy if isinstance(e.strategy, dict) else {}
            e.strategy = _merge_strategy(merged, contribution)
        else:
            e.strategy = contribution
    return out


def _is_expr_node(spec: Any) -> bool:
    return isinstance(spec, dict) and "expr" in spec


def _eval_spread_n(node: Dict[str, Any]) -> Optional[int]:
    """``spread.n`` da nodo-expr (percorso-v1), valutato col solo ``let``.

    Tollerante: se l'espressione non risolve staticamente (nomi di percorso non
    in scope) o non da' un intero >= 1, ritorna None e il conteggio si cerca
    nelle strategy di ``over``."""
    from . import exprlang

    try:
        text, let = exprlang.parse_expr_node(node)
        out = exprlang.eval_expr(text, dict(let))
    except ValueError:
        return None
    if isinstance(out, float) and out.is_integer():
        out = int(out)
    if isinstance(out, int) and not isinstance(out, bool) and out >= 1:
        return out
    return None


def ramp_count(cfg: Dict[str, Any]) -> Optional[int]:
    """Numero di punti di una ``ramp`` scalare piena (None se non statico)."""
    start, stop, step = cfg.get("start"), cfg.get("stop"), cfg.get("step")
    s0, s1, st = _num(start), _num(stop), _num(step)
    if s0 is None or s1 is None or st is None or st <= 0:
        return None
    import math

    span = abs(s1 - s0)
    return int(math.floor(span / st + 1e-9)) + 1


def y_generator_of(cfg: Dict[str, Any]) -> Tuple[Optional[str], Optional[int]]:
    """(generatore, n posseduto) di un dict-asse/strategy: values | ramp | band."""
    markers = [m for m in GEN_MARKERS if m in cfg]
    if len(markers) != 1:
        return (None, None)
    m = markers[0]
    if m == "values":
        vals = cfg.get("values")
        return ("values", len(vals) if isinstance(vals, list) else None)
    if m == "ramp":
        r = cfg.get("ramp")
        return ("ramp", ramp_count(r) if isinstance(r, dict) else None)
    n = cfg.get("n")
    return ("band", n if isinstance(n, int) and not isinstance(n, bool) else None)


def build(doc: Document) -> StudyModel:
    m = StudyModel(doc=doc)
    data = doc.data
    if not isinstance(data, dict):
        return m
    m.study_id = data.get("study_id") if isinstance(data.get("study_id"), str) else None
    m.duration = _num(data.get("duration"))

    base = data.get("base")
    if isinstance(base, dict):
        m.base = base
        tm = base.get("time_mode")
        if tm in ("absolute", "normalized"):
            m.time_mode = tm
        m.base_duration = _num(base.get("duration"))

    axes = data.get("axes")
    if isinstance(axes, dict):
        interp = axes.get("interpolation")
        if isinstance(interp, str):
            m.study_interpolation = interp
        seed = axes.get("seed")
        if isinstance(seed, int):
            m.axes_seed = seed
        for name, cfg in axes.items():
            if name in AXES_RESERVED or not isinstance(cfg, dict):
                continue
            gen, n = y_generator_of(cfg)
            # 'path' esplicito resta un alias; se omesso, la chiave dell'asse
            # (anche in dot-notation, es. 'grain.duration') e' il path engine
            explicit = isinstance(cfg.get("path"), str)
            m.axes[name] = AxisInfo(
                name=name,
                path=cfg["path"] if explicit else (name if isinstance(name, str) else None),
                explicit_path=explicit,
                cfg=cfg,
                doc_path=("axes", name),
                generator=gen,
                n=n,
                interpolation=cfg.get("interpolation", m.study_interpolation),
            )

    sweep = data.get("sweep")
    if isinstance(sweep, dict):
        m.sweep = sweep

    if "stack" in data:
        m.has_stack = True
        stack = data.get("stack")
        if isinstance(stack, dict):
            unit = stack.get("unit")
            m.stack_unit = unit if isinstance(unit, str) else None
            for name, cfg in stack.items():
                if name in STACK_RESERVED or cfg is None or not isinstance(cfg, dict):
                    continue
                per_axis = cfg.get("unit")
                resolved = per_axis if isinstance(per_axis, str) else (m.stack_unit or "hz")
                m.walks[name] = WalkInfo(
                    axis=name, cfg=cfg, doc_path=("stack", name), unit=resolved
                )

    streams = data.get("streams")
    if isinstance(streams, dict):
        for name, cfg in streams.items():
            cfg = cfg if isinstance(cfg, dict) else {}
            spread = cfg.get("spread")
            is_spread = isinstance(spread, dict)
            n = None
            if is_spread:
                decl = spread.get("n")
                if isinstance(decl, int) and not isinstance(decl, bool):
                    n = decl
                elif _is_expr_node(decl):
                    n = _eval_spread_n(decl)
                if n is None:
                    for oe in expand_over_items(over_items(spread)).values():
                        if isinstance(oe.strategy, dict):
                            _, owned = y_generator_of(oe.strategy)
                            if owned:
                                n = owned
                                break
            m.streams[name] = StreamInfo(
                name=name, cfg=cfg, doc_path=("streams", name),
                is_spread=is_spread, spread_n=n,
            )
    return m
