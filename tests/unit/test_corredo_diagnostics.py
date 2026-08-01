"""Le diagnostiche del corredo e dei due ruoli di una lista.

Sono quasi tutte **statiche**: l'editor le puo' dare mentre si scrive, ed e' li'
che vale piu' del runtime. I messaggi sono portati da granulation-studies, non
riscritti — due diagnostiche che dicono la stessa cosa con parole diverse sono
un bug di prodotto.
"""
import pathlib

import pytest

from glls import diagnostics, model, yamlpos

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

TESTA = """study_id: t
base: {onset: 0, duration: 6, sample: c.wav}
axes: {density: {baseline: 20, base: {expr: "%s"}, range: 1, n: 4}}
stack: {density: {base: 1, range: 2}}
"""


def _diags(text):
    doc = yamlpos.parse(text)
    return diagnostics.collect(doc, model.build(doc))


def _uno(text, code):
    got = [d for d in _diags(text) if d.code == code]
    assert got, "atteso %r, trovati: %s" % (
        code, [(d.code, d.message[:60]) for d in _diags(text)])
    return got[0]


def _con_let(let, expr="ratio[0]"):
    return TESTA % expr + "let:\n" + let + "\n"


# --- la dichiarazione del corredo --------------------------------------------

def test_corredo_vuoto():
    d = _uno(_con_let("  ratio: {list: []}"), "corredo")
    assert "niente da indicizzare" in d.message


def test_corredo_con_elementi_non_numerici():
    d = _uno(_con_let("  ratio: {list: [1, ciao]}"), "corredo")
    assert "non e' un numero" in d.message


def test_cycle_non_booleano():
    d = _uno(_con_let("  ratio: {list: [1, 2], cycle: forse}"), "corredo")
    assert "true o false" in d.message


def test_chiave_estranea_accanto_a_list():
    d = _uno(_con_let("  ratio: {list: [1, 2], pippo: 3}"), "corredo")
    assert "non ammesse" in d.message


def test_cycle_senza_list():
    """`cycle` e' la politica di un corredo, non un valore a se'."""
    d = _uno(_con_let("  x: {cycle: true}", expr="x"), "corredo")
    assert "senza 'list'" in d.message


# --- dentro `list:`: un corredo possiede la propria lunghezza ----------------

def test_linear_env_dentro_list():
    """Annidare un ruolo in un ruolo."""
    d = _uno(_con_let("  ratio: {list: {linear_env: [1, 2]}}"), "corredo")
    assert "forma nel tempo" in d.message


@pytest.mark.parametrize("ramp, manca", [
    ("{start: 1, step: 1}", "stop"),
    ("{start: 1, stop: 4}", "step"),
])
def test_ramp_parziale_dentro_list(ramp, manca):
    d = _uno(_con_let("  ratio: {list: {ramp: %s}}" % ramp), "corredo")
    assert "non possiede il proprio conteggio" in d.message
    assert manca in d.message


def test_banda_senza_n_dentro_list():
    d = _uno(_con_let("  ratio: {list: {base: 2, range: 6}}"), "corredo")
    assert "non possiede il proprio conteggio" in d.message


@pytest.mark.parametrize("dentro", [
    "[2, 3, 4, 7]",
    "{values: [2, 3, 4, 7]}",
    "{ramp: {start: 1, stop: 8, step: 1}}",
    "{n: 5, base: 2, range: 6, seed: 1988}",
])
def test_le_forme_ammesse_dentro_list_non_danno_rilievi(dentro):
    got = [d for d in _diags(_con_let("  ratio: {list: %s}" % dentro))
           if d.code == "corredo"]
    assert got == [], [d.message for d in got]


# --- i due ruoli di una lista ------------------------------------------------

@pytest.mark.parametrize("nudo", [
    "{values: [1, 2, 3]}",
    "{ramp: {start: 1, stop: 4, step: 1}}",
    "{n: 4, base: 1, range: 2}",
])
def test_generatore_nudo_in_un_let_vuole_linear_env(nudo):
    """Famiglia 1 in posizione di Famiglia 2: in un `let:` la posizione non
    disambigua i due ruoli, quindi il ruolo va marcato."""
    d = _uno(_con_let("  x: %s" % nudo, expr="x"), "linear-env-migrazione")
    assert "per tempo" in d.message and "linear_env" in d.message


def test_linear_env_in_un_let_e_corretto():
    got = [d for d in _diags(_con_let("  x: {linear_env: [1, 2, 3]}", expr="x"))
           if d.code in ("linear-env-migrazione", "linear-env-ruolo")]
    assert got == []


def test_linear_env_su_un_asse_e_errore():
    """Famiglia 2 in posizione di Famiglia 1: sull'asse la lista si legge per
    indice, la posizione k e' l'elemento k."""
    testo = (
        "study_id: t\n"
        "base: {onset: 0, duration: 6, sample: c.wav}\n"
        "axes: {density: {baseline: 20, linear_env: [10, 30]}}\n"
    )
    d = _uno(testo, "linear-env-ruolo")
    assert "per indice" in d.message


# --- dove vive un corredo ----------------------------------------------------

def test_corredo_in_spread_let_e_errore():
    """A livello di voce `i` e' gia' fissato: una lista qui non avrebbe nessun
    indice da cui essere letta."""
    testo = TESTA % "1" + (
        "streams:\n"
        "  g:\n"
        "    spread:\n"
        "      n: 2\n"
        "      let: {ratio: {list: [1, 2]}, r: {expr: 'ratio[i]'}}\n"
        "      over: {base.pan: {expr: 'i'}}\n"
    )
    d = _uno(testo, "corredo")
    assert "spread.let" in d.message or "livello di voce" in d.message


# --- versions e percorso muovono il valore, non il tipo ----------------------

_VERS = (
    "study_id: t\n"
    "base: {onset: 0, duration: 6, sample: c.wav}\n"
    "axes: {density: {baseline: 20, base: {expr: 'ratio[0]'}, range: 1, n: 4}}\n"
    "stack: {density: {base: 1, range: 2}}\n"
    "let: {ratio: {list: [2, 3]}}\n"
    "versions:\n"
    "  a:\n"
    "    x: {ratio: {list: [2, 3]}}\n"
    "    y: {ratio: %s}\n"
)


def test_versions_non_puo_sostituire_un_corredo_con_altro():
    d = _uno(_VERS % "5", "corredo-mosso")
    assert "mai il suo tipo" in d.message


def test_versions_non_puo_cambiare_la_politica_di_cycle():
    d = _uno(_VERS % "{list: [2, 3], cycle: true}", "corredo-mosso")
    assert "cycle" in d.message


def test_versions_puo_sostituire_un_corredo_con_un_corredo():
    got = [d for d in _diags(_VERS % "{list: [2, 3, 4]}") if d.code == "corredo-mosso"]
    assert got == []


def test_percorso_non_puo_muovere_un_corredo():
    testo = (
        "study_id: t\n"
        "base: {onset: 0, duration: 6, sample: c.wav}\n"
        "axes: {density: {baseline: 20, base: {expr: 'ratio[0]'}, range: 1, n: 4}}\n"
        "stack: {density: {base: 1, range: 2}}\n"
        "let: {ratio: {list: [2, 3]}}\n"
        "percorso: {ratio: {base: 1, range: 2}}\n"
    )
    d = _uno(testo, "corredo-mosso")
    assert "traiettoria" in d.message


# --- il corredo sotto-consumato: warning, non errore -------------------------

_SOTTO = """study_id: t
base: {onset: 0, duration: 6, sample: c.wav}
axes: {density: {baseline: 20, values: [10, 30]}}
let: {ratio: {list: [2, 3, 4, 7]}}
streams:
  g:
    spread:
      n: %s
      let: {r: {expr: "%s"}}
      over: {base.pointer.start: {ramp: {start: 0.1, step: 0.2}}}
"""


def test_corredo_sotto_consumato_e_un_warning():
    from lsprotocol import types

    d = _uno(_SOTTO % (2, "ratio[i]"), "corredo-sotto-consumato")
    assert d.severity == types.DiagnosticSeverity.Warning
    assert "4 elementi" in d.message and "2 voci" in d.message


def test_il_rilievo_nomina_gli_indici_davvero_inutilizzati():
    """«Da indice n» vale solo per l'indice identita': con `ratio[i + 2]` le
    voci leggono 2 e 3, quindi restano fuori 0 e 1."""
    d = _uno(_SOTTO % (2, "ratio[i + 2]"), "corredo-sotto-consumato")
    assert "0, 1" in d.message


def test_nessun_rilievo_quando_il_corredo_e_consumato():
    got = [d for d in _diags(_SOTTO % (4, "ratio[i]"))
           if d.code == "corredo-sotto-consumato"]
    assert got == []


def test_nessun_rilievo_con_indice_costante():
    """`ratio[0]` e' la fondamentale: non ne consuma nemmeno uno oltre il
    primo, ed e' esattamente cio' che si voleva."""
    got = [d for d in _diags(_SOTTO % (2, "ratio[0] * i"))
           if d.code == "corredo-sotto-consumato"]
    assert got == []


# --- il completamento propone il ruolo giusto per il contesto ----------------
#
# E' il guadagno dichiarato della separazione: `values:` dove la lista si legge
# per indice, `linear_env:` dove si legge per tempo. Proporre il wrapper
# sbagliato significherebbe suggerire l'errore che il runtime rifiuta.

def _chiavi(contesto):
    from glls import schema

    return {k.name for k in schema.keys_for(contesto)}


def test_il_vocabolario_dei_generatori_vale_in_entrambi_i_ruoli():
    for contesto in ("env", "axis", "spread_strategy"):
        assert {"values", "ramp", "base"} <= _chiavi(contesto), contesto


@pytest.mark.parametrize("contesto", ["axis", "spread_strategy"])
def test_in_famiglia_1_non_si_propongono_i_wrapper_di_ruolo(contesto):
    """Sull'asse e nelle strategy la posizione disambigua gia'."""
    assert not ({"linear_env", "list", "cycle"} & _chiavi(contesto))


def test_in_famiglia_2_si_propongono_i_wrapper_di_ruolo():
    """Il valore di una manopola di `let:` e i bordi di un `Env`."""
    assert {"linear_env", "list", "cycle"} <= _chiavi("env")
