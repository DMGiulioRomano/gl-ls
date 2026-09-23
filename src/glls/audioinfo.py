"""Durata di un file audio letta dall'header, senza dipendenze.

gl-ls e' stdlib + pygls + PyYAML di proposito (gira dentro l'editor), quindi
qui non entra ``soundfile``. Non serve: per la durata bastano due numeri
dell'header, i frame e la frequenza di campionamento, e i tre formati che il
corpus usa li scrivono in posti noti.

- **WAV** (RIFF/RF64): chunk ``fmt `` (sample rate, block align) e ``data``
  (byte). Letto a mano e non con ``wave``, che rifiuta i WAV in virgola mobile
  e ``WAVE_FORMAT_EXTENSIBLE`` fino a Python 3.12 — cioe' proprio i sample
  esportati a 32 bit float;
- **AIFF/AIFC**: chunk ``COMM`` (frame, sample rate in extended a 80 bit).
  ``aifc`` e' fuori dalla stdlib da Python 3.13;
- **FLAC**: blocco ``STREAMINFO`` (sample rate a 20 bit, campioni totali a
  36), anche dietro un tag ID3v2.

La durata e' ``frame / sample_rate``, la stessa che l'engine legge con
``soundfile.info`` (``sample_dur_sec``). Un file che non si riconosce, o un
header che non dice quanti frame ha, da' ``None``: meglio nessuna risposta di
una durata indovinata.
"""
from __future__ import annotations

import os
import struct
from typing import BinaryIO, Dict, Optional, Tuple

#: (mtime_ns, size) -> durata, per path: l'inlay chiede a ogni scroll.
_CACHE: Dict[str, Tuple[int, int, Optional[float]]] = {}

AUDIO_EXTENSIONS = (".wav", ".aif", ".aiff", ".flac")


def duration(path: str) -> Optional[float]:
    """Durata in secondi del file audio a ``path``, o None."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    hit = _CACHE.get(path)
    if hit is not None and hit[:2] == (st.st_mtime_ns, st.st_size):
        return hit[2]
    try:
        with open(path, "rb") as f:
            dur = _read(f, st.st_size)
    except (OSError, struct.error, ValueError):
        dur = None
    _CACHE[path] = (st.st_mtime_ns, st.st_size, dur)
    return dur


def _read(f: BinaryIO, size: int) -> Optional[float]:
    head = f.read(12)
    if head[:4] in (b"RIFF", b"RF64") and head[8:12] == b"WAVE":
        return _wav(f, size, rf64=head[:4] == b"RF64")
    if head[:4] == b"FORM" and head[8:12] in (b"AIFF", b"AIFC"):
        return _aiff(f)
    f.seek(0)
    return _flac(f)


def _frames_to_sec(frames: int, rate: float) -> Optional[float]:
    if rate <= 0 or frames <= 0:
        return None
    return frames / rate


def _wav(f: BinaryIO, size: int, rf64: bool) -> Optional[float]:
    rate = align = None
    data_size: Optional[int] = None
    ds64_data: Optional[int] = None
    while True:
        hdr = f.read(8)
        if len(hdr) < 8:
            break
        cid, csize = hdr[:4], struct.unpack("<I", hdr[4:])[0]
        start = f.tell()
        if cid == b"fmt ":
            body = f.read(min(csize, 16))
            if len(body) < 14:
                return None
            rate = struct.unpack("<I", body[4:8])[0]
            align = struct.unpack("<H", body[12:14])[0]
        elif cid == b"ds64" and rf64:
            body = f.read(16)
            if len(body) == 16:
                ds64_data = struct.unpack("<Q", body[8:16])[0]
        elif cid == b"data":
            data_size = ds64_data if (rf64 and csize == 0xFFFFFFFF) else csize
            # un header che dichiara piu' byte di quanti il file ne abbia
            # (registrazione interrotta) si legge su quelli che ci sono
            data_size = min(data_size or 0, max(0, size - start))
            if rate is not None:
                break
        f.seek(start + csize + (csize & 1))
    if not rate or not align or data_size is None:
        return None
    return _frames_to_sec(data_size // align, rate)


def _extended(b: bytes) -> float:
    """IEEE 754 extended a 80 bit, big endian (il sample rate di AIFF)."""
    expon = ((b[0] & 0x7F) << 8) | b[1]
    mant = int.from_bytes(b[2:10], "big")
    if expon == 0 and mant == 0:
        return 0.0
    value = mant * 2.0 ** (expon - 16383 - 63)
    return -value if b[0] & 0x80 else value


def _aiff(f: BinaryIO) -> Optional[float]:
    while True:
        hdr = f.read(8)
        if len(hdr) < 8:
            return None
        cid, csize = hdr[:4], struct.unpack(">I", hdr[4:])[0]
        start = f.tell()
        if cid == b"COMM":
            body = f.read(18)
            if len(body) < 18:
                return None
            frames = struct.unpack(">I", body[2:6])[0]
            return _frames_to_sec(frames, _extended(body[8:18]))
        f.seek(start + csize + (csize & 1))


def _flac(f: BinaryIO) -> Optional[float]:
    head = f.read(10)
    if head[:3] == b"ID3" and len(head) == 10:
        # tag ID3v2 davanti al flusso: dimensione in 4 byte "syncsafe"
        tag = 0
        for byte in head[6:10]:
            tag = (tag << 7) | (byte & 0x7F)
        f.seek(10 + tag)
        head = f.read(4)
    else:
        head = head[:4]
        f.seek(4)
    if head[:4] != b"fLaC":
        return None
    block = f.read(4)
    if len(block) < 4 or block[0] & 0x7F != 0:     # 0 = STREAMINFO, sempre primo
        return None
    info = f.read(34)
    if len(info) < 34:
        return None
    packed = int.from_bytes(info[10:18], "big")
    rate = packed >> 44
    total = packed & ((1 << 36) - 1)
    return _frames_to_sec(total, rate)
