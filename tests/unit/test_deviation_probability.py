"""``deviation_probability``: la rinomina di PGE #204 e la stretta di v8.

Tre cose che si somigliano e non significano la stessa cosa — chiave assente,
chiave a ``false``, chiave **scritta e lasciata vuota** — piu' una chiave morta
che l'engine non legge piu' e di cui non si lamenta. Sono tutte scritture che
girano senza fermare niente e suonano diverso da come si legge lo YAML: il
posto dove dirlo e' l'editor.
"""
from glls import actions, diagnostics, model, schema, yamlpos

BASE = """study_id: t
base:
  onset: 0
  duration: 6
  sample: corpus.wav
%s
axes:
  density:
    baseline: 20
    values: [10, 30]
"""


def diags_of(text):
    doc = yamlpos.parse(text)
    return diagnostics.collect(doc, model.build(doc))


def codes_of(text):
    return {d.code for d in diags_of(text)}


def base(righe):
    return BASE % righe


# --- la chiave nuova ---------------------------------------------------------

def test_la_chiave_e_nota_al_blocco_engine():
    assert schema.key_in("engine_stream", "deviation_probability") is not None
    assert diags_of(base("  deviation_probability: 50\n")) == []


def test_false_e_una_scrittura_valida():
    assert diags_of(base("  deviation_probability: false\n")) == []


def test_un_envelope_globale_e_una_scrittura_valida():
    assert diags_of(base("  deviation_probability: [[0, 0], [30, 80]]\n")) == []


def test_la_forma_per_parametro_e_una_scrittura_valida():
    text = base("  deviation_probability:\n    volume: 50\n    pointer: null\n")
    assert diags_of(text) == []


def test_il_dict_vuoto_e_una_scrittura_valida():
    """``{}`` e' NeverGate, ed e' documentato come tale."""
    assert diags_of(base("  deviation_probability: {}\n")) == []


def test_read_direction_e_una_chiave_per_parametro():
    """PGE #207: il verso stocastico si dichiara di qui."""
    assert diags_of(base("  deviation_probability: {read_direction: 30}\n")) == []


def test_una_chiave_per_parametro_inventata_si_segnala():
    text = base("  deviation_probability: {colume: 50}\n")
    ds = [d for d in diags_of(text) if d.code == "unknown-key"]
    assert len(ds) == 1
    assert "volume" in ds[0].message


# --- la chiave morta ---------------------------------------------------------

def test_dephase_e_una_chiave_morta():
    """Rinominata senza alias di compatibilita': l'engine non la legge piu' e
    non se ne lamenta, quindi la probabilita' si perde in silenzio."""
    ds = [d for d in diags_of(base("  dephase: 50\n"))
          if d.code == "dephase-rinominata"]
    assert len(ds) == 1
    assert "deviation_probability" in ds[0].message


def test_dephase_ha_il_quick_fix_di_rinomina():
    uri = "file:///s.yml"
    doc = yamlpos.parse(base("  dephase: 50\n"))
    ds = [d for d in diagnostics.collect(doc, model.build(doc))
          if d.code == "dephase-rinominata"]
    acts = actions.quickfixes(doc, uri, ds)
    assert [a.edit.changes[uri][0].new_text for a in acts] == \
        ["deviation_probability"]


def test_dephase_non_e_una_chiave_sconosciuta():
    """Sconosciuta e' un'altra cosa: questa la conosciamo, ed e' morta."""
    assert "unknown-key" not in codes_of(base("  dephase: 50\n"))


def test_dephase_vuota_dice_una_cosa_sola():
    """La trappola della chiave vuota non vale su una chiave che nessuno
    legge: dirla qui manderebbe a cercare un jitter che non esiste."""
    got = codes_of(base("  dephase:\n"))
    assert "dephase-rinominata" in got
    assert "deviation-probability-implicita" not in got


def test_dentro_dephase_il_contesto_resta_quello_giusto():
    """Completion e hover di un blocco per-parametro valgono anche mentre lo
    si sta migrando."""
    assert schema.context_for_path(("base", "dephase"), frozenset()) == \
        "deviation_probability"


# --- la chiave scritta e lasciata vuota --------------------------------------

def test_la_chiave_vuota_non_e_assente():
    """E' la scrittura che piu' somiglia a «non voglio deviazione» e fa
    l'opposto: jitter implicito sull'1% dei grani."""
    ds = [d for d in diags_of(base("  deviation_probability:\n"))
          if d.code == "deviation-probability-implicita"]
    assert len(ds) == 1
    assert ds[0].severity == 2      # gira, ma non e' quello che sembra
    assert "1%" in ds[0].message


def test_la_chiave_assente_non_dice_niente():
    assert diags_of(base("  volume: -6\n")) == []


# --- il corpo che non si costruisce come envelope ---------------------------

def test_lista_vuota():
    assert "deviation-probability-corpo" in codes_of(
        base("  deviation_probability: []\n"))


def test_lista_di_non_breakpoint():
    assert "deviation-probability-corpo" in codes_of(
        base("  deviation_probability: [1, 2, 3]\n"))


def test_stringa():
    assert "deviation-probability-corpo" in codes_of(
        base("  deviation_probability: sempre\n"))


def test_il_corpo_di_una_chiave_per_parametro_segue_la_stessa_regola():
    ds = [d for d in diags_of(base("  deviation_probability: {volume: []}\n"))
          if d.code == "deviation-probability-corpo"]
    assert len(ds) == 1
    assert "volume" in ds[0].message


def test_un_envelope_per_parametro_passa():
    assert diags_of(
        base("  deviation_probability: {volume: [[0, 0], [30, 80]]}\n")) == []


def test_un_dict_con_points_e_un_envelope_globale():
    assert diags_of(
        base("  deviation_probability: {points: [[0, 0], [30, 80]]}\n")) == []


def test_un_generatore_non_viene_giudicato():
    """Il valore lo produce la pipeline prima che l'engine lo veda: giudicarlo
    qui significherebbe rifiutare uno YAML che il runtime accetta."""
    text = base('  deviation_probability: {expr: "p"}\n').replace(
        "axes:", "let:\n  p: 30\naxes:")
    assert "deviation-probability-corpo" not in codes_of(text)
