"""``grain.duration_range_unit``: la banda come frazione della base (gl-ls #49).

PGE #267 aggiunge ``grain.duration_range_unit: absolute | relative``. Con
``relative`` il numero di ``grain.duration_range`` non e' piu' una larghezza
nell'unita' di ``duration_unit``: e' una **frazione del valore base**, letta
istante per istante, con un dominio suo (``RELATIVE_RANGE_BOUNDS``, [0, 1]) che
*sostituisce* quello assoluto. Assente vale ``absolute``, la lettura storica.

Tre buchi, uno per lato del mirror:

- ``grain`` e' un contesto chiuso, e la chiave nuova era un ``unknown-key`` con
  un rename distruttivo verso ``duration_range`` (gia' presente due righe
  sopra);
- ``_UNIT_SCALED`` convertiva la banda verso i secondi anche quando e' una
  frazione, cioe' faceva la conversione che l'engine ha smesso di fare
  (``Stream._pre_normalize_grain_params``): ``2.0`` sotto ``samples`` diventava
  ``4.2e-05`` e passava, dove l'engine si ferma con ``ParameterBoundError``;
- bounds e hover della banda dicevano ``±s`` su un numero adimensionale.
"""
import pytest

from glls import completion, diagnostics, hover, model, schema, yamlpos
from glls import engine_info as EI

HEAD = """study_id: t
base:
  onset: 0
  duration: 6
  sample: corpus.wav
  grain:
%s
axes:
  density:
    baseline: 20
    values: [10, 30]
"""


def _grain(*lines):
    return HEAD % "\n".join("    " + ln for ln in lines)


def diags_of(text):
    doc = yamlpos.parse(text)
    return diagnostics.collect(doc, model.build(doc))


def codes_of(text):
    return [d.code for d in diags_of(text)]


def _of(text, code):
    return [d for d in diags_of(text) if d.code == code]


# --- 1. la chiave e' nel vocabolario di ``grain`` ----------------------------

def test_la_chiave_e_nel_registro_di_grain():
    k = schema.key_in("grain", "duration_range_unit")
    assert k is not None
    assert list(k.values) == list(EI.RANGE_UNITS) == ["absolute", "relative"]


def test_il_caso_della_issue_non_e_un_unknown_key():
    """Lo studio da cui nasce PGE #267: durata da un campione a 500 ms, banda
    relativa. Prima: ``unknown-key`` col rename verso ``duration_range``."""
    text = _grain("duration_unit: milliseconds",
                  "duration: [[0, 0.021], [6, 500]]",
                  "duration_range: 0.5",
                  "duration_range_unit: relative")
    assert diags_of(text) == []


def test_absolute_esplicito_e_valido():
    text = _grain("duration: 0.05", "duration_range: 0.01",
                  "duration_range_unit: absolute")
    assert diags_of(text) == []


def test_la_doc_della_banda_nomina_la_lettura_relativa():
    doc = schema.key_in("grain", "duration_range").doc
    assert "duration_range_unit" in doc
    assert "relative" in schema.key_in("grain", "duration_range_unit").doc


def test_completion_del_valore():
    text = _grain("duration: 0.05", "duration_range: 0.5",
                  "duration_range_unit: ")
    doc = yamlpos.parse(text)
    line = text.splitlines().index("    duration_range_unit: ")
    labels = {i.label for i in completion.complete(doc, model.build(doc), line, 25)}
    assert labels >= {"absolute", "relative"}


# --- vocabolario chiuso, assente != vuota ------------------------------------

def test_grafia_fuori_vocabolario_e_errore_con_suggerimento():
    got = _of(_grain("duration: 0.05", "duration_range: 0.5",
                     "duration_range_unit: relativ"), "range-unit-sconosciuta")
    assert len(got) == 1
    assert "absolute | relative" in got[0].message
    assert got[0].data["fix"] == {"kind": "rename-value", "new": "relative"}


def test_la_chiave_vuota_non_vale_absolute():
    """L'engine distingue assente da vuota (``_KEY_ABSENT``): la vuota e'
    scritta, e leggerla come il default sarebbe il silenzio che rifiuta."""
    got = _of(_grain("duration: 0.05", "duration_range: 0.5",
                     "duration_range_unit:"), "range-unit-vuota")
    assert len(got) == 1
    assert "absolute | relative" in got[0].message


def test_il_vocabolario_vale_anche_negli_override_di_stream():
    text = (_grain("duration: 0.05", "duration_range: 0.5")
            + "streams:\n  a:\n    base:\n      grain:\n"
              "        duration_range_unit: relatve\n")
    got = _of(text, "range-unit-sconosciuta")
    assert len(got) == 1
    assert got[0].range.start.line == text.splitlines().index(
        "        duration_range_unit: relatve")


# --- relative senza banda: l'engine pretende la banda esplicita ---------------

def test_relative_senza_banda_e_errore():
    got = _of(_grain("duration: 0.05", "duration_range_unit: relative"),
              "range-unit-senza-banda")
    assert len(got) == 1
    assert "duration_range" in got[0].message


def test_absolute_senza_banda_no():
    assert "range-unit-senza-banda" not in codes_of(
        _grain("duration: 0.05", "duration_range_unit: absolute"))


def test_la_banda_vuota_non_e_una_banda():
    assert "range-unit-senza-banda" in codes_of(
        _grain("duration: 0.05", "duration_range:",
               "duration_range_unit: relative"))


def test_un_asse_sulla_banda_la_fornisce():
    text = (_grain("duration: 0.05", "duration_range_unit: relative")
            + "  grain.duration_range:\n    baseline: 0.2\n"
              "    values: [0.1, 0.5]\n")
    assert "range-unit-senza-banda" not in codes_of(text)


def test_un_path_puntato_sulla_banda_la_fornisce():
    text = (_grain("duration: 0.05", "duration_range_unit: relative")
            + "for_each:\n  base.grain.duration_range: [0.1, 0.5]\n")
    assert "range-unit-senza-banda" not in codes_of(text)


def test_la_banda_dello_stream_basta_per_lo_stream():
    text = (_grain("duration: 0.05", "duration_range_unit: relative")
            + "streams:\n  a:\n    base:\n      grain:\n"
              "        duration_range: 0.3\n"
              "  b:\n    base:\n      grain:\n"
              "        duration_range: 0.6\n")
    assert "range-unit-senza-banda" not in codes_of(text)


def test_il_difetto_del_base_non_si_moltiplica_per_gli_stream():
    text = (_grain("duration: 0.05", "duration_range_unit: relative")
            + "streams:\n  a:\n    base: {volume: -6}\n"
              "  b:\n    base: {volume: -3}\n")
    got = _of(text, "range-unit-senza-banda")
    assert len(got) == 1
    assert got[0].range.start.line == text.splitlines().index(
        "    duration_range_unit: relative")


def test_lo_stream_che_dichiara_relative_senza_banda_si_prende_il_rilievo():
    text = (_grain("duration: 0.05")
            + "streams:\n  a:\n    base:\n      grain:\n"
              "        duration_range_unit: relative\n")
    got = _of(text, "range-unit-senza-banda")
    assert len(got) == 1
    assert got[0].range.start.line == text.splitlines().index(
        "        duration_range_unit: relative")


# --- 2. una frazione non si converte -----------------------------------------

def test_la_frazione_non_si_converte_dai_campioni():
    """Il falso negativo della issue: 2.0 / 48000 sta in [0, 1], 2.0 no."""
    got = _of(_grain("duration_unit: samples", "duration: 4800",
                     "duration_range: 2.0", "duration_range_unit: relative"),
              "out-of-bounds")
    assert len(got) == 1
    assert "frazione" in got[0].message
    assert "campioni" not in got[0].message


def test_la_frazione_non_si_converte_dai_millisecondi():
    # 500 ms assoluti sono 0.5 s, dentro [0, 1]; una frazione 500 no
    text = _grain("duration_unit: milliseconds", "duration: 50",
                  "duration_range: 500", "duration_range_unit: %s")
    assert "out-of-bounds" not in codes_of(text % "absolute")
    assert "out-of-bounds" in codes_of(text % "relative")


def test_la_base_si_converte_ancora():
    """L'unita' governa la sola base: sotto ``relative`` ``grain.duration``
    resta nei campioni e si confronta in secondi."""
    text = _grain("duration_unit: samples", "duration: 500000",
                  "duration_range: 0.5", "duration_range_unit: relative")
    got = _of(text, "out-of-bounds")
    assert len(got) == 1
    assert "campioni" in got[0].message


def test_absolute_converte_come_prima():
    # 96000 campioni sono 2 s: fuori dalla banda assoluta (1 s)
    got = _of(_grain("duration_unit: samples", "duration: 4800",
                     "duration_range: 96000"), "out-of-bounds")
    assert len(got) == 1
    assert "campioni" in got[0].message
    assert "out-of-bounds" not in codes_of(
        _grain("duration_unit: samples", "duration: 4800",
               "duration_range: 2.0"))


def test_i_punti_di_un_envelope_sono_frazioni():
    text = _grain("duration_unit: samples", "duration: 4800",
                  "duration_range: [[0, 0.2], [6, 1.5]]",
                  "duration_range_unit: relative")
    got = _of(text, "out-of-bounds")
    assert len(got) == 1
    assert "1.5" in got[0].message


def test_i_punti_di_un_bp_group_sono_frazioni():
    text = _grain("duration_unit: samples", "duration: 4800",
                  "duration_range: [[[0, 0.2], [6, 3]], linear]",
                  "duration_range_unit: relative")
    assert len(_of(text, "out-of-bounds")) == 1


def test_l_unita_si_eredita_dal_base_nello_stream():
    text = (_grain("duration_unit: samples", "duration: 4800",
                   "duration_range: 0.5", "duration_range_unit: relative")
            + "streams:\n  a:\n    base:\n      grain:\n"
              "        duration_range: 2.0\n")
    got = _of(text, "out-of-bounds")
    assert len(got) == 1
    assert got[0].range.start.line == text.splitlines().index(
        "        duration_range: 2.0")


def test_lo_stream_che_torna_absolute_converte():
    # 96 campioni = 2 ms: in bounds come durata, fuori come frazione
    text = (_grain("duration_unit: samples", "duration: 4800",
                   "duration_range: 0.5", "duration_range_unit: relative")
            + "streams:\n  a:\n    base:\n      grain:\n"
              "        duration_range: 96\n"
              "        duration_range_unit: absolute\n")
    assert "out-of-bounds" not in codes_of(text)


def test_i_valori_di_un_asse_sono_frazioni():
    text = (_grain("duration_unit: samples", "duration: 4800",
                   "duration_range_unit: relative")
            + "  grain.duration_range:\n    baseline: 0.2\n"
              "    values: [0.5, 2]\n")
    got = _of(text, "out-of-bounds")
    assert len(got) == 1
    assert "values[1]" in got[0].message


def test_i_valori_di_for_each_sono_frazioni():
    text = (_grain("duration_unit: samples", "duration: 4800",
                   "duration_range: 0.2", "duration_range_unit: relative")
            + "for_each:\n  base.grain.duration_range: [0.5, 3]\n")
    assert len(_of(text, "out-of-bounds")) == 1


def test_il_dominio_relativo_non_e_quello_assoluto(monkeypatch):
    """I due ``1`` coincidono per caso (PGE lo dichiara accanto a
    ``RELATIVE_RANGE_BOUNDS``): alzarne uno non alza l'altro."""
    monkeypatch.setattr(EI, "RELATIVE_RANGE_BOUNDS", (0.0, 0.5))
    text = _grain("duration: 0.05", "duration_range: 0.7",
                  "duration_range_unit: %s")
    assert "out-of-bounds" in codes_of(text % "relative")
    assert "out-of-bounds" not in codes_of(text % "absolute")


def test_info_for_sostituisce_bounds_e_unita():
    absolute = EI.info_for("grain.duration_range")
    relative = EI.info_for("grain.duration_range", range_unit="relative")
    assert absolute.unit == "±s"
    assert (relative.min, relative.max) == EI.RELATIVE_RANGE_BOUNDS
    assert relative.unit == EI.RELATIVE_RANGE_UNIT
    # solo la banda governata dalla chiave cambia lettura
    assert EI.info_for("volume_range", range_unit="relative").unit == "±dB"
    assert EI.info_for("grain.duration_range", range_unit="relativ").unit == "±s"


# --- 3. l'hover --------------------------------------------------------------

def _hover(text, needle, col):
    doc = yamlpos.parse(text)
    line = text.splitlines().index(needle)
    h = hover.hover(doc, model.build(doc), line, col)
    return h.contents.value if h else None


def test_hover_della_banda_relativa_non_dice_secondi():
    text = _grain("duration: 0.05", "duration_range: 0.5",
                  "duration_range_unit: relative")
    for col in (6, 22):   # chiave e valore
        v = _hover(text, "    duration_range: 0.5", col)
        assert EI.RELATIVE_RANGE_UNIT in v, col
        assert "±s" not in v, col


def test_hover_della_banda_assoluta_dice_secondi():
    text = _grain("duration: 0.05", "duration_range: 0.5")
    assert "±s" in _hover(text, "    duration_range: 0.5", 6)


def test_hover_segue_l_override_di_stream():
    text = (_grain("duration: 0.05", "duration_range: 0.5")
            + "streams:\n  a:\n    base:\n      grain:\n"
              "        duration_range: 0.2\n"
              "        duration_range_unit: relative\n")
    v = _hover(text, "        duration_range: 0.2", 10)
    assert EI.RELATIVE_RANGE_UNIT in v
    assert "±s" in _hover(text, "    duration_range: 0.5", 6)


def test_hover_di_un_asse_sulla_banda():
    text = (_grain("duration: 0.05", "duration_range_unit: relative")
            + "  grain.duration_range:\n    baseline: 0.2\n"
              "    values: [0.1, 0.5]\n")
    v = _hover(text, "  grain.duration_range:", 4)
    assert EI.RELATIVE_RANGE_UNIT in v
