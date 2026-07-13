"""Superficie engine PGE vista dal linguaggio degli studi.

Snapshot dichiarativo di bounds, default, finestre, unita' e path YAML del
PythonGranularEngine (fonte: ``docs/reference/yaml.md`` e
``parameter_definitions.py`` dell'engine). gl-ls e' standalone: non importa
l'engine, replica la sua superficie osservabile.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

OUTPUT_SR = 48000


@dataclass(frozen=True)
class ParamInfo:
    """Bounds/default/unita' di un parametro engine (path dotted)."""

    min: Optional[float]
    max: Optional[float]  # None = bound dinamico (es. sample_dur)
    default: Optional[float]
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
    "grain.duration": ParamInfo(1.0 / OUTPUT_SR, 10, 0.05, "s",
        "Durata del singolo grano (con `duration_unit: samples` i valori sono "
        "campioni a 48000 Hz)."),
    "grain.duration_range": ParamInfo(0, 10, None, "±s",
        "Randomizzazione ± della durata per grano."),
    "volume": ParamInfo(-120, 12, 0.0, "dB", "Volume dello stream."),
    "volume_range": ParamInfo(0, 132, None, "±dB", "Randomizzazione ± per grano."),
    "pan": ParamInfo(-3600, 3600, 0.0, "gradi", "0 = centro, ±180 = estremi."),
    "pan_range": ParamInfo(0, 7200, None, "±gradi", "Randomizzazione ± per grano."),
    "pitch.ratio": ParamInfo(0.001, 8, 1.0, "ratio", "Moltiplicatore diretto."),
    "pitch.semitones": ParamInfo(-36, 36, 0.0, "semitoni", "±3 ottave (12-EDO)."),
    "pitch.quarter_tone": ParamInfo(-72, 72, 0.0, "quarti di tono", "24-EDO."),
    "pitch.eighth_tone": ParamInfo(-144, 144, 0.0, "ottavi di tono", "48-EDO."),
    "pitch.cents": ParamInfo(-3600, 3600, 0.0, "cents", "1200-EDO."),
    "pointer.start": ParamInfo(0, None, 0.0, "s",
        "Posizione iniziale di lettura nel sample."),
    "pointer.speed_ratio": ParamInfo(-100, 100, 1.0, "ratio",
        "Velocita' di lettura: 1 normale, -1 indietro, 0 fermo."),
    "pointer.offset_range": ParamInfo(-1, 1, 0.0, "frazione",
        "Deviazione per-grano, scalata e confinata alla finestra di loop."),
    "pointer.loop_start": ParamInfo(0, None, None, "s", "Inizio loop."),
    "pointer.loop_end": ParamInfo(0, None, None, "s", "Fine loop (priorita' su loop_dur)."),
    "pointer.loop_dur": ParamInfo(0.005, None, None, "s", "Durata loop."),
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
DURATION_UNITS = ["seconds", "samples"]

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
