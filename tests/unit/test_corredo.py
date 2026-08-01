"""Il corredo (``list:``) e il wrapper ``linear_env:`` visti dall'editor.

Porto di `granulation-studies` #48-#54: un **corredo** e' una lista nominata,
dichiarata in un ``let:`` e letta **solo per indice**. La grammatica di
``expr`` acquista due produzioni, ``nome[expr]`` e ``len(nome)``, e nient'altro:
la linea di confine e' che *una lista non e' mai un valore*.

Questi test coincidono con `tests/test_corredo.py` di granulation-studies: la
diagnostica dell'editor deve dire le stesse cose del runtime, o le due
divergono e l'editor diventa rumore.
"""
import pathlib

import pytest

from glls import diagnostics, model, yamlpos
from glls.exprlang import eval_expr, names_in

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _diags(text):
    doc = yamlpos.parse(text)
    return diagnostics.collect(doc, model.build(doc))


ACCORDO = {"ratio": {"list": [2, 3, 4, 7]}}
PATTERN = {"ratio": {"list": [2, 3, 4, 7], "cycle": True}}


# --- l'indicizzazione --------------------------------------------------------

def test_indice_costante():
    assert eval_expr("ratio[0]", ACCORDO) == 2
    assert eval_expr("ratio[3]", ACCORDO) == 7


def test_indice_calcolato():
    assert eval_expr("ratio[i]", {**ACCORDO, "i": 2}) == 4


def test_indice_negativo_e_l_ultimo():
    assert eval_expr("ratio[-1]", ACCORDO) == 7
    assert eval_expr("ratio[-4]", ACCORDO) == 2


def test_fuori_range_su_accordo_e_errore():
    """Mai tiene-l'ultimo: un accordo e' un insieme fisso, il quinto elemento
    di quattro e' una domanda sbagliata."""
    with pytest.raises(ValueError, match="fuori dal corredo"):
        eval_expr("ratio[4]", ACCORDO)
    with pytest.raises(ValueError, match="fuori dal corredo"):
        eval_expr("ratio[-5]", ACCORDO)


def test_su_pattern_l_indice_si_avvolge():
    """Il quinto elemento *e'* il primo: la politica la decide il corredo."""
    assert eval_expr("ratio[4]", PATTERN) == 2
    assert eval_expr("ratio[9]", PATTERN) == 3


def test_su_pattern_i_negativi_cadono_fuori_dal_modulo():
    assert eval_expr("ratio[-1]", PATTERN) == 7


def test_indice_float_con_valore_intero_e_valido():
    """``4 / 2`` vale 2.0, che *e'* un intero: la guardia e' sui frazionari."""
    assert eval_expr("ratio[4 / 2]", ACCORDO) == 4


def test_indice_frazionario_e_errore_con_hint():
    with pytest.raises(ValueError, match="non e' intero"):
        eval_expr("ratio[2.5]", ACCORDO)
    with pytest.raises(ValueError, match="floor"):
        eval_expr("ratio[2.5]", ACCORDO)


def test_quantizzare_con_floordiv_funziona():
    assert eval_expr("ratio[7 // 2]", ACCORDO) == 7


def test_indicizzare_un_non_corredo_e_errore():
    with pytest.raises(ValueError, match="non e' un corredo"):
        eval_expr("x[0]", {"x": [[0, 1], [1, 2]]})


def test_indicizzare_un_nome_ignoto_e_errore():
    with pytest.raises(ValueError, match="nome ignoto"):
        eval_expr("zzz[0]", ACCORDO)


# --- la linea di confine: una lista non e' mai un valore ---------------------

def test_il_nome_nudo_e_errore():
    with pytest.raises(ValueError, match="si legge solo per indice"):
        eval_expr("ratio", ACCORDO)


def test_aritmetica_su_un_corredo_e_errore():
    with pytest.raises(ValueError, match="si legge solo per indice"):
        eval_expr("ratio + 1", ACCORDO)


@pytest.mark.parametrize("testo", ["min(ratio, 2)", "abs(ratio)", "mix(ratio, 1, 0.5)"])
def test_un_corredo_non_si_passa_a_una_funzione(testo):
    with pytest.raises(ValueError, match="si legge solo per indice"):
        eval_expr(testo, ACCORDO)


def test_la_base_dell_indice_e_un_nome_non_un_espressione():
    with pytest.raises(ValueError, match="solo un corredo per nome"):
        eval_expr("ratio[0][0]", ACCORDO)


# --- len() -------------------------------------------------------------------

def test_len_di_un_corredo():
    assert eval_expr("len(ratio)", ACCORDO) == 4


def test_len_dentro_un_indice():
    """L'idioma del ciclo scritto a mano."""
    assert eval_expr("ratio[i % len(ratio)]", {**ACCORDO, "i": 5}) == 3


def test_len_di_un_envelope_e_errore():
    """Quanti breakpoint ha un Env e' un dettaglio di rappresentazione: farlo
    trapelare renderebbe le espressioni dipendenti dall'implementazione."""
    with pytest.raises(ValueError, match="vuole un corredo"):
        eval_expr("len(x)", {"x": [[0, 1], [1, 2]]})


def test_len_di_uno_scalare_e_errore():
    with pytest.raises(ValueError, match="vuole un corredo"):
        eval_expr("len(x)", {"x": 5})


def test_len_di_un_nome_ignoto_e_errore():
    with pytest.raises(ValueError, match="nome ignoto"):
        eval_expr("len(zzz)", ACCORDO)


def test_len_vuole_un_nome_non_un_espressione():
    with pytest.raises(ValueError, match="solo un corredo per nome"):
        eval_expr("len(1 + 2)", ACCORDO)


# --- il corredo in scope -----------------------------------------------------

def test_un_corredo_vuoto_in_scope_e_errore():
    with pytest.raises(ValueError, match="vuoto o malformato"):
        eval_expr("x[0]", {"x": {"list": []}})


def test_un_corredo_con_elementi_non_scalari_e_errore():
    with pytest.raises(ValueError, match="non scalari"):
        eval_expr("x[0]", {"x": {"list": [1, "a"]}})


def test_un_corredo_generato_non_arriva_mai_in_scope():
    """Si dichiara in un ``let:`` che lo risolve al load; qui arriva gia' fatto."""
    with pytest.raises(ValueError, match="non e' stato generato"):
        eval_expr("x[0]", {"x": {"list": {"ramp": {"start": 1, "stop": 4, "step": 1}}}})


def test_cycle_non_booleano_e_errore():
    with pytest.raises(ValueError, match="vuole true o false"):
        eval_expr("x[0]", {"x": {"list": [1, 2], "cycle": "si"}})


# --- names_in: allineamento con granstudies.inject.expr_names ----------------
#
# gl-ls escludeva i nomi di funzione **per sottrazione**; granstudies dopo #55
# esclude il solo ``Call.func``. Le due strade divergono su due casi, ed e'
# la divergenza a rendere sbagliata la guardia «manopola non referenziata».

def test_names_in_ignora_il_bersaglio_della_chiamata():
    assert names_in("min(a, 10)") == {"a"}


def test_names_in_non_conta_len_come_manopola():
    """Altrimenti: falso «manopola 'len' non dichiarata»."""
    assert names_in("len(ratio)") == {"ratio"}


def test_names_in_vede_un_argomento_omonimo_di_una_primitiva():
    """Una manopola che si chiama come una primitiva, *usata come argomento*,
    resta referenziata: e' escluso il solo bersaglio della chiamata."""
    assert names_in("min(abs, 2)") == {"abs"}


def test_names_in_registra_il_corredo_e_l_indice():
    assert names_in("ratio[i]") == {"ratio", "i"}


# --- la sonda: uno study.yml valido per il runtime non deve dare rilievi ------
#
# Questo file e' verificato valido su granulation-studies@main (genera 4
# stream). Prima di questo lavoro gl-ls ci produceva sopra 9 diagnostiche, 5
# delle quali errori: e' il criterio di successo della issue #40, e resta qui
# come regressione permanente.

def test_la_sonda_del_corredo_non_produce_diagnostiche():
    testo = (FIXTURES / "corredo_completo.yml").read_text()
    got = _diags(testo)
    assert got == [], "\n".join(f"{d.code}: {d.message}" for d in got)


# --- le chiavi nuove sono note allo schema -----------------------------------

@pytest.mark.parametrize("chiave", ["list", "cycle", "linear_env"])
def test_le_chiavi_del_corredo_non_sono_sconosciute(chiave):
    """`unknown-key` su una chiave valida e' rumore sui file dell'utente."""
    testo = (FIXTURES / "corredo_completo.yml").read_text()
    codici = [(d.code, d.message) for d in _diags(testo)]
    assert not [m for c, m in codici if c == "unknown-key" and f"'{chiave}'" in m]


# --- lo scope di spread.n ----------------------------------------------------
#
# Il runtime **inietta** le manopole di documento e di gruppo nel nodo-expr di
# ``spread.n`` prima di valutarlo (verificato: `n: {expr: "k"}` con `k: 3` nel
# `let:` genera 3 voci). gl-ls valutava col solo `let` locale, quindi dava
# «nome ignoto» su codice giusto — un difetto **preesistente al corredo**, che
# `len(ratio)` ha solo reso visibile.
#
# Restano fuori `spread.let`, `i` e `n`: quelli lo spread li possiede, e al
# momento in cui `n` si calcola non esistono ancora.

_BASE_N = """study_id: t
base: {onset: 0, duration: 6, sample: c.wav}
axes: {density: {baseline: 20, values: [10, 30]}}
let: {k: 3%s}
streams:
  g:
    spread:
      n: {expr: "%s"}
      let: {r: {expr: "i * k"}}
      over: {base.pointer.start: {ramp: {start: 0.1, step: 0.2}}}
"""


def test_spread_n_legge_una_manopola_di_documento():
    got = [d for d in _diags(_BASE_N % ("", "k")) if d.code in ("expr", "spread-no-n")]
    assert got == [], "\n".join(d.message for d in got)


def test_spread_n_legge_len_di_un_corredo():
    testo = _BASE_N % (", ratio: {list: [2, 3, 4, 7]}", "len(ratio)")
    got = [d for d in _diags(testo) if d.code in ("expr", "spread-no-n")]
    assert got == [], "\n".join(d.message for d in got)


@pytest.mark.parametrize("nome", ["r", "i", "n"])
def test_spread_n_non_vede_le_manopole_di_voce_ne_i_ne_n(nome):
    """Al momento in cui `n` si calcola, `spread.let` non esiste ancora."""
    got = [d for d in _diags(_BASE_N % ("", nome)) if d.code == "expr"]
    assert any("nome ignoto" in d.message for d in got)
