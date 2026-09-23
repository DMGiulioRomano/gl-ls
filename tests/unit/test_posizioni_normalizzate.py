"""Le posizioni nel sample sotto ``loop_unit: normalized`` (gl-ls #48).

Con il loop normalizzato ``loop_end: 0.363636363636`` e' una frazione della
durata del **sample**, e l'hover diceva «s» su un valore che secondi non e'.
Ora l'unita' di ``engine_info`` dipende da ``loop_unit``, e un inlay hint
accanto al valore dice i secondi reali: ``loop_end: 0.363636  ≈ 2.00 s``.

La trappola da non cadere: il riferimento e' la durata del sample, non
``base.duration`` (granstudies ``gainmap``: ``pos = start * n_frames`` sotto
``normalized``). Sbagliarla darebbe un hint plausibile e falso — qui la durata
dello stream e' 20 s e quella del sample 5.5 s apposta.
"""
import wave

import pytest

from glls import engine_info as EI
from glls import hover, inlay, model, positions, yamlpos

HEAD = """study_id: t
samples_dir: samples
base:
  onset: 0
  duration: 20
  sample: corpus.wav
  pointer:
    loop_unit: normalized
    loop_start: 0.1
    loop_end: 0.363636363636
axes:
  density:
    baseline: 20
    values: [10, 30]
"""


def _wav(path, seconds, rate=1000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(round(seconds * rate)))


@pytest.fixture
def studio(tmp_path):
    """Un repo di studi: ``samples/`` alla root, lo study.yml due livelli
    sotto — ``samples_dir`` si trova risalendo, come nella navigazione."""
    (tmp_path / "samples").mkdir()
    _wav(tmp_path / "samples" / "corpus.wav", 5.5)
    _wav(tmp_path / "samples" / "lungo.wav", 11.0)
    d = tmp_path / "studies" / "001-41"
    d.mkdir(parents=True)
    return str(d)


def labels_at(text, file_dir):
    doc = yamlpos.parse(text)
    rows = text.splitlines()
    out = {}
    for h in inlay.hints(doc, model.build(doc), 0, len(rows), file_dir):
        out.setdefault(rows[h.position.line].strip(), []).append(h.label)
    return out


# --- l'unita' in engine_info --------------------------------------------------

def test_l_unita_di_una_posizione_dipende_da_loop_unit():
    assert EI.info_for("pointer.loop_end").unit == "s"
    assert EI.info_for("pointer.loop_end", "seconds").unit == "s"
    assert EI.info_for("pointer.loop_end", "absolute").unit == "s"
    assert EI.info_for("pointer.loop_end", "normalized").unit == \
        EI.NORMALIZED_POSITION_UNIT
    for k in EI.LOOP_UNIT_SCOPE:
        assert EI.info_for(f"pointer.{k}", "normalized").unit == \
            EI.NORMALIZED_POSITION_UNIT


def test_solo_le_posizioni_cambiano_unita():
    assert EI.info_for("pointer.speed_ratio", "normalized").unit == "ratio"
    assert EI.info_for("density", "normalized") is EI.PARAMS["density"]


def test_i_bounds_restano_quelli_dichiarati():
    info = EI.info_for("pointer.loop_dur", "normalized")
    base = EI.PARAMS["pointer.loop_dur"]
    assert (info.min, info.max, info.default) == (base.min, base.max, base.default)


# --- l'inlay -----------------------------------------------------------------

def test_i_secondi_sono_quelli_del_sample_non_della_duration(studio):
    got = labels_at(HEAD, studio)
    assert got["loop_end: 0.363636363636"] == ["≈ 2.00 s"]
    assert got["loop_start: 0.1"] == ["≈ 0.550 s"]


def test_in_secondi_nessun_hint(studio):
    for unit in ("seconds", "absolute"):
        text = HEAD.replace("loop_unit: normalized", f"loop_unit: {unit}")
        assert "loop_end: 0.363636363636" not in labels_at(text, studio), unit


def test_loop_unit_assente_vale_secondi_anche_sotto_time_mode_normalized(studio):
    """Da PGE v9 ``loop_unit`` non eredita da ``time_mode``: senza la chiave il
    numero e' gia' in secondi, e tradurlo sarebbe il falso."""
    text = HEAD.replace("    loop_unit: normalized\n", "").replace(
        "  sample: corpus.wav\n", "  sample: corpus.wav\n  time_mode: normalized\n")
    assert "loop_end: 0.363636363636" not in labels_at(text, studio)


def test_senza_il_file_del_sample_nessun_hint(studio):
    text = HEAD.replace("sample: corpus.wav", "sample: manca.wav")
    assert labels_at(text, studio) == {}
    assert labels_at(HEAD, None) == {}


def test_samples_dir_e_quella_dichiarata(studio):
    text = HEAD.replace("samples_dir: samples", "samples_dir: altrove")
    assert labels_at(text, studio) == {}


def test_valori_piccoli_in_millisecondi(studio):
    text = HEAD.replace("loop_start: 0.1", "loop_start: 0.001")
    assert labels_at(text, studio)["loop_start: 0.001"] == ["≈ 5.50 ms"]


def test_le_y_dei_breakpoint_si_i_tempi_no(studio):
    text = HEAD.replace("    loop_start: 0.1\n",
                        "    loop_start: [[0, 0.1], [1, 0.2]]\n")
    got = labels_at(text, studio)
    assert got["loop_start: [[0, 0.1], [1, 0.2]]"] == ["≈ 0.550 s", "≈ 1.10 s"]


def test_i_posizionali_di_una_forma_compatta_non_sono_posizioni(studio):
    text = HEAD.replace("    loop_start: 0.1\n",
                        "    loop_start: [[[0, 0.1], [50, 0.2]], 1, 4]\n")
    got = labels_at(text, studio)["loop_start: [[[0, 0.1], [50, 0.2]], 1, 4]"]
    assert not any(label.startswith("≈") for label in got)


def test_override_di_stream_col_suo_sample(studio):
    """``loop_unit`` ereditata dal base, sample dell'override: 11 s."""
    text = HEAD + ("streams:\n  a:\n    base:\n      sample: lungo.wav\n"
                   "      pointer:\n        start: 0.5\n")
    assert labels_at(text, studio)["start: 0.5"] == ["≈ 5.50 s"]


def test_override_di_stream_che_torna_in_secondi(studio):
    text = HEAD + ("streams:\n  a:\n    base:\n"
                   "      pointer:\n        loop_unit: seconds\n        start: 0.5\n")
    assert "start: 0.5" not in labels_at(text, studio)


def test_assi_sulle_posizioni(studio):
    text = HEAD + "  pointer.start:\n    baseline: 0.5\n    values: [0.1, 0.2]\n"
    got = labels_at(text, studio)
    assert got["baseline: 0.5"] == ["≈ 2.75 s"]
    assert got["values: [0.1, 0.2]"] == ["≈ 0.550 s", "≈ 1.10 s"]


def test_for_each_e_patch_di_coppia(studio):
    text = HEAD + ("for_each:\n  coppia:\n    lunga:\n"
                   "      base.pointer.loop_end: 0.5\n"
                   "  base.pointer.loop_start: [0.1, 0.2]\n")
    got = labels_at(text, studio)
    assert got["base.pointer.loop_end: 0.5"] == ["≈ 2.75 s"]
    assert got["base.pointer.loop_start: [0.1, 0.2]"] == ["≈ 0.550 s", "≈ 1.10 s"]


def test_una_patch_col_suo_sample_si_legge_su_quello(studio):
    text = HEAD + ("for_each:\n  coppia:\n    lunga:\n"
                   "      base.sample: lungo.wav\n"
                   "      base.pointer.loop_end: 0.5\n")
    got = labels_at(text, studio)
    assert got["base.pointer.loop_end: 0.5"] == ["≈ 5.50 s"]


def test_se_il_sample_cambia_fra_i_documenti_l_hint_lo_nomina(studio):
    """Una patch di ``coppia`` riscrive il sample: i valori del ``base:`` si
    leggono su ``corpus.wav`` solo in una parte delle combinazioni, e
    l'etichetta lo dice invece di tacerlo."""
    text = HEAD + ("for_each:\n  coppia:\n    lunga:\n"
                   "      base.sample: lungo.wav\n    corta: {}\n")
    got = labels_at(text, studio)
    assert got["loop_end: 0.363636363636"] == ["≈ 2.00 s su corpus.wav"]


def test_il_magazzino_privato_non_fa_variare_il_sample(studio):
    text = HEAD + "_assi:\n  s: {base.sample: lungo.wav}\n"
    assert labels_at(text, studio)["loop_end: 0.363636363636"] == ["≈ 2.00 s"]


def test_positions_riconosce_solo_le_posizioni():
    text = HEAD + ("  pointer.start:\n    baseline: 0.5\n    base: 0.1\n"
                   "    range: 0.2\n")
    doc = yamlpos.parse(text)
    assert positions.position_key(doc, ("base", "pointer", "loop_end")) == "loop_end"
    assert positions.position_key(doc, ("axes", "pointer.start", "baseline")) == "start"
    # la range di una banda e' una larghezza, non una posizione
    assert positions.position_key(doc, ("axes", "pointer.start", "range")) is None
    assert positions.position_key(doc, ("base", "pointer", "loop_unit")) is None
    assert positions.position_key(doc, ("base", "sample")) is None


# --- l'hover -----------------------------------------------------------------

def _hover(text, needle, col, file_dir=None):
    doc = yamlpos.parse(text)
    line = text.splitlines().index(needle)
    h = hover.hover(doc, model.build(doc), line, col, file_dir)
    return h.contents.value if h else None


def test_hover_della_chiave_dice_l_unita_in_vigore():
    v = _hover(HEAD, "    loop_end: 0.363636363636", 6)
    assert EI.NORMALIZED_POSITION_UNIT in v
    v = _hover(HEAD.replace("loop_unit: normalized", "loop_unit: seconds"),
               "    loop_end: 0.363636363636", 6)
    assert EI.NORMALIZED_POSITION_UNIT not in v
    assert "] s" in v


def test_hover_del_valore_senza_sample_dice_almeno_l_unita():
    v = _hover(HEAD, "    loop_end: 0.363636363636", 16)
    assert EI.NORMALIZED_POSITION_UNIT in v
    assert "] s" not in v


def test_hover_del_valore_col_sample_dice_i_secondi(studio):
    v = _hover(HEAD, "    loop_end: 0.363636363636", 16, studio)
    assert "2.00 s" in v
    assert "corpus.wav" in v
    assert "5.50 s" in v
