"""``grain.read_direction``: il verso di lettura interno al grano (PGE #207).

Una chiave con due stati, `-1` e `+1`, e tre regole che scendono da quella
natura: il dominio e' un **insieme** (non l'intervallo fra i due), `step` e'
l'interpolazione imposta e implicita, e la chiave e' **alternativa** a
`grain.reverse` — insieme sono un errore, non una priorita'. L'engine le fa
rispettare sempre come errore esplicito, mai come correzione silenziosa: qui
si dicono un passo prima.
"""
from glls import diagnostics, engine_info as EI, model, schema, yamlpos

BASE = """study_id: t
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


def diags_of(text):
    doc = yamlpos.parse(text)
    return diagnostics.collect(doc, model.build(doc))


def codes_of(text):
    return {d.code for d in diags_of(text)}


def grain(righe):
    return BASE % righe


# --- la chiave esiste --------------------------------------------------------

def test_la_chiave_e_nota_al_contesto_grain():
    assert schema.key_in("grain", "read_direction") is not None
    assert "unknown-key" not in codes_of(grain("    read_direction: 1\n"))


def test_e_un_path_engine_noto():
    """Prima era ignota al registro, quindi un asse su di lei era
    'unknown-path'."""
    assert "grain.read_direction" in EI.known_paths()
    text = """study_id: t
base: {onset: 0, duration: 6, sample: c.wav}
axes:
  verso:
    path: grain.read_direction
    baseline: 1
    values: [-1, 1]
"""
    assert "unknown-path" not in codes_of(text)


def test_senza_default_engine_l_asse_pretende_il_baseline():
    """Chiave assente = modalita' auto, non un valore: non c'e' un default da
    cui partire."""
    assert EI.needs_baseline("grain.read_direction")


# --- il dominio e' un insieme -----------------------------------------------

def test_i_due_versi_passano():
    for v in ("-1", "1", "+1", "-1.0"):
        assert diags_of(grain(f"    read_direction: {v}\n")) == [], v


def test_lo_zero_non_ha_un_segno():
    assert "read-direction-valore" in codes_of(grain("    read_direction: 0\n"))


def test_un_valore_intermedio_non_e_un_verso():
    ds = [d for d in diags_of(grain("    read_direction: 0.3\n"))
          if d.code == "read-direction-valore"]
    assert len(ds) == 1
    assert "arrotond" in ds[0].message


def test_un_valore_fuori_scala_e_errore_una_volta_sola():
    """Il dominio e' piu' stretto dei bounds: se parlassero tutti e due, la
    stessa riga porterebbe due diagnostiche."""
    ds = [d for d in diags_of(grain("    read_direction: 5\n")) if d.code]
    assert [d.code for d in ds] == ["read-direction-valore"]


def test_true_non_e_piu_uno():
    assert "read-direction-valore" in codes_of(grain("    read_direction: true\n"))


def test_gli_y_di_un_envelope_stanno_nello_stesso_insieme():
    ok = "    read_direction: [[0, -1], [0.5, 1], [1, -1]]\n"
    assert diags_of(grain(ok)) == []
    ko = "    read_direction: [[0, -1], [0.5, 0], [1, 1]]\n"
    assert "read-direction-valore" in codes_of(grain(ko))


def test_gli_y_dentro_points_contano():
    ko = "    read_direction: {points: [[0, -1], [1, 0.5]]}\n"
    assert "read-direction-valore" in codes_of(grain(ko))


# --- step e' l'interpolazione, non un'opzione -------------------------------

def test_step_esplicito_e_ridondanza_accettata():
    text = grain("    read_direction: {type: step, points: [[0, -1], [1, 1]]}\n")
    assert diags_of(text) == []


def test_un_type_dichiarato_diverso_da_step_e_errore():
    text = grain("    read_direction: {type: linear, points: [[0, -1], [1, 1]]}\n")
    ds = [d for d in diags_of(text) if d.code == "read-direction-interp"]
    assert len(ds) == 1
    assert "step" in ds[0].message


def test_il_tag_per_punto_e_soggetto_alla_stessa_regola():
    text = grain("    read_direction: [[0, -1], [0.5, 1, cubic], [1, -1]]\n")
    assert "read-direction-interp" in codes_of(text)


def test_l_interp_di_un_bp_group_e_soggetto_alla_stessa_regola():
    text = grain("    read_direction: [[[0, -1], [1, 1]], 'linear']\n")
    assert "read-direction-interp" in codes_of(text)


def test_un_bp_group_a_step_passa():
    text = grain("    read_direction: [[[0, -1], [1, 1]], 'step']\n")
    assert diags_of(text) == []


def test_l_interp_di_una_forma_compatta_e_soggetto_alla_stessa_regola():
    text = grain("    read_direction: [[[0, -1], [50, 1]], 1, 4, 'linear']\n")
    assert "read-direction-interp" in codes_of(text)


def test_una_forma_compatta_senza_interp_passa():
    text = grain("    read_direction: [[[0, -1], [50, 1]], 1, 4]\n")
    assert diags_of(text) == []


# --- la coppia esclusiva -----------------------------------------------------

def test_le_due_chiavi_del_verso_insieme_sono_un_errore():
    text = grain("    read_direction: 1\n    reverse:\n")
    ds = [d for d in diags_of(text) if d.code == "read-direction-coppia"]
    assert len(ds) == 1
    assert "reverse" in ds[0].message


def test_reverse_da_sola_resta_valida():
    assert diags_of(grain("    reverse:\n")) == []


def test_nessuna_delle_due_e_la_modalita_auto():
    assert diags_of(grain("    envelope: hanning\n")) == []


# --- cio' che non si valuta --------------------------------------------------

def test_un_nodo_expr_non_viene_giudicato():
    """Il valore lo produce ``_resolve_expr_nodes`` prima che l'engine lo
    veda: qui non c'e' niente da controllare, e inventarsi un verdetto
    significherebbe rifiutare uno YAML che il runtime accetta."""
    text = grain('    read_direction: {expr: "verso"}\n').replace(
        "axes:", "let:\n  verso: 1\naxes:")
    assert not [d for d in diags_of(text) if str(d.code).startswith("read-direction")]
