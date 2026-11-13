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

Un bound qui dentro non e' dell'engine ma di *granulation-studies*, che lo
alza (``VOLUME_MAX_DB``): il runtime che valida questi ``study.yml`` e' quello,
quindi la superficie da rispecchiare e' la sua.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional, Tuple, Union

OUTPUT_SR = 48000

#: Il floor di ``grain.duration`` in secondi: **un campione** alla frequenza di
#: render, il minimo dinamico dell'engine (``get_parameter_definition(
#: "grain_duration", output_sr=...)`` porta ``min_val`` a ``1/output_sr``; il
#: ``0.001`` statico del registry non vale a runtime). Fino a gl-ls #47 qui
#: c'era un floor di *studio* di 4 campioni (granulation-studies
#: ``bounds.MIN_GRAIN_SAMPLES``), che granulation-studies ha tolto
#: (mare-nostrum da95f26): ``bounds_for("grain.duration")`` restituisce ora il
#: minimo dell'engine senza rialzo. Vale sempre, anche coi valori scritti in
#: secondi — non solo con una ``grain.duration_unit`` dichiarata.
GRAIN_DURATION_MIN = 1 / OUTPUT_SR

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
        "prima del confronto. Il minimo e' un campione, quello dell'engine."),
    "grain.duration_range": ParamInfo(0, 1, None, "±s",
        "Randomizzazione ± della durata per grano, nell'unita' di "
        "`grain.duration_unit`. La banda ha bounds suoi, molto piu' stretti "
        "del valore: 1 s, non i 10 s di `grain.duration`. Con "
        "`grain.duration_range_unit: relative` (PGE #267) e' invece una "
        "frazione della durata base, adimensionale, in [0, 1]."),
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
    "volume_range": ParamInfo(0, 24, None, "±dB",
        "Randomizzazione ± per grano. Il tetto e' il `max_range` dell'engine, "
        "che vale 24 dB per conto suo: che il numero sia lo stesso di "
        "`VOLUME_MAX_DB` — il `max_val`, e quello viene da granstudies — non "
        "li lega, e legarli romperebbe il giorno in cui lo studio alza il "
        "tetto del volume."),
    "pan": ParamInfo(-3600, 3600, 0.0, "gradi", "0 = centro, ±180 = estremi."),
    "pan_range": ParamInfo(0, 360, None, "±gradi",
        "Randomizzazione ± per grano: un giro, mentre il valore arriva a "
        "±3600 (dieci giri)."),
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
    "pointer.offset_range": ParamInfo(0, 1, 0.0, "frazione",
        "Deviazione per-grano, scalata e confinata alla finestra di loop. E' "
        "la *banda* di `pointer_deviation`, il cui valore non ha una chiave "
        "YAML (`yaml_path='_dummy_fixed_zero_'`): il dominio dichiarabile e' "
        "[0, 1], non il [-1, 1] del valore."),
    "pointer.loop_start": ParamInfo(0, None, None, "s",
        "Inizio loop, nell'unita' di `pointer.loop_unit`."),
    "pointer.loop_end": ParamInfo(0, None, None, "s",
        "Fine loop (priorita' su loop_dur), nell'unita' di `pointer.loop_unit`."),
    "pointer.loop_dur": ParamInfo(0.005, None, None, "s",
        "Durata loop, nell'unita' di `pointer.loop_unit`."),
    "voices.num_voices": ParamInfo(1, 256, 1, "voci", "Numero di voci."),
    "voices.scatter": ParamInfo(0, 1, 0.0, "0..1",
        "0 = voci sincrone sullo stesso IOT, 1 = IOT indipendenti."),
    "grain.iot": ParamInfo(1 / OUTPUT_SR, 100, None, "s",
        "Attesa fino al grano successivo (PGE #311): il terzo modo accanto a "
        "`density` e `fill_factor`, scelto per presenza della chiave. Con lei "
        "la densita' non si decide, emerge dagli onset. Da un campione a "
        "100 s, in **secondi**: con una `grain.duration_unit` dichiarata il "
        "valore vive in quell'unita' e si converte prima del confronto. "
        "Esclusiva con `density`, `fill_factor` e `distribution`: insieme "
        "sono un errore dell'engine, non una priorita'."),
    "pointer.position": ParamInfo(0, 1, None, "frazione della finestra",
        "Posizione di lettura scritta (PGE #312), da 0 a 1 della finestra "
        "attiva: la finestra di loop se c'e', altrimenti il file. Fuori da "
        "0–1 **rientra a capo** (`1.25` e' `0.25`): non e' un errore. Sta al "
        "posto di `speed_ratio` e `start`, e `loop_unit` non la riscala."),
    "onset": ParamInfo(0, None, None, "s", "Tempo di inizio assoluto dello stream."),
    "duration": ParamInfo(0, None, None, "s", "Durata dello stream."),
}

# ---------------------------------------------------------------------------
# Provenienza: da dove viene ogni riga di ``PARAMS``.
#
# La domanda di gl-ls #43 — «lo snapshot regge?» — non si risponde una volta:
# si risponde ogni volta che l'engine si muove, e per rispondere serve sapere
# *contro cosa* va confrontata ciascuna riga. Il primo giro l'aveva chiesto a
# granstudies, che pero' indicizza dodici path su ventisette: nei quindici che
# restavano fuori sono rimasti per un giro quattro bounds sbagliati, tutti
# nella direzione peggiore (l'editor muto su cio' che il parser rifiuta).
#
# Questa mappa e' quel termine di paragone, dichiarato accanto ai numeri
# invece che dentro un test: ``test_snapshot_granstudies.py`` la percorre
# tutta e pretende che sia **totale** su ``PARAMS``, cosi' un path nuovo non
# puo' entrare senza dire da dove vengono i suoi numeri.


@dataclass(frozen=True)
class Origin:
    """Il termine di paragone dei bounds di un path.

    ``kind``:

    - ``"registry"`` — ``GRANULAR_PARAMETERS[name]`` dell'engine. ``slot``
      sceglie *quale* coppia: ``"value"`` e' ``min_val``/``max_val``,
      ``"range"`` e' ``min_range``/``max_range``. Sono numeri diversi per lo
      stesso parametro, e una chiave ``_range`` si confronta col secondo — la
      banda di ``volume`` si ferma a 24 dB mentre il valore copre i 144 fra
      -120 e +24, quella di ``pan`` fa un giro dove il valore ne fa dieci.
    - ``"pitch"`` — ``make_pitch_unit(name).value_bounds()``: il pitch e'
      unit-driven e nel registry non c'e'
      (``PITCH_PARAMETER_SCHEMA`` e' vuoto).
    - ``"studio"`` — l'engine non ha niente da confrontare e ``note`` dice
      perche'. Non e' una scusa: e' la dichiarazione che quel numero e' nostro
      e che il drift, li', non esiste per definizione.
    """

    kind: str
    name: str = ""
    slot: str = "value"
    note: str = ""


def _reg(name: str, slot: str = "value") -> Origin:
    return Origin("registry", name, slot)


ORIGINS: Dict[str, Origin] = {
    "density": _reg("density"),
    "fill_factor": _reg("fill_factor"),
    "distribution": _reg("distribution"),
    "grain.duration": _reg("grain_duration"),
    "grain.duration_range": _reg("grain_duration", "range"),
    "grain.envelope": _reg("grain_envelope"),
    "grain.reverse": _reg("reverse"),
    "grain.read_direction": _reg("read_direction"),
    "volume": _reg("volume"),
    "volume_range": _reg("volume", "range"),
    "pan": _reg("pan"),
    "pan_range": _reg("pan", "range"),
    "pitch.ratio": Origin("pitch", "ratio"),
    "pitch.semitones": Origin("pitch", "semitones"),
    "pitch.quarter_tone": Origin("pitch", "quarter_tone"),
    "pitch.eighth_tone": Origin("pitch", "eighth_tone"),
    "pitch.cents": Origin("pitch", "cents"),
    "pointer.speed_ratio": _reg("pointer_speed_ratio"),
    # Il *valore* di ``pointer_deviation`` non ha una chiave YAML
    # (``yaml_path='_dummy_fixed_zero_'``): l'unica meta' dichiarabile e' la
    # banda, e i suoi bounds sono ``min_range``/``max_range``.
    "pointer.offset_range": _reg("pointer_deviation", "range"),
    "pointer.loop_start": _reg("loop_start"),
    "pointer.loop_end": _reg("loop_end"),
    "pointer.loop_dur": _reg("loop_dur"),
    "voices.num_voices": _reg("num_voices"),
    "voices.scatter": _reg("scatter"),
    "grain.iot": _reg("grain_iot"),
    "pointer.position": _reg("pointer_position"),
    "pointer.start": Origin("studio", note=
        "``pointer_start`` e' ``is_smart=False``: valore raw, l'engine non gli "
        "applica bounds. Il minimo a 0 e' nostro — una posizione in un file "
        "non e' negativa — e resta l'unico posto dove gl-ls e' piu' stretto "
        "del runtime."),
    "onset": Origin("studio", note=
        "Campo di ``StreamContext``, non parametro del registry: nessun bound "
        "engine. Il minimo a 0 e' l'origine della timeline."),
    "duration": Origin("studio", note=
        "Come ``onset``: campo di contesto, non parametro."),
}

# Path con default engine assente: baseline obbligatorio in un asse.
NEEDS_BASELINE = frozenset(
    p for p, info in PARAMS.items() if info.default is None
) | frozenset({"pitch"})


def bounds_for(path: str, range_unit: Optional[str] = None,
               ) -> Optional[Tuple[Optional[float], Optional[float]]]:
    """I bounds di un path engine; ``range_unit`` come in ``info_for``."""
    info = info_for(path, range_unit=range_unit)
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

# Seconda meta' della stessa divergenza, sui *numeri* invece che sul nome.
# Indicizzando ``pointer.deviation`` sul registry, granstudies ne legge
# ``min_val``/``max_val`` — i bounds del **valore**, che pero' una chiave YAML
# non ce l'ha (``yaml_path='_dummy_fixed_zero_'``). L'unica meta' dichiarabile
# e' la banda ``pointer.offset_range``, e i suoi bounds sono
# ``min_range``/``max_range``: [0, 1], non [-1, 1]. Il runtime accetta quindi
# una deviazione negativa che il suo stesso engine rifiuta al parse.
#
# Dichiarata qui, e non nascosta in un `!=` del test, per la stessa ragione di
# ``REGISTRY_SPELLINGS``: il giorno in cui granstudies legge lo slot giusto la
# verifica cade, e la voce si toglie da qui.
RUNTIME_VALUE_FOR_RANGE = frozenset({"pointer.deviation"})


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
# La banda dei ``_range`` (``StreamConfig`` di PGE v9, ``docs/reference/yaml.md``
# «La banda dei ``_range``»): due assi ortogonali, entrambi a vocabolario
# chiuso. ``distribution_mode`` e' la *forma* (``DistributionFactory.modes()``,
# fuori di qui ``StrategyNotFoundError``) e omonima per caso della
# ``distribution`` di una banda di studio, che pesca da un altro vocabolario;
# ``range_anchor`` e' dove cade il valore base dentro la banda
# (``RANGE_ANCHORS``, fuori di qui ``InvalidFieldValueError``).
DISTRIBUTION_MODES = ["uniform", "gaussian"]
RANGE_ANCHORS = ["center", "min"]
# Unita' di ``grain.duration``/``grain.duration_range``
# (``pge.core.stream.GRAIN_DURATION_UNITS``, granstudies
# ``bounds.GRAIN_DURATION_UNITS``). ``milliseconds`` entra con PGE v5.2.0.
DURATION_UNITS = ["seconds", "samples", "milliseconds"]

MS_PER_SECOND = 1000.0

# ---------------------------------------------------------------------------
# Posizioni nel sample: ``pointer.loop_unit`` (engine #222, PGE v9).
#
# I due nomi stavano in ``controllers/pointer_controller.py``, e lo scope era
# privato (``_LOOP_UNIT_SCOPE``). PGE #246 ha registrato che tre repository li
# leggevano e li ha spostati in ``parameters/loop_unit.py``, un modulo senza
# dipendenze fatto apposta per essere letto, togliendo l'underscore a cio' che
# era privato di nome e non di fatto. Qui il mirror e' statico e nessun test
# legge il motore, quindi lo spostamento non rompe niente: cambia il posto da
# guardare quando questi valori vanno riconfrontati a mano.

# Vocabolario chiuso di ``pointer.loop_unit``
# (``pge.parameters.loop_unit.LOOP_UNITS``, granstudies
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
# (``pge.parameters.loop_unit.LOOP_UNIT_SCOPE``, granstudies
# ``diagnostics.LOOP_UNIT_SCOPE``). ``start`` e' fra queste benche' loop non
# sia: e' una posizione nel sample come ``loop_start``, stesso dominio e
# stessa unita'.
LOOP_UNIT_SCOPE = ("start", "loop_start", "loop_end", "loop_dur")

#: I path engine delle posizioni nel sample: quelli la cui unita' non e' un
#: fatto del parametro ma di ``loop_unit``.
POSITION_PATHS = frozenset(f"pointer.{k}" for k in LOOP_UNIT_SCOPE)

#: L'unita' di una posizione sotto ``loop_unit: normalized``: una frazione
#: della durata del **sample** — non della ``duration`` dello stream, che e'
#: il riferimento dell'asse X degli envelope, non del valore.
NORMALIZED_POSITION_UNIT = "frazione della durata del sample"


def info_for(dotted: str, loop_unit: Optional[str] = None,
             range_unit: Optional[str] = None) -> Optional[ParamInfo]:
    """La riga di ``PARAMS`` letta con le unita' in vigore.

    Lo snapshot dichiara le posizioni in secondi, che e' il default: con
    ``loop_unit: normalized`` lo stesso numero e' una frazione del sample, e
    un hover che dicesse «s» su ``loop_end: 0.36`` affermerebbe il falso.
    Li' solo l'unita' cambia: i bounds restano quelli dichiarati, il massimo
    dinamico (la durata del sample) non si confronta comunque.

    ``range_unit`` e' la grafia della ``<param>_range_unit`` che governa la
    banda ``dotted`` (``RANGE_UNIT_PATHS``). Sotto ``relative`` cambiano
    unita' **e** bounds: il dominio relativo sostituisce quello assoluto
    (``relative_range_bounds`` dell'engine), non lo restringe."""
    info = PARAMS.get(dotted)
    if info is None:
        return None
    if dotted in RANGE_UNIT_PATHS and range_unit_is_relative(range_unit):
        lo, hi = RELATIVE_RANGE_BOUNDS
        return replace(info, min=lo, max=hi, unit=RELATIVE_RANGE_UNIT)
    if dotted not in POSITION_PATHS or loop_unit != "normalized":
        return info
    return replace(info, unit=NORMALIZED_POSITION_UNIT)

# ---------------------------------------------------------------------------
# L'unita' della banda: ``<param>_range_unit`` (PGE #267).
#
# Con ``relative`` il numero scritto nella banda non e' piu' una larghezza
# nell'unita' del parametro, ma una **frazione del valore base** letta istante
# per istante: banda ``frazione × |base(t)|``. Mirror di
# ``pge.parameters.parameter_definitions`` (``RANGE_UNITS``,
# ``RANGE_UNIT_DEFAULT``, ``RELATIVE_RANGE_BOUNDS``, ``range_unit_is_relative``)
# e di ``ParameterSpec.range_unit_path``; ``test_snapshot_engine_range_unit.py``
# li confronta col motore quando c'e'.

RANGE_UNIT_ABSOLUTE = "absolute"
RANGE_UNIT_RELATIVE = "relative"

#: Grafie ammesse, la prima canonica. Fuori di qui (la chiave **vuota**
#: compresa: l'engine distingue assente da nullo) e' ``InvalidFieldValueError``.
RANGE_UNITS = (RANGE_UNIT_ABSOLUTE, RANGE_UNIT_RELATIVE)

#: Chiave assente: assoluto, la lettura storica bit per bit.
RANGE_UNIT_DEFAULT = RANGE_UNIT_ABSOLUTE

#: Dominio della banda relativa. E' della **modalita'**, non del parametro: che
#: coincida col ``max_range`` assoluto di ``grain_duration`` (1 s) e' una
#: coincidenza numerica che l'engine dichiara come tale — alzarne uno non alza
#: l'altro, e per questo qui sono due numeri e non uno.
RELATIVE_RANGE_BOUNDS = (0.0, 1.0)

#: L'unita' di una banda relativa, come la dicono hover e diagnostica.
RELATIVE_RANGE_UNIT = "frazione della base"

#: Banda (path YAML) -> chiave che ne dichiara l'unita' (path YAML). Mirror di
#: ``ParameterSpec.range_path`` -> ``range_unit_path``: oggi un parametro solo,
#: l'unico la cui base spazia per costruzione su piu' ordini di grandezza.
RANGE_UNIT_PATHS: Dict[str, str] = {
    "grain.duration_range": "grain.duration_range_unit",
}


def range_unit_is_relative(unit: object) -> bool:
    """True se la grafia dichiara una banda relativa.

    Lettura **pura**, come quella dell'engine: una grafia sbagliata legge come
    non-relativa, e dire che e' sbagliata tocca a chi la valida."""
    return unit == RANGE_UNIT_RELATIVE

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


# ---------------------------------------------------------------------------
# I tre modi della densita' e le due leggi di moto del puntatore (PGE #311,
# #312): esclusivita' per **presenza** della chiave, non priorita'.

#: Le chiavi che non convivono con ``grain.iot``
#: (``pge.controllers.density_controller.IOT_EXCLUSIVE_KEYS``): anche
#: ``distribution: 0``, anche una ``grain.iot:`` lasciata vuota.
IOT_EXCLUSIVE_KEYS = ("density", "fill_factor", "distribution")

#: Le chiavi di ``pointer:`` che non convivono con ``position``
#: (``pge.controllers.pointer_controller.POSITION_EXCLUSIVE_KEYS``).
POSITION_EXCLUSIVE_KEYS = ("speed_ratio", "start")

#: I path i cui bounds **avvolgono** invece di tagliare
#: (``WRAPPING_PARAMETERS`` del motore, ``('pointer_position',)``): un valore
#: finito fuori dai bounds rientra a capo ed e' valido; un non-finito resta un
#: errore di bounds.
WRAPPING_PATHS = frozenset({"pointer.position"})


# ---------------------------------------------------------------------------
# ``maps:`` (PGE #308, #310, #313): le mappe iterate di uno stream.

#: I tipi del catalogo (``pge.maps.catalog.MAP_TYPES``), piu' ``custom``.
MAP_TYPES = ("logistic", "tent", "sine", "cubic", "henon", "circle")
MAP_TYPE_CUSTOM = "custom"
MAP_TYPE_VALUES = MAP_TYPES + (MAP_TYPE_CUSTOM,)

#: Le chiavi di una mappa (``pge.maps.map_set.MAP_KEYS``).
MAP_KEYS = ("type", "r", "clock", "iterate", "x0", "transient", "y0", "x", "y")

#: ``clock: grain``: un passo per grano, il default.
MAP_CLOCK_GRAIN = "grain"

#: Tetti al caricamento (``MAP_ITERATE_MAX``, ``MAP_TRANSIENT_MAX``) e il
#: transitorio di default (``MAP_TRANSIENT_DEFAULT``).
MAP_ITERATE_MAX = 40
MAP_TRANSIENT_MAX = 100_000
MAP_TRANSIENT_DEFAULT = 300

#: Lo stato iniziale di una ``custom`` (``MAP_CUSTOM_X0``/``MAP_CUSTOM_Y0``).
MAP_CUSTOM_X0 = 0.1
MAP_CUSTOM_Y0 = 0.1


@dataclass(frozen=True)
class MapKindInfo:
    """Cio' che il catalogo dichiara di un tipo (``MAP_KINDS``)."""
    x0: float
    r_range: Tuple[float, float]
    value_range: Tuple[float, float]
    variables: int = 1
    y0: float = 0.0
    y_range: Optional[Tuple[float, float]] = None
    sin_based: bool = False


MAP_KINDS: Dict[str, MapKindInfo] = {
    "logistic": MapKindInfo(0.3, (2.5, 4.0), (0.0, 1.0)),
    "tent": MapKindInfo(0.3, (2.5, 3.999), (0.0, 1.0)),
    "sine": MapKindInfo(0.1, (0.0, 4.0), (-1.0, 1.0), sin_based=True),
    "cubic": MapKindInfo(0.3, (1.5, 3.0), (-1.2, 1.2)),
    "henon": MapKindInfo(0.1, (0.8, 1.4), (-1.3, 1.4), variables=2, y0=0.1,
                         y_range=(-0.39, 0.42)),
    "circle": MapKindInfo(0.2, (0.0, 1.0), (0.0, 1.0), sin_based=True),
}

#: Un nome di mappa: lettere, cifre e ``_``, non una cifra in testa.
MAP_NAME_PATTERN = r"[A-Za-z_][A-Za-z_0-9]*\Z"


def reserved_map_names() -> frozenset:
    """Nomi che una mappa non puo' prendere (``RESERVED_MAP_NAMES``): in
    un'espressione sono gia' una funzione, una costante, il tempo, o una
    variabile dell'equazione di una mappa."""
    from . import engine_expr as EX
    return (frozenset(EX.FUNCTIONS) | frozenset(EX.CONSTANTS)
            | frozenset({EX.TIME_NAME}) | frozenset(EX.MAP_EQUATION_VARIABLES))


def map_kind_doc(name: str) -> Optional[str]:
    """Una riga di hover per un tipo del catalogo."""
    if name == MAP_TYPE_CUSTOM:
        return ("**custom** — l'equazione si scrive nello YAML: `x:` "
                "(obbligatoria) e `y:` (seconda variabile, facoltativa), nel "
                "linguaggio delle espressioni con le variabili `x`, `y`, `r`, "
                "senza le parentesi esterne. `x0`/`y0` di default "
                f"{MAP_CUSTOM_X0:g}; `r` serve solo se un'equazione lo legge. "
                "L'intervallo del valore dipende dall'equazione.")
    k = MAP_KINDS.get(name)
    if k is None:
        return None
    lo, hi = k.value_range
    rlo, rhi = k.r_range
    text = (f"**{name}** — valore in [{lo:g}, {hi:g}], `r` in "
            f"[{rlo:g}, {rhi:g}], `x0` {k.x0:g}.")
    if k.variables == 2 and k.y_range:
        text += (f" Due variabili: la seconda si legge come `<nome>.y`, in "
                 f"[{k.y_range[0]:g}, {k.y_range[1]:g}], `y0` {k.y0:g}.")
    if k.sin_based:
        text += (" Passa da `sin`: fra due macchine i grani possono "
                 "divergere.")
    return text
