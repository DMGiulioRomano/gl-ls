"""Modello semantico di uno ``study.yml`` gia' parsato.

Estrae dal :class:`glls.yamlpos.Document` la vista che serve alle feature:
assi con il loro generatore Y, camminate-X del blocco stack con unit risolta
per precedenza, stream (incluse le entry-spread), durata condivisa. Tutto
tollerante: il modello si costruisce anche da documenti incompleti.
"""
from __future__ import annotations

import math
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
    # Durata dichiarata dalla entry: ``duration:`` di entry (che dopo il merge
    # diventa top-level del documento merged) o la sua ``base.duration``. None
    # se la entry non ne dichiara nessuna: erediterebbe quella di documento.
    duration: Optional[float] = None
    declares_duration: bool = False       # dichiarata, anche se non statica
    # La entry porta un blocco ``stack:`` proprio (annidato o in chiavi
    # puntate). Dopo il merge quel blocco e' top-level del documento dello
    # stream, quindi il processo stack e' attivo per LUI anche se il documento
    # base non ha nessun ``stack:``.
    declares_stack: bool = False
    # I path — relativi a ``stack.`` — che la entry scrive, con ogni prefisso
    # (``grain.duration.range`` porta anche ``grain``, ``grain.duration``):
    # cosi' il confine dei nomi d'asse dotted non va risolto. Una camminata
    # annullata (``asse: null``) non c'e': la forma serve proprio a riportare
    # l'asse a linear.
    stack_paths: frozenset = frozenset()
    # Gli assi che la entry riporta a linear con ``asse: null``. Non e'
    # l'inverso di ``stack_paths``: "assente" e "annullata" sono cose diverse —
    # assente eredita la camminata di documento, annullata la toglie.
    stack_nulled: frozenset = frozenset()


@dataclass
class StudyModel:
    doc: Document
    study_id: Optional[str] = None
    # ``duration:`` al top del documento: NON e' piu' una chiave dello studio
    # (granstudies #42, ``study_spec.reject_top_level_duration``). Resta nel
    # modello solo per poterla diagnosticare — non e' una fonte di durata.
    duration: Optional[float] = None
    has_top_duration: bool = False
    base: Dict[str, Any] = field(default_factory=dict)
    time_mode: str = "absolute"
    base_duration: Optional[float] = None
    has_base_duration: bool = False       # dichiarata, anche se non statica
    # Durata di replica iniettata come ``base.duration`` dai rami
    # multi-documento: ``versions.duration`` (passo della concatenazione) o
    # ``percorso`` (durata d'istanza, dedotta da arco/passo quando implicita).
    # Il valore c'e' solo se statico; l'etichetta dice da dove viene.
    replica_duration_source: Optional[str] = None
    replica_duration: Optional[float] = None
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

    def walk_in_stream(self, axis: str, stream: str) -> bool:
        """True se ``axis`` ha una camminata-X nel documento *merged* di
        ``stream`` — quello che il runtime valida davvero.

        Il blocco ``stack:`` di un override e' un fatto dello stream: dopo il
        merge diventa top-level del suo documento. Tre esiti, e sono tutti e
        tre diversi: la entry dichiara la camminata (vale), non ne parla
        (eredita quella di documento), la annulla con ``asse: null`` (la
        toglie, l'asse torna linear per lui). ``walk_for`` risponde per il
        documento base, questa per uno stream."""
        si = self.streams.get(stream)
        if si is None:
            return self.walk_for(axis) is not None
        if any(p == axis or p.startswith(f"{axis}.") for p in si.stack_paths):
            return True
        return self.walk_for(axis) is not None and axis not in si.stack_nulled

    # ---- durata (granstudies #42) -------------------------------------
    # Ogni ``duration`` sta accanto alla cosa di cui e' la durata, e quella di
    # uno *stream* si risolve per catena: ``duration:`` di entry >
    # ``base.duration`` dello stream > ``base.duration`` di documento. Con
    # ``versions:``/``percorso:`` la durata di replica viene iniettata come
    # ``base.duration`` del documento per-combo, quindi fa da default. La
    # durata del *documento* non si dichiara: e' ``max(onset + duration)``.

    def duration_for(self, stream: Optional[str] = None) -> Optional[float]:
        """Durata risolta di uno stream (o del documento se ``stream`` e' None).

        None solo quando nessuna fonte statica la risolve: e' l'unico caso in
        cui il runtime va davvero in errore su ``stack:``."""
        if stream is not None:
            si = self.streams.get(stream)
            if si is not None and si.duration is not None:
                return si.duration
        if self.base_duration is not None:
            return self.base_duration
        if self.replica_duration is not None:
            return self.replica_duration
        # ultima rete: il top-level ora vietato. Leggerlo qui evita che ogni
        # stima (walk, lens, inlay) muoia su un documento non ancora migrato,
        # che ha gia' la sua diagnostica.
        return self.duration

    def declares_duration(self, stream: Optional[str] = None) -> bool:
        """True se una fonte *dichiara* una durata, anche non statica.

        Serve alle diagnostiche: una durata scritta come generatore o nodo-expr
        non da' un numero ma non e' un documento senza durata."""
        if stream is not None:
            si = self.streams.get(stream)
            if si is not None and si.declares_duration:
                return True
        return (self.has_base_duration
                or self.replica_duration_source is not None
                or self.has_top_duration)

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


def has_compact_frame(spec: Any) -> bool:
    """La *cornice* posizionale di una forma compatta, senza guardare il pattern.

    ``3-6 elementi`` con ``end_time`` numero in posizione 1 e ``n_reps`` intero
    in posizione 2. Separarla dal predicato completo serve a un caso solo, ma
    ambiguo: un pattern scritto come BP group. ``[group, end_time, n_reps]`` non
    e' preso ne' da ``is_compact_env`` (il pattern non e' una lista di liste)
    ne' da ``is_bp_group`` (3 elementi), e senza la cornice non si
    distinguerebbe da un envelope misto di tre macrozone — dove il secondo
    elemento e' una lista, non un numero.
    """
    return (
        isinstance(spec, (list, tuple))
        and 3 <= len(spec) <= 6
        and isinstance(spec[1], (int, float))
        and not isinstance(spec[1], bool)
        and isinstance(spec[2], int)
        and not isinstance(spec[2], bool)
    )


def is_compact_env(spec: Any) -> bool:
    """True se ``spec`` e' la forma compatta a cicli dell'engine.

    ``[pattern, end_time, n_reps, interp?, time_dist?, wrap?]`` — il predicato
    e' quello del runtime (granstudies ``value_generators.is_compact_env``): si
    riconosce dai primi tre elementi (lista non vuota di liste, numero, intero).
    Non collide con le forme statiche di Env: ``[[t, y], ...]`` ha una lista in
    posizione 1, lo shorthand ``[a, b]`` ha due soli scalari.
    """
    return (
        has_compact_frame(spec)
        and isinstance(spec[0], (list, tuple))
        and len(spec[0]) > 0
        and all(isinstance(p, (list, tuple)) for p in spec[0])
    )


def is_bp_group(spec: Any) -> bool:
    """True se ``spec`` e' un **BP group** dell'engine: ``[points, interp]``.

    Un run di breakpoint avvolto in un gruppo compatto che dichiara
    l'interpolazione della propria macrozona (PGE #64, ``yaml.md`` §2.7),
    simmetrico ai loop block. La disambiguazione e' quella ufficiale: il BP
    group e' l'unica lista a **2 elementi** con ``elem[0]`` lista di punti ed
    ``elem[1]`` stringa. Un breakpoint nudo ``[t, v]`` ha ``elem[0]``
    numerico; un loop block ha 3-6 elementi (quindi nessuna collisione con
    ``is_compact_env``).

    Differenza che conta per la validazione: i tempi dei punti del gruppo sono
    **assoluti**, non percentuali del ciclo come nel ``pattern`` della forma
    compatta, ne' normalizzati in [0, 1] come i breakpoint di banda.
    """
    return (
        isinstance(spec, (list, tuple))
        and len(spec) == 2
        and isinstance(spec[0], (list, tuple))
        and len(spec[0]) > 0
        and all(isinstance(p, (list, tuple)) for p in spec[0])
        and isinstance(spec[1], str)
    )


def stack_paths_of(cfg: Dict[str, Any]) -> frozenset:
    """I path scritti sotto ``stack.`` da una entry di ``streams:``.

    Forma annidata (``stack: {density: {...}}``) e chiavi puntate
    (``stack.density.base``) sono la stessa cosa dopo ``_expand_dotted_keys``
    del runtime. Si raccoglie **ogni prefisso** — come ``_axis_write_paths`` fa
    per ``axes.`` — cosi' un asse dotted (``grain.duration``) si riconosce per
    confronto diretto senza dover risolvere dove finisce il suo nome.

    Una entry annullata (``asse: null``) viene scartata: e' la forma con cui un
    override riporta a linear una camminata ereditata, quindi *toglie* la
    camminata invece di dichiararla.
    """
    out: set = set()

    def walk(prefix: str, node: Any) -> None:
        if prefix:
            out.add(prefix)
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(k, str) and v is not None:
                    walk(f"{prefix}.{k}" if prefix else k, v)

    for key, value in cfg.items():
        if (isinstance(key, str) and key.startswith("stack.")
                and len(key) > len("stack.") and value is not None):
            walk(key[len("stack."):], value)
    nested = cfg.get("stack")
    if isinstance(nested, dict):
        walk("", nested)
    return frozenset(out)


def stack_nulled_of(cfg: Dict[str, Any]) -> frozenset:
    """Gli assi che una entry riporta a linear con ``asse: null``.

    Il runtime scarta le entry annullate (``study_spec._stack_config``): dopo
    il merge quell'asse non ha piu' camminata, quindi per QUELLO stream la
    n-ownership torna alla Y. Va tenuto distinto dall'asse semplicemente
    assente dall'override, che invece eredita la camminata di documento."""
    out: set = set()
    nested = cfg.get("stack")
    if isinstance(nested, dict):
        out |= {k for k, v in nested.items() if isinstance(k, str) and v is None}
    for key, value in cfg.items():
        if (isinstance(key, str) and key.startswith("stack.")
                and len(key) > len("stack.") and value is None):
            out.add(key[len("stack."):])
    return frozenset(out)


def looks_like_bp_group(spec: Any) -> bool:
    """Come :func:`is_bp_group`, ma senza pretendere punti ben formati.

    ``is_bp_group`` e' il predicato *ufficiale*, quello che disambigua un
    gruppo da un breakpoint nudo e da un loop block: pretende che ``elem[0]``
    sia una lista di liste, quindi dice No a un gruppo scritto male. Alla
    diagnostica serve il contrario — ``[[[..], 1, 4], 'cubic']`` (una forma
    compatta infilata al posto dei punti) non e' un gruppo valido ma e'
    inequivocabilmente un gruppo *sbagliato*, e dirlo e' meglio che tacere.
    """
    return (isinstance(spec, (list, tuple)) and len(spec) == 2
            and isinstance(spec[0], (list, tuple)) and len(spec[0]) > 0
            and isinstance(spec[1], str))


def bp_group_summary(spec: Any) -> Optional[str]:
    """Riassunto leggibile di un BP group: punti, interp, arco dei tempi.

    ``3 punti · cubic · t 0–1 (assoluti)`` — l'arco compare solo se i tempi
    del primo e ultimo punto sono numeri. None se ``spec`` non e' un gruppo.
    """
    if not is_bp_group(spec):
        return None
    points, interp = spec[0], spec[1]
    n = len(points)
    parts = [f"{n} {'punto' if n == 1 else 'punti'}", str(interp)]
    t0 = _num(points[0][0]) if points[0] else None
    t1 = _num(points[-1][0]) if points[-1] else None
    if t0 is not None and t1 is not None:
        parts.append(f"t {t0:g}–{t1:g} (assoluti)")
    else:
        parts.append("tempi assoluti")
    return " · ".join(parts)


def in_spread_let(path: KeyPath) -> bool:
    """True se ``path`` vive dentro un blocco ``spread.let`` (manopole di voce).

    La forma compatta a cicli la risolve ``resolve_knobs`` — documento e gruppo;
    ``spread.let`` ha un resolver suo (banda per voce / expr su ``i``/``n``) che
    non la conosce, quindi li' non va ne' riassunta ne' annotata."""
    return any(seg == "spread" and i + 1 < len(path) and path[i + 1] == "let"
               for i, seg in enumerate(path))


def compact_summary(spec: Any) -> Optional[str]:
    """Riassunto leggibile di una forma compatta: cicli, vertice, wrap.

    ``4 cicli · vertice 25% · wrap`` — il vertice e' la ``x%`` del punto di
    massimo del pattern (omesso se il massimo non e' unico o il pattern ha un
    punto solo); ``interp``/``time_dist`` no, si leggono gia' nel testo a
    fianco. None se ``spec`` non e' una forma compatta.
    """
    if not is_compact_env(spec):
        return None
    parts = [f"{spec[2]} {'ciclo' if spec[2] == 1 else 'cicli'}"]
    pairs = [(_num(p[0]), _num(p[1])) for p in spec[0] if len(p) >= 2]
    if len(pairs) > 1 and all(x is not None and y is not None for x, y in pairs):
        ys = [y for _x, y in pairs]
        top = max(ys)
        if ys.count(top) == 1:
            parts.append(f"vertice {pairs[ys.index(top)][0]:g}%")
    if len(spec) >= 6 and spec[5] is True:
        parts.append("wrap")
    return " · ".join(parts)


def _is_expr_node(spec: Any) -> bool:
    return isinstance(spec, dict) and "expr" in spec


def is_n_env(raw: Any) -> bool:
    """True se ``spread.n`` e' scritto come Env — il coro cresce e cala *nel
    tempo* dentro la singola versione (runtime ``spread._is_n_env``).

    Le forme di sempre di un Env disegnato: ``[[t, n], ...]``, lo shorthand
    ``[a, b]``, ``{type, points, curve}``. Il nodo-expr (dict con ``expr`` e
    senza ``points``) resta il caso scalare per-istanza, e l'intero pure.
    """
    if isinstance(raw, dict):
        return "points" in raw
    return isinstance(raw, (list, tuple)) and bool(raw)


def n_env_values(raw: Any) -> Optional[List[float]]:
    """I valori Y di un ``spread.n`` come Env, None se non sono tutti numeri.

    Come il runtime (``spread._n_env_peak``): il secondo elemento di ogni
    punto, o il punto stesso nello shorthand ``[a, b]``. La forma compatta a
    cicli finisce qui con un pattern al posto di un numero — e infatti non e'
    ammessa per ``n``.
    """
    points = raw.get("points") if isinstance(raw, dict) else raw
    if not isinstance(points, (list, tuple)) or not points:
        return None
    out: List[float] = []
    for p in points:
        if isinstance(p, (list, tuple)):
            v = p[1] if len(p) >= 2 else None
        else:
            v = p
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return None
        out.append(float(v))
    return out


def n_env_peak(raw: Any) -> Optional[int]:
    """Voci da generare con ``n`` come Env: ``ceil`` del picco di ``n(t)``.

    Uno stream nel documento engine e' statico, il loro numero non cambia in
    corsa: le voci si generano tutte fino al massimo e un gate su
    ``base.volume`` le accende e spegne. Il conteggio da confrontare coi
    posseduti di ``over`` e' quindi il picco, non il primo o l'ultimo punto.
    """
    values = n_env_values(raw)
    if values is None:
        return None
    return math.ceil(max(values))


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
    m.has_top_duration = "duration" in data

    base = data.get("base")
    if isinstance(base, dict):
        m.base = base
        tm = base.get("time_mode")
        if tm in ("absolute", "normalized"):
            m.time_mode = tm
        m.base_duration = _num(base.get("duration"))
        m.has_base_duration = "duration" in base

    # Durata di replica dei rami multi-documento: entrambi la iniettano come
    # ``base.duration`` del documento per-combo/per-istanza, quindi a valle e'
    # indistinguibile da un default di documento. ``versions`` la inietta solo
    # se ``versions.duration`` c'e' (senza, il passo della concatenazione
    # manca e il runtime da' errore per conto suo); ``percorso`` sempre —
    # senza ``percorso.duration`` esplicita le istanze sono legate e la durata
    # e' l'intervallo verso la prossima, dedotto da arco/passo o dagli onset.
    versions = data.get("versions")
    if isinstance(versions, dict) and "duration" in versions:
        m.replica_duration_source = "versions.duration"
        m.replica_duration = _num(versions.get("duration"))
    percorso = data.get("percorso")
    if isinstance(percorso, dict):
        m.replica_duration_source = m.replica_duration_source or "percorso"

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
                if is_n_env(decl):
                    # n nel tempo: gli stream generati sono quelli del picco
                    n = n_env_peak(decl)
                elif isinstance(decl, int) and not isinstance(decl, bool):
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
            # Catena della entry: la ``duration:`` scritta nella entry (che
            # dopo il merge diventa top-level del documento merged, come
            # ``onset``) vince sulla sua ``base.duration``; entrambe vincono
            # sul default di documento.
            # ``base.duration:`` puntata al primo livello della entry e la
            # forma annidata sono la stessa cosa (``_expand_dotted_keys``).
            entry_base = cfg.get("base") if isinstance(cfg.get("base"), dict) else {}
            sources = [(cfg, "duration"), (entry_base, "duration"),
                       (cfg, "base.duration")]
            declared = any(key in node for node, key in sources)
            dur = next((_num(node[key]) for node, key in sources
                        if key in node and _num(node[key]) is not None), None)
            declares_stack = "stack" in cfg or any(
                isinstance(k, str) and k.startswith("stack.") for k in cfg)
            m.streams[name] = StreamInfo(
                name=name, cfg=cfg, doc_path=("streams", name),
                is_spread=is_spread, spread_n=n,
                duration=dur, declares_duration=declared,
                declares_stack=declares_stack, stack_paths=stack_paths_of(cfg),
                stack_nulled=stack_nulled_of(cfg),
            )
    return m
