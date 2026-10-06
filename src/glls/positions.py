"""Le posizioni nel sample, e cosa valgono in secondi (gl-ls #48).

``pointer.start``/``loop_start``/``loop_end``/``loop_dur`` sono posizioni
nello stesso dominio, e la loro unita' la dice ``pointer.loop_unit``: in
secondi (il default) il numero si legge da se', ``normalized`` e' una frazione
della durata del **sample** — e ``loop_end: 0.363636363636`` resta
illeggibile finche' qualcuno non fa la moltiplicazione.

Il riferimento e' la durata del sample, **non** ``base.duration``: e' la
distinzione che fa ``granstudies.gainmap`` (``pos = start * n_frames`` sotto
``normalized``, ``start * sr`` altrimenti), e sbagliarla darebbe un numero
plausibile e falso. La durata si legge dall'header del file
(:mod:`glls.audioinfo`), risolto come fa la navigazione: ``samples_dir``
cercato risalendo dalla cartella dello studio (``navigation.find_samples_dir``).

Una posizione non vive solo in un blocco ``pointer:``. Le stesse chiavi
arrivano per path puntato (``base.pointer.loop_end`` in ``for_each:``,
``spread.over``, una patch di ``coppia``) e come asse (``axes.pointer.start``):
il riconoscimento guarda i segmenti del path, non il blocco.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from . import audioinfo
from . import engine_info as EI
from . import schema
from .convert import as_num as _num
from .model import StudyModel, lookup
from .navigation import find_samples_dir
from .yamlpos import Document, KeyPath


def _tokens(path: KeyPath) -> List[Any]:
    """Il path coi segmenti puntati spezzati: ``("for_each",
    "base.pointer.loop_end", 2)`` -> ``[for_each, base, pointer, loop_end, 2]``."""
    out: List[Any] = []
    for seg in path:
        if isinstance(seg, str):
            out.extend(seg.split("."))
        else:
            out.append(seg)
    return out


def _all_numbers(v: Any) -> bool:
    return isinstance(v, list) and bool(v) and all(_num(x) is not None for x in v)


def _is_breakpoint_list(v: Any) -> bool:
    return (isinstance(v, list) and bool(v)
            and all(isinstance(p, list) and len(p) in (2, 3)
                    and _num(p[0]) is not None for p in v))


def position_key(doc: Document, path: KeyPath) -> Optional[str]:
    """La posizione (``start`` | ``loop_*``) di cui lo scalare a ``path`` e' un
    valore, o None.

    Un valore e' lo scalare stesso, un elemento di una lista di numeri (gli
    stati di un asse, ``values``), il ``baseline`` di un asse, o la **y** di un
    breakpoint. Non lo sono il tempo di un breakpoint, la ``range`` di una banda
    (una larghezza, non una posizione) ne' i posizionali di una forma compatta
    o di un BP group, che qui non si interpretano."""
    toks = _tokens(path)
    for j in range(len(toks) - 2, 0, -1):
        if (toks[j] == "pointer" and toks[j + 1] in EI.LOOP_UNIT_SCOPE
                and toks[j - 1] in ("base", "axes")):
            break
    else:
        return None
    key, tail = toks[j + 1], toks[j + 2:]
    if not tail:
        return key
    if tail == ["baseline"]:
        return key
    if len(tail) == 2 and tail[0] == "values" and isinstance(tail[1], int):
        return key if _all_numbers(doc.get(path[:-1])) else None
    if len(tail) == 1 and isinstance(tail[0], int):
        return key if _all_numbers(doc.get(path[:-1])) else None
    breakpoint_y = (len(tail) == 2 and isinstance(tail[0], int) and tail[1] == 1) or (
        len(tail) == 3 and tail[0] == "points" and isinstance(tail[1], int)
        and tail[2] == 1)
    if breakpoint_y and _is_breakpoint_list(doc.get(path[:-2])):
        return key
    return None


@dataclass(frozen=True)
class Reading:
    """Una posizione normalizzata tradotta in secondi."""

    seconds: float
    sample: str
    sample_duration: float
    # il documento scrive ``base.sample`` anche fuori da ``base:`` e dagli
    # override di stream (for_each, spread, versions, ...): il sample di questa
    # lettura e' uno dei possibili, e l'etichetta deve nominarlo
    sample_varies: bool

    @property
    def label(self) -> str:
        out = f"≈ {fmt_seconds(self.seconds)}"
        return out + (f" su {self.sample}" if self.sample_varies else "")


def fmt_seconds(s: float) -> str:
    """Secondi leggibili: due decimali sopra il secondo, tre sotto, ms sotto
    il centesimo (una posizione a 0.4 ms in un sample corto non e' «0.00 s»)."""
    if abs(s) >= 1:
        return f"{s:.2f} s"
    if abs(s) >= 0.01:
        return f"{s:.3f} s"
    return f"{s * 1000:.2f} ms"


class Resolver:
    """Unita', sample e durata per i valori di un documento.

    Una istanza per richiesta: la durata di un sample si legge una volta, e la
    domanda «il sample cambia fra i documenti generati?» si fa una volta."""

    def __init__(self, doc: Document, m: StudyModel, file_dir: Optional[str]):
        self.doc = doc
        self.m = m
        self.file_dir = file_dir
        self._durations: Dict[str, Optional[float]] = {}
        self._varies: Optional[bool] = None

    # ------------------------------------------------------------------
    def _patch(self, path: KeyPath) -> Optional[Dict[str, Any]]:
        """La patch di ``coppia`` che contiene ``path``, se ce n'e' una: le sue
        chiavi valgono per i valori scritti accanto."""
        if len(path) >= 3 and path[:2] == ("for_each", "coppia"):
            state = self.doc.get(path[:3])
            return state if isinstance(state, dict) else None
        return None

    def _stream(self, path: KeyPath) -> Optional[str]:
        if len(path) >= 2 and path[0] == "streams" and isinstance(path[1], str):
            return path[1]
        return None

    def loop_unit(self, path: KeyPath) -> Optional[str]:
        """La ``loop_unit`` in vigore dove vive ``path``."""
        patch = self._patch(path)
        if patch is not None:
            v = lookup(patch, ("base", "pointer", "loop_unit"))
            if isinstance(v, str):
                return v
        return self.m.loop_unit_for(self._stream(path))

    def sample(self, path: KeyPath) -> Tuple[Optional[str], bool]:
        """(sample in vigore dove vive ``path``, dichiarato dalla sua patch)."""
        patch = self._patch(path)
        if patch is not None:
            v = lookup(patch, ("base", "sample"))
            if isinstance(v, str):
                return v, True
        return self.m.sample_for(self._stream(path)), False

    def sample_varies(self) -> bool:
        """True se ``base.sample`` e' scritto anche fuori dal ``base:`` di
        documento e dagli override di stream — cioe' se i documenti generati
        (for_each, spread, versions, percorso) possono avere sample diversi."""
        if self._varies is None:
            self._varies = False
            for entry in self.doc.iter_entries():
                p = entry.path
                if not p or schema.is_private_key(p[0]):
                    continue
                toks = _tokens(p)
                if not any(toks[i] == "base" and toks[i + 1] == "sample"
                           for i in range(len(toks) - 1)):
                    continue
                own = (toks == ["base", "sample"]
                       or (len(toks) == 4 and toks[0] == "streams"
                           and toks[2:] == ["base", "sample"]))
                if not own:
                    self._varies = True
                    break
        return self._varies

    def duration(self, sample: str) -> Optional[float]:
        if sample not in self._durations:
            self._durations[sample] = self._read_duration(sample)
        return self._durations[sample]

    def _read_duration(self, sample: str) -> Optional[float]:
        samples_dir = self.doc.get(("samples_dir",))
        root = find_samples_dir(
            self.file_dir, samples_dir if isinstance(samples_dir, str) else "samples")
        if root is None:
            return None
        target = os.path.join(root, sample)
        if not os.path.isfile(target):
            return None
        return audioinfo.duration(target)

    # ------------------------------------------------------------------
    def reading(self, path: KeyPath) -> Optional[Reading]:
        """Il valore a ``path`` in secondi, se e' una posizione normalizzata e
        la durata del suo sample si legge."""
        n = _num(self.doc.get(path))
        if n is None or position_key(self.doc, path) is None:
            return None
        if self.loop_unit(path) != "normalized":
            return None
        sample, from_patch = self.sample(path)
        if not sample:
            return None
        dur = self.duration(sample)
        if dur is None:
            return None
        return Reading(seconds=n * dur, sample=sample, sample_duration=dur,
                       sample_varies=self.sample_varies() and not from_patch)
