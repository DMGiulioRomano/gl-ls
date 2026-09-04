"""Superficie engine PGE vista dal linguaggio degli studi.

Snapshot dichiarativo di bounds, default, finestre, unita' e path YAML del
PythonGranularEngine (fonte: ``docs/reference/yaml.md`` e
``parameter_definitions.py`` dell'engine). gl-ls e' standalone: non importa
l'engine, replica la sua superficie osservabile.

Il costo di quella scelta e' il drift: la tabella qui sotto va allineata a
mano. Se un giorno lo si vuole chiudere, da PGE v5.1.0 esiste l'API stabile
pensata per questo consumo — ``pge.api.parameter_bounds(output_sr=...,
sample_dur_sec=...)`` (PGE #163), che restituisce i bounds con gli override
dinamici gia' applicati (``grain_duration.min_val = 1/output_sr``, ``loop_*``
limitati a ``sample_dur_sec``). Finche' la scelta standalone resta, quei
bounds dinamici sono fuori portata: vedi "Limiti noti" in
``docs/architettura.md``.

Le chiavi di ``PARAMS`` sono **path YAML**, non nomi del registry engine: e'
la sola grafia che l'engine legge davvero, ed e' quella che un ``path:`` di
``axes``/``spread.over`` deve avere. Dove le due grafie divergono, la seconda
non e' un sinonimo ma un errore muto — vedi ``REGISTRY_SPELLINGS``.

Due bounds qui dentro non sono dell'engine ma di *granulation-studies*, che li
stringe (``VOLUME_MAX_DB``, ``MIN_GRAIN_SAMPLES``): il runtime che valida
questi ``study.yml`` e' quello, quindi la superficie da rispecchiare e' la sua.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Union

OUTPUT_SR = 48000

# Minimo di ``grain.duration`` **in campioni**. Non e' un dato dell'engine, che
# scende a 1 campione (``pge.api.parameter_bounds(output_sr=...)`` porta
# ``grain_duration.min_val`` a ``1/output_sr``): e' un vincolo di *studio*,
# granulation-studies ``bounds.MIN_GRAIN_SAMPLES`` — sotto i 4 campioni il
# grano non ha inviluppo udibile, e ``granstudies sweep`` rifiuta il valore al
# parse invece di renderizzarlo. Vale sempre, anche coi valori scritti in
# secondi: prima il floor dinamico si accendeva solo con una
# ``grain.duration_unit`` dichiarata, e uno studio in secondi passava muto qui
# per poi fallire di la'.
MIN_GRAIN_SAMPLES = 4

#: Il floor di ``grain.duration`` in secondi, alla frequenza di render.
GRAIN_DURATION_MIN = MIN_GRAIN_SAMPLES / OUTPUT_SR

# Tetto di ``volume``. Non e' un dato fisso dell'engine: e' una costante di
# *studio*. granulation-studies (``granstudies/engine_bridge.py``, costante
# ``VOLUME_MAX_DB``) rimpiazza a runtime ``GRANULAR_PARAMETERS["volume"]`` con
# un ``dataclasses.replace`` quando inserisce ``engine/src`` in ``sys.path``,
# e il registry viene riletto a ogni ``get_parameter_definition``: il tetto
# vale quindi per parser, ``pge.api`` e ``granstudies/bounds.py``. Puo'
# cambiare di nuovo — quando succede, si cambia qui (unico punto: la doc
# hover di ``schema.py`` interpola questa costante).
VOLUME_MAX_DB = 24.0


@dataclass(frozen=True)
class ParamInfo:
    """Bounds/default/unita' di un parametro engine (path dotted).

    ``min``/``max`` a ``None`` insieme dicono *nessun bound numerico*: il
    parametro non e' un numero (``grain.envelope`` e' un nome di finestra).
    ``max`` da solo a ``None`` e' il bound dinamico dell'engine (``loop_*``,
    limitati alla durata del sample). ``default`` a ``None`` e' l'assenza di
    default engine, cioe' il baseline obbligatorio in un asse; puo' anche non
    essere un numero, per gli stessi parametri senza bounds.
    """

    min: Optional[float]
    max: Optional[float]
    default: Optional[Union[float, str]]
    unit: str
    doc: str


# path YAML dotted (come compaiono in axes.path e in spread.over) -> info
PARAMS: Dict[str, ParamInfo] = {
    "density": ParamInfo(0.01, 4000, None, "grani/s",
        "Frequenza di emissione dei grani. L'unica altezza del sistema: sotto "
        "~20 Hz ritmo, sopra pitch, in mezzo flutter."),
    "fill_factor": ParamInfo(0.001, 50, 2.0, "adimensionale",
        "density = fill_factor / grain.duration; ha priorita' su density."),
    "distribution": ParamInfo(0, 1, 0.0, "0..1",
        "Distribuzione temporale (modello Truax): 0 = sincrono, 1 = asincrono."),
    "grain.duration": ParamInfo(GRAIN_DURATION_MIN, 10, 0.05, "s",
        "Durata del singolo grano. I bounds sono in secondi: con una "
        "`duration_unit` dichiarata (`samples` = campioni a 48000 Hz, "
        "`milliseconds` = ms) i valori vivono in quell'unita' e si convertono "
        "prima del confronto. Il minimo e' il floor di studio di "
        "`MIN_GRAIN_SAMPLES` campioni, non il campione singolo dell'engine."),
    "grain.duration_range": ParamInfo(0, 10, None, "±s",
        "Randomizzazione ± della durata per grano, nell'unita' di "
        "`grain.duration_unit`."),
    "grain.envelope": ParamInfo(None, None, "hanning", "nome di finestra",
        "Finestra del grano: un nome, non un numero — nessun bound da "
        "confrontare (`variation_mode='choice'`). I nomi ammessi sono in "
        "`WINDOWS`."),
    "grain.reverse": ParamInfo(0, 1, 0.0, "0|1",
        "Verso del grano nella grafia storica: presente-e-vuota = sempre "
        "indietro, assente = `auto` (segue il segno di `pointer.speed_ratio`). "
        "In gruppo esclusivo con `grain.read_direction`: dichiararle entrambe "
        "e' un errore dell'engine."),
    "grain.read_direction": ParamInfo(-1, 1, None, "verso",
        "Verso di lettura interno al grano: -1 indietro, +1 avanti, scalare o "
        "envelope, indipendente dal segno della velocita' della testina. Il "
        "dominio e' il segno — 0 sta nei bounds ma l'engine lo rifiuta. Senza "
        "default engine: in un asse il `baseline` e' obbligatorio."),
    "volume": ParamInfo(-120, VOLUME_MAX_DB, 0.0, "dB",
        "Volume dello stream. Sopra 0 dBFS il renderer non normalizza: il "
        "range positivo e' clipping reale, non headroom."),
    "volume_range": ParamInfo(0, 132, None, "±dB", "Randomizzazione ± per grano."),
    "pan": ParamInfo(-3600, 3600, 0.0, "gradi", "0 = centro, ±180 = estremi."),
    "pan_range": ParamInfo(0, 7200, None, "±gradi", "Randomizzazione ± per grano."),
    "pitch.ratio": ParamInfo(0.001, 8, 1.0, "ratio", "Moltiplicatore diretto."),
    "pitch.semitones": ParamInfo(-36, 36, 0.0, "semitoni", "±3 ottave (12-EDO)."),
    "pitch.quarter_tone": ParamInfo(-72, 72, 0.0, "quarti di tono", "24-EDO."),
    "pitch.eighth_tone": ParamInfo(-144, 144, 0.0, "ottavi di tono", "48-EDO."),
    "pitch.cents": ParamInfo(-3600, 3600, 0.0, "cents", "1200-EDO."),
    "pointer.start": ParamInfo(0, None, 0.0, "s",
        "Posizione iniziale di lettura nel sample, nell'unita' di "
        "`pointer.loop_unit` (default `seconds`: da PGE v9 non eredita da "
        "`time_mode`)."),
    "pointer.speed_ratio": ParamInfo(-100, 100, 1.0, "ratio",
        "Velocita' di lettura: 1 normale, -1 indietro, 0 fermo."),
    "pointer.offset_range": ParamInfo(-1, 1, 0.0, "frazione",
        "Deviazione per-grano, scalata e confinata alla finestra di loop."),
    "pointer.loop_start": ParamInfo(0, None, None, "s",
        "Inizio loop, nell'unita' di `pointer.loop_unit`."),
    "pointer.loop_end": ParamInfo(0, None, None, "s",
        "Fine loop (priorita' su loop_dur), nell'unita' di `pointer.loop_unit`."),
    "pointer.loop_dur": ParamInfo(0.005, None, None, "s",
        "Durata loop, nell'unita' di `pointer.loop_unit`."),
    "voices.num_voices": ParamInfo(1, 256, 1, "voci", "Numero di voci."),
    "voices.scatter": ParamInfo(0, 1, 0.0, "0..1",
        "0 = voci sincrone sullo stesso IOT, 1 = IOT indipendenti."),
    "onset": ParamInfo(0, None, None, "s", "Tempo di inizio assoluto dello stream."),
    "duration": ParamInfo(0, None, None, "s", "Durata dello stream."),
}

# Path con default engine assente: baseline obbligatorio in un asse.
NEEDS_BASELINE = frozenset(
    p for p, info in PARAMS.items() if info.default is None
) | frozenset({"pitch"})


def bounds_for(path: str) -> Optional[Tuple[Optional[float], Optional[float]]]:
    info = PARAMS.get(path)
    if info is None and (path == "pitch" or path.startswith("pitch.")):
        return None
    return (info.min, info.max) if info else None


def needs_baseline(path: str) -> bool:
    if path == "pitch" or path.startswith("pitch."):
        return True
    info = PARAMS.get(path)
    return info is not None and info.default is None


def fmt_default(info: ParamInfo) -> str:
    """Il default di un parametro come testo: numero, nome, o assenza."""
    if info.default is None:
        return "—"
    if isinstance(info.default, str):
        return f"`{info.default}`"
    return f"{info.default:g}"


def bounds_phrase(info: ParamInfo) -> str:
    """``bounds [lo, hi] unit``, o la frase di chi bounds numerici non ne ha."""
    if info.min is None and info.max is None:
        return f"{info.unit} — nessun bound numerico"
    lo = "-∞" if info.min is None else f"{info.min:g}"
    hi = "∞" if info.max is None else f"{info.max:g}"
    return f"bounds [{lo}, {hi}] {info.unit}"


def grain_floor_note() -> str:
    """Perche' ``grain.duration`` ha quel minimo, detto una volta sola.

    Un valore sotto il floor e' *renderizzabile* — l'engine scende a un
    campione — e viene rifiutato lo stesso: il messaggio deve dire di chi e'
    il vincolo, altrimenti sembra un limite dell'engine e si va a cercarlo
    dove non c'e'."""
    return (f"Il minimo e' {MIN_GRAIN_SAMPLES} campioni a {OUTPUT_SR} Hz "
            f"({GRAIN_DURATION_MIN:g} s): e' un vincolo di studio, non "
            f"dell'engine — che scende a 1 campione — perche' sotto i "
            f"{MIN_GRAIN_SAMPLES} campioni il grano non ha inviluppo udibile.")


# ---------------------------------------------------------------------------
# Grafie di *registry* che non sono chiavi YAML.
#
# ``granstudies.bounds`` indicizza i bounds col nome che il parametro ha nel
# registry dell'engine (``GRANULAR_PARAMETERS``), e per tre parametri quel
# nome non coincide con la chiave dove il valore va scritto nello stream:
# ``num_voices``/``scatter`` vivono dentro il blocco ``voices:``
# (``pge.core.stream._init_voice_manager``), e ``pointer_deviation`` non ha
# affatto una chiave propria — si dichiara come ``offset_range`` dentro
# ``pointer:`` (``POINTER_PARAMETER_SCHEMA``, ``range_path='offset_range'``).
#
# Scritte come path in ``axes``/``spread.over`` producono un override che
# atterra dove l'engine non guarda: nessuno dei due runtime protesta, il
# render gira, e il parametro resta al default. E' il caso peggiore — muto —
# quindi qui ha una diagnostica sua invece del generico ``unknown-path``.
REGISTRY_SPELLINGS: Dict[str, str] = {
    "num_voices": "voices.num_voices",
    "scatter": "voices.scatter",
    "pointer.deviation": "pointer.offset_range",
}


# ---------------------------------------------------------------------------
# Finestre grain.envelope
WINDOWS: Dict[str, str] = {
    "hanning": "Hanning/von Hann (default). Estremi nulli.",
    "hamming": "Hamming. Estremi a 0.08 (buona per grani ultra-corti).",
    "bartlett": "Bartlett/Triangle (alias: triangle).",
    "triangle": "Alias di bartlett.",
    "blackman": "Blackman.",
    "blackman_harris": "Blackman-Harris.",
    "gaussian": "Gaussiana.",
    "kaiser": "Kaiser-Bessel.",
    "rectangle": "Rettangolare/Dirichlet (piatta: utile per grani di 1-3 campioni).",
    "sinc": "Sinc.",
    "half_sine": "Semi-sinusoide.",
    "expodec": "Decadimento esponenziale (Roads-style), parte da 1.0.",
    "expodec_strong": "Decadimento esponenziale forte.",
    "exporise": "Salita esponenziale.",
    "exporise_strong": "Salita esponenziale forte.",
    "rexpodec": "Decadimento esponenziale inverso.",
    "rexporise": "Salita esponenziale inversa.",
    "all": "Espande a tutte le finestre disponibili.",
}

CHORDS = [
    "maj", "min", "dim", "aug", "sus2", "sus4",
    "dom7", "maj7", "min7", "dim7", "minmaj7",
    "dom9", "maj9", "min9", "9sus4",
    "dom9s11", "maj9s11", "min11",
    "dom13", "min13", "maj13s11", "altered",
]

INTERPOLATIONS = ["linear", "cubic", "step"]
SWEEP_MODES = ["discrete", "envelope", "both"]
DISTRIBUTIONS = ["uniform", "gaussian"]
TIME_MODES = ["absolute", "normalized"]
CLIP_STRATEGIES = ["overflow_margin", "passthrough"]
# Unita' di ``grain.duration``/``grain.duration_range``
# (``pge.core.stream.GRAIN_DURATION_UNITS``, granstudies
# ``bounds.GRAIN_DURATION_UNITS``). ``milliseconds`` entra con PGE v5.2.0.
DURATION_UNITS = ["seconds", "samples", "milliseconds"]

MS_PER_SECOND = 1000.0

# ---------------------------------------------------------------------------
# Posizioni nel sample: ``pointer.loop_unit`` (engine #222, PGE v9).

# Vocabolario chiuso di ``pointer.loop_unit``
# (``pge.controllers.pointer_controller.LOOP_UNITS``, granstudies
# ``bounds.LOOP_UNITS``). ``seconds`` e' la grafia canonica — allinea
# ``loop_unit`` a ``grain.duration_unit`` — e ``absolute`` l'alias storico:
# stessa lettura, valori gia' in secondi assoluti. Fuori di qui l'engine alza
# ``InvalidFieldValueError``: prima «tutto cio' che non e' normalized» valeva
# assoluto, e un refuso passava muto.
LOOP_UNITS = ["seconds", "absolute", "normalized"]

# L'unita' che vale quando ``loop_unit`` e' assente. Da PGE v9 **non** eredita
# piu' da ``time_mode`` (granstudies ``bounds.LOOP_UNIT_DEFAULT``): le due
# chiavi governano assi diversi con riferimenti diversi — ``time_mode`` scala
# l'asse X (tempo) degli envelope sulla duration dello stream, ``loop_unit``
# l'asse Y (valore) sulla durata del file audio.
LOOP_UNIT_DEFAULT = "seconds"

# Le chiavi del blocco pointer che ``loop_unit`` interpreta
# (``_LOOP_UNIT_SCOPE`` del PointerController, granstudies
# ``diagnostics.LOOP_UNIT_SCOPE``). ``start`` e' fra queste benche' loop non
# sia: e' una posizione nel sample come ``loop_start``, stesso dominio e
# stessa unita'.
LOOP_UNIT_SCOPE = ("start", "loop_start", "loop_end", "loop_dur")

# ---------------------------------------------------------------------------
# Verso di lettura del grano: ``grain.read_direction`` (PGE #207).

# I due soli valori dichiarabili (``READ_DIRECTION_VALUES`` dell'engine): un
# insieme, non un intervallo. Arrotondare al segno significherebbe accettare
# una scrittura e renderizzarne un'altra, e lo 0 non ha una risposta non
# arbitraria.
READ_DIRECTION_VALUES = (-1.0, 1.0)

# L'unica interpolazione ammessa, e quella imposta dalla chiave
# (``REQUIRED_INTERP``): il verso ha due stati, non una rampa fra i due.
READ_DIRECTION_INTERP = "step"

# ---------------------------------------------------------------------------
# ``deviation_probability``: le chiavi della forma per-parametro.

# I ``deviation_probability_key`` dichiarati nel registry dell'engine
# (``parameters/parameter_schema.py`` piu' ``pitch`` dal PitchController).
# ``reverse`` e ``read_direction`` sono due chiavi distinte: la prima e' la
# probabilita' di ribaltare ``grain.reverse``, la seconda quella di ribaltare
# il verso dichiarato con ``grain.read_direction``.
DEVIATION_PROBABILITY_KEYS = [
    "volume", "pan", "duration", "envelope", "reverse", "read_direction",
    "pointer", "pitch",
]

# Nome dei valori attesi per ogni unita', per i messaggi di diagnostica
# (granstudies ``study_spec._UNIT_LABELS``).
GRAIN_UNIT_LABELS: Dict[str, str] = {
    "seconds": "s", "samples": "campioni", "milliseconds": "ms",
}


def grain_duration_factor(unit: Optional[str], output_sr: int = OUTPUT_SR) -> float:
    """Fattore che porta un valore di ``grain.duration`` in secondi.

    Unico posto che sa quanto vale un'unita' (granstudies
    ``bounds.grain_duration_factor``): ``seconds`` (o unita' assente/ignota)
    -> 1.0; ``milliseconds`` -> 1e-3; ``samples`` -> ``1/output_sr``, l'unica
    che dipende dal sample rate.
    """
    if unit == "milliseconds":
        return 1.0 / MS_PER_SECOND
    if unit == "samples":
        return 1.0 / output_sr
    return 1.0


def unit_note(n: float, unit: Optional[str]) -> str:
    """Glossa da mettere accanto a un valore espresso in ``unit`` non-secondi.

    ``650 ms`` non si legge come ``0.65 s`` a occhio: il messaggio di bounds
    porta entrambi i numeri."""
    factor = grain_duration_factor(unit)
    if factor == 1.0:
        return ""
    label = GRAIN_UNIT_LABELS.get(unit or "", unit or "")
    extra = f" a {OUTPUT_SR} Hz" if unit == "samples" else ""
    return f" ({n:g} {label}{extra})"

# ---------------------------------------------------------------------------
# Unita' della camminata-X (registro X_UNITS di granstudies).
# Famiglie semantiche: rate (hz, bpm = hz*60) e periodo (s).
X_UNITS: Dict[str, str] = {
    "hz": "frequenza di generazione: il punto successivo cade a t + 1/f",
    "s": "periodo in secondi: il punto successivo cade a t + p",
    "bpm": "battiti al minuto: il punto successivo cade a t + 60/v",
}
RATE_UNITS = frozenset({"hz", "bpm"})


def unit_convert_value(v: float, src: str, dst: str) -> float:
    """Converte un *valore puntuale* di banda tra unita' X.

    hz<->bpm e' un riscalamento nello spazio-rate; il passaggio rate<->periodo
    e' il reciproco (1/f). Attenzione: sui *bordi di banda* la conversione
    rate<->periodo inverte l'ordine (vedi ``convert.convert_band``).
    """
    if src == dst:
        return v
    hz = {"hz": lambda x: x, "bpm": lambda x: x / 60.0, "s": lambda x: 1.0 / x}[src](v)
    return {"hz": lambda x: x, "bpm": lambda x: x * 60.0, "s": lambda x: 1.0 / x}[dst](hz)


def density_zone(v: float) -> str:
    """Descrizione percettiva di un valore di density (continuum Truax)."""
    if v < 8:
        return "zona ritmica: eventi contabili, pulsazione"
    if v < 20:
        return "zona di transizione ritmo→flutter (~8–20 g/s)"
    if v < 50:
        return "flutter: granulosita' percepita, fusione incompleta"
    return "banda audio: fusione in tessitura/pitch percepito"


# path proponibili per axes.<asse>.path e spread.over
AXIS_PATHS = sorted(PARAMS.keys())


def known_paths() -> frozenset:
    """Tutti i path engine dotted noti (granstudies ``bounds.known_paths``)."""
    return frozenset(PARAMS)


def split_axis_key(
    dotted: str, axis_names=frozenset()
) -> Tuple[str, Tuple[str, ...], Optional[Tuple[str, ...]]]:
    """(asse, resto, ambigui) — confine del nome d'asse in una chiave dotted.

    Rispecchia granstudies ``spread.split_axis_key``: sotto ``axes.``/``stack.``
    il primo identificatore e' un nome d'asse il cui confine si risolve con
    precedenza (1) assi dichiarati nel documento base, (2) registro parametri
    engine (un override puo' introdurre un asse dotted non dichiarato),
    (3) fallback sintattico al primo segmento (chiavi riservate, alias senza
    punto). Piu' match nello stesso livello — es. assi ``grain`` e
    ``grain.duration`` entrambi dichiarati — sono indecidibili: il terzo
    elemento porta i nomi in conflitto (altrimenti ``None``).
    """
    segs = dotted.split(".")
    spans = range(1, len(segs) + 1)
    for names in (frozenset(axis_names), known_paths()):
        candidates = [j for j in spans if ".".join(segs[:j]) in names]
        if len(candidates) > 1:
            ambiguous = tuple(".".join(segs[:j]) for j in candidates)
            j = candidates[-1]
            return ".".join(segs[:j]), tuple(segs[j:]), ambiguous
        if candidates:
            j = candidates[0]
            return ".".join(segs[:j]), tuple(segs[j:]), None
    return segs[0], tuple(segs[1:]), None
