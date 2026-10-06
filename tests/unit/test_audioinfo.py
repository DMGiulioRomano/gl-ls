"""Durata di un file audio dall'header (``glls.audioinfo``), senza dipendenze.

I file sono costruiti qui, byte per byte dove la stdlib non sa scriverli: e'
il modo di provare proprio i casi per cui il lettore esiste — il WAV in
virgola mobile e ``WAVE_FORMAT_EXTENSIBLE``, che ``wave`` rifiuta; l'AIFF, per
cui ``aifc`` non c'e' piu' da Python 3.13; il FLAC, di cui basta
``STREAMINFO``.
"""
import os
import struct
import wave

import pytest

from glls import audioinfo


def _wav_pcm(path, frames, rate=1000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * frames)


def _wav_raw(path, fmt_tag, rate, channels, bits, frames, extensible=False,
             declared=None):
    align = channels * bits // 8
    data = b"\x00" * (frames * align)
    fmt = struct.pack("<HHIIHH", fmt_tag, channels, rate, rate * align, align,
                      bits)
    if extensible:
        fmt += struct.pack("<HHI", 22, bits, 0) + b"\x03\x00" + b"\x00" * 14
    body = (b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
            + b"LIST" + struct.pack("<I", 4) + b"INFO"
            + b"data" + struct.pack("<I", declared if declared is not None
                                    else len(data)) + data)
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)


def _extended(rate):
    """``rate`` come IEEE 754 extended a 80 bit (il sample rate di AIFF)."""
    exp = rate.bit_length() - 1
    mant = rate << (63 - exp)
    return struct.pack(">H", exp + 16383) + mant.to_bytes(8, "big")


def _aiff(path, frames, rate, form=b"AIFF"):
    comm = struct.pack(">hIh", 1, frames, 16) + _extended(rate)
    ssnd = struct.pack(">II", 0, 0) + b"\x00" * (frames * 2)
    body = (form + b"COMM" + struct.pack(">I", len(comm)) + comm
            + b"SSND" + struct.pack(">I", len(ssnd)) + ssnd)
    path.write_bytes(b"FORM" + struct.pack(">I", len(body)) + body)


def _flac(path, total, rate, id3=False):
    packed = (rate << 44) | (0 << 41) | (15 << 36) | total
    info = (struct.pack(">HH", 4096, 4096) + b"\x00" * 6
            + packed.to_bytes(8, "big") + b"\x00" * 16)
    stream = b"fLaC" + bytes([0x80]) + len(info).to_bytes(3, "big") + info
    if id3:
        tag = b"\x00" * 20
        size = len(tag)
        syncsafe = bytes([(size >> 21) & 0x7F, (size >> 14) & 0x7F,
                          (size >> 7) & 0x7F, size & 0x7F])
        stream = b"ID3\x04\x00\x00" + syncsafe + tag + stream
    path.write_bytes(stream)


def test_wav_pcm(tmp_path):
    p = tmp_path / "a.wav"
    _wav_pcm(p, 5500)
    assert audioinfo.duration(str(p)) == pytest.approx(5.5)


def test_wav_in_virgola_mobile(tmp_path):
    """Formato 3 (IEEE float): ``wave`` lo rifiuta, ed e' l'export a 32 bit
    piu' comune."""
    p = tmp_path / "f.wav"
    _wav_raw(p, 3, 48000, 2, 32, 24000)
    assert audioinfo.duration(str(p)) == pytest.approx(0.5)


def test_wav_extensible(tmp_path):
    p = tmp_path / "x.wav"
    _wav_raw(p, 0xFFFE, 44100, 1, 24, 44100, extensible=True)
    assert audioinfo.duration(str(p)) == pytest.approx(1.0)


def test_wav_con_data_dichiarato_oltre_il_file(tmp_path):
    """Registrazione interrotta: l'header promette piu' byte di quanti ce ne
    siano. Si legge su quelli che ci sono."""
    p = tmp_path / "t.wav"
    _wav_raw(p, 1, 1000, 1, 16, 2000, declared=10_000_000)
    assert audioinfo.duration(str(p)) == pytest.approx(2.0)


def test_aiff_e_aifc(tmp_path):
    for form in (b"AIFF", b"AIFC"):
        p = tmp_path / f"a.{form.decode().lower()}"
        _aiff(p, 44100 * 3, 44100, form)
        assert audioinfo.duration(str(p)) == pytest.approx(3.0), form


def test_flac(tmp_path):
    p = tmp_path / "a.flac"
    _flac(p, 96000 * 2, 96000)
    assert audioinfo.duration(str(p)) == pytest.approx(2.0)


def test_flac_dietro_un_tag_id3(tmp_path):
    p = tmp_path / "b.flac"
    _flac(p, 48000, 48000, id3=True)
    assert audioinfo.duration(str(p)) == pytest.approx(1.0)


def test_flac_senza_conteggio_dei_campioni_non_indovina(tmp_path):
    """``total = 0`` e' «sconosciuto» nello standard: nessuna durata."""
    p = tmp_path / "c.flac"
    _flac(p, 0, 48000)
    assert audioinfo.duration(str(p)) is None


def test_file_non_audio_o_assente(tmp_path):
    p = tmp_path / "note.wav"
    p.write_text("non sono un wav")
    assert audioinfo.duration(str(p)) is None
    assert audioinfo.duration(str(tmp_path / "manca.wav")) is None


def test_la_cache_segue_il_file(tmp_path):
    """Il sample riesportato sotto lo stesso nome deve cambiare durata."""
    p = tmp_path / "c.wav"
    _wav_pcm(p, 1000)
    assert audioinfo.duration(str(p)) == pytest.approx(1.0)
    _wav_pcm(p, 3000)
    st = os.stat(p)
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    assert audioinfo.duration(str(p)) == pytest.approx(3.0)
