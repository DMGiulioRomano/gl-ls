"""Il blocco ``for_each:`` di ``study.yml`` (gl-ls #48).

Semantica (granstudies ``for_each.py``):

- ``coppia`` e' una chiave **riservata**, come ``onset``/``duration``/``chunk``
  in ``versions:``: i suoi stati sono patch sul documento, non valori di una
  variabile nel senso ordinario;
- ogni altra chiave e' un asse esterno il cui nome **e' un path puntato dentro
  il documento** (``base.pitch.range``): si valida come tale, segmento per
  segmento, nel contesto della forma annidata — non come un nome d'asse;
- il prodotto cartesiano genera una cartella per combinazione, con label
  ``k=v__k=v``.

La fixture ``for_each_assi.yml`` ricostruisce la forma dello ``study.yml``
dello studio 001-41, su cui gl-ls dava 11 warning, tutti falsi positivi.
"""
import os

from glls import (completion, diagnostics, hover, model, schema, semtokens,
                  yamlpos)

HERE = os.path.dirname(__file__)

BASE = """study_id: t
base:
  onset: 0
  duration: 6
  sample: corpus.wav
axes:
  density:
    baseline: 20
    values: [10, 30]
"""


def diags_of(text):
    doc = yamlpos.parse(text)
    return diagnostics.collect(doc, model.build(doc))


def codes_of(text):
    return [d.code for d in diags_of(text)]


def for_each(corpo):
    return BASE + "for_each:\n" + corpo


# --- la fixture dell'issue ---------------------------------------------------

def test_lo_studio_001_41_non_ha_piu_falsi_positivi():
    with open(os.path.join(HERE, "fixtures", "for_each_assi.yml")) as f:
        text = f.read()
    got = [(d.range.start.line + 1, d.code, d.message) for d in diags_of(text)]
    assert got == []


# --- schema ------------------------------------------------------------------

def test_for_each_e_una_chiave_del_documento():
    assert schema.key_in("root", "for_each") is not None
    assert schema.context_for_path(("for_each",)) == "for_each"


def test_coppia_e_riservata_e_i_suoi_stati_non_si_giudicano():
    """Gli stati di ``coppia`` sono patch sul documento: il loro contenuto non
    e' il vocabolario di un contesto dello studio."""
    assert schema.key_in("for_each", "coppia") is not None
    assert schema.context_for_path(("for_each", "coppia")) == "value"
    assert schema.context_for_path(("for_each", "coppia", "a")) == "value"
    text = for_each("  coppia:\n    a: {base.pointer.loop_end: 0.2}\n"
                    "    b: {qualcosa: 1}\n")
    assert codes_of(text) == []


def test_il_contesto_for_each_non_e_chiuso():
    """I nomi degli assi esterni sono path, validati da una regola propria:
    il pass generico sulle chiavi sconosciute non deve leggerli come chiavi di
    un vocabolario."""
    assert "for_each" not in schema.CLOSED_CONTEXTS


# --- gli assi esterni sono path nel documento ---------------------------------

def test_i_path_validi_passano():
    text = for_each("  base.distribution: [0, 0.5, 1]\n"
                    "  base.pointer.offset_range: [0, 0.1]\n"
                    "  base.grain.duration_range: [0, 0.005]\n"
                    "  base.pitch.range: [0, 1]\n")
    assert codes_of(text) == []


def test_un_path_che_non_esiste_nel_documento_e_segnalato():
    text = for_each("  base.pich.range: [0, 1]\n")
    got = [d for d in diags_of(text) if d.code == "for-each-path"]
    assert len(got) == 1
    assert "'pich'" in got[0].message
    assert got[0].data["fix"] == {"kind": "rename", "new": "base.pitch.range"}


def test_il_segmento_sbagliato_e_nominato_col_suo_contesto():
    text = for_each("  base.pointer.loop_fine: [0.1, 0.2]\n")
    got = [d for d in diags_of(text) if d.code == "for-each-path"]
    assert len(got) == 1
    assert "'loop_fine'" in got[0].message
    assert "pointer" in got[0].message


def test_il_primo_segmento_dev_essere_una_chiave_del_documento():
    text = for_each("  bsae.distribution: [0, 1]\n")
    got = [d for d in diags_of(text) if d.code == "for-each-path"]
    assert len(got) == 1
    assert got[0].data["fix"]["new"] == "base.distribution"


def test_un_path_sugli_assi_segue_il_confine_del_nome_d_asse():
    """``axes.grain.duration.values``: il nome d'asse e' dotted, e il confine
    si risolve come negli override (assi dichiarati > registro engine)."""
    text = BASE + ("  grain.duration:\n    baseline: 0.01\n"
                   "    values: [0.01, 0.02]\n"
                   "for_each:\n  axes.grain.duration.baseline: [0.01, 0.02]\n")
    assert codes_of(text) == []


def test_la_chiave_non_e_un_nome_d_asse():
    """L'errore dell'issue era il contrario: un path letto come nome libero.
    Un nome d'asse dichiarato non e' un path del documento."""
    text = for_each("  density: [10, 20]\n")
    assert "for-each-path" in codes_of(text)


def test_for_each_dev_essere_un_mapping():
    assert "for-each-type" in codes_of(BASE + "for_each: [1, 2]\n")


def test_bounds_sui_valori_numerici_di_un_path_engine():
    """I valori di un asse esterno finiscono nel documento come ogni altra
    patch: un numero fuori dai bounds dell'engine lo e' anche qui."""
    text = for_each("  base.distribution: [0, 0.5, 2]\n")
    got = [d for d in diags_of(text) if d.code == "out-of-bounds"]
    assert len(got) == 1
    assert "for_each['base.distribution'][2]" in got[0].message


def test_bounds_nell_unita_della_durata_del_grano():
    text = (BASE.replace("  sample: corpus.wav\n",
                         "  sample: corpus.wav\n  grain:\n"
                         "    duration_unit: milliseconds\n    duration: 5\n")
            + "for_each:\n  base.grain.duration_range: [0, 2000]\n")
    got = [d for d in diags_of(text) if d.code == "out-of-bounds"]
    assert len(got) == 1
    assert "2000" in got[0].message


def test_for_each_non_vale_in_un_override_di_stream():
    text = BASE + "streams:\n  a:\n    for_each:\n      base.volume: [0, -6]\n"
    got = [d for d in diags_of(text) if d.code == "unknown-key"]
    assert any("'for_each'" in d.message for d in got)


# --- feature d'appoggio -------------------------------------------------------

def test_completion_propone_coppia_e_i_path_del_documento():
    text = for_each("  \n")
    doc = yamlpos.parse(text)
    line = len(text.splitlines()) - 1
    labels = {i.label for i in completion.complete(doc, model.build(doc), line, 2)}
    assert "coppia" in labels
    assert "base.distribution" in labels
    assert "base.pointer.loop_end" in labels


def test_hover_su_un_asse_esterno_dice_che_e_un_path():
    text = for_each("  base.distribution: [0, 1]\n")
    doc = yamlpos.parse(text)
    line = len(text.splitlines()) - 1
    h = hover.hover(doc, model.build(doc), line, 4)
    assert h is not None
    assert "path" in h.contents.value
    assert "bounds [0, 1]" in h.contents.value


def test_hover_su_coppia():
    text = for_each("  coppia:\n    a: {base.volume: -6}\n")
    doc = yamlpos.parse(text)
    line = len(text.splitlines()) - 2
    h = hover.hover(doc, model.build(doc), line, 3)
    assert h is not None
    assert "riservata" in h.contents.value


def test_semantic_token_dei_path_e_della_chiave_riservata():
    text = for_each("  coppia:\n    a: {}\n  base.distribution: [0, 1]\n")
    doc = yamlpos.parse(text)
    data = semtokens.tokens(doc, model.build(doc))
    toks, line, col = {}, 0, 0
    for i in range(0, len(data), 5):
        dl, dc, _ln, tok, _ = data[i:i + 5]
        line += dl
        col = dc if dl else col + dc
        toks[(line, col)] = semtokens.TOKEN_TYPES[tok]
    rows = text.splitlines()
    assert toks[(rows.index("  coppia:"), 2)] == "keyword"
    assert toks[(rows.index("  base.distribution: [0, 1]"), 2)] == "property"


def test_un_path_engine_senza_base_suggerisce_il_path_nel_documento():
    """Dimenticare ``base.`` e' l'errore piu' probabile: ``distribution`` e'
    un parametro engine, ma nel documento vive sotto ``base:``."""
    text = for_each("  distribution: [0, 1]\n")
    got = [d for d in diags_of(text) if d.code == "for-each-path"]
    assert len(got) == 1
    assert got[0].data["fix"] == {"kind": "rename", "new": "base.distribution"}


def test_un_path_verso_una_chiave_vietata_non_regge():
    """``duration`` al root lo schema la conosce — per spiegarla — ma il
    runtime la rifiuta: una patch che la scrive non e' un path valido."""
    text = for_each("  duration: [10, 20]\n")
    got = [d for d in diags_of(text) if d.code == "for-each-path"]
    assert len(got) == 1
    assert got[0].data["fix"] == {"kind": "rename", "new": "base.duration"}


def test_un_path_verso_una_chiave_morta_non_regge():
    text = for_each("  base.dephase: [0, 50]\n")
    got = [d for d in diags_of(text) if d.code == "for-each-path"]
    assert len(got) == 1
    assert got[0].data["fix"]["new"] == "base.deviation_probability"


def test_la_durata_di_uno_stream_e_un_path_valido():
    text = BASE + "streams:\n  a: {}\nfor_each:\n  streams.a.duration: [10, 20]\n"
    assert codes_of(text) == []
