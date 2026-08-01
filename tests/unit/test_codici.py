"""Il contratto sui codici diagnostici, e la sua tenuta.

Un codice e' l'identificatore con cui un consumatore **agisce** su una
diagnostica: un editor che spegne una regola, un test che ne cerca una. Per i
codici condivisi con `granulation-studies` la stringa e' un'API fra i due
repo, e rinominarla da un lato rompe silenziosamente chi filtra dall'altro.

Qui si fissa quella stringa alla lettera, e — quando `granstudies` e'
importabile, cioe' per chi ha entrambi i repo — si verifica che i due lati
dicano davvero la stessa cosa. In CI la verifica incrociata si salta: gl-ls
non dipende dal runtime, ed e' proprio il punto del contratto.
"""
import pytest

from glls import codes, diagnostics, model, yamlpos


def _diags(text):
    doc = yamlpos.parse(text)
    return diagnostics.collect(doc, model.build(doc))


# --- il lato gl-ls: le stringhe sono fissate ---------------------------------

def test_il_codice_condiviso_e_esattamente_questo():
    """Fissato alla lettera: e' un'API, non un dettaglio di formattazione."""
    assert codes.CORREDO_SOTTO_CONSUMATO == "corredo-sotto-consumato"


def test_le_due_categorie_sono_disgiunte():
    assert not (codes.SHARED & codes.STATIC_ONLY)
    assert codes.CORREDO_CODES == codes.SHARED | codes.STATIC_ONLY


def test_ogni_codice_ha_una_descrizione():
    """Serve a un consumatore che mostri la regola in un pannello."""
    assert set(codes.DESCRIZIONI) == codes.CORREDO_CODES


# --- il lato emissione: nessun codice ad hoc sfugge al registro --------------

_CASI = [
    # (yaml, codice atteso)
    ("let:\n  ratio: {list: []}\n", codes.CORREDO),
    ("let:\n  x: {values: [1, 2, 3]}\n", codes.LINEAR_ENV_MIGRAZIONE),
]

_TESTA = """study_id: t
base: {onset: 0, duration: 6, sample: c.wav}
axes: {density: {baseline: 20, base: {expr: "ratio[0]"}, range: 1, n: 4}}
stack: {density: {base: 1, range: 2}}
"""

_SOTTO = """study_id: t
base: {onset: 0, duration: 6, sample: c.wav}
axes: {density: {baseline: 20, values: [10, 30]}}
let: {ratio: {list: [2, 3, 4, 7]}}
streams:
  g:
    spread:
      n: 2
      let: {r: {expr: "ratio[i]"}}
      over: {base.pointer.start: {ramp: {start: 0.1, step: 0.2}}}
"""


@pytest.mark.parametrize("corpo, atteso", _CASI)
def test_i_codici_emessi_vengono_dal_registro(corpo, atteso):
    got = {d.code for d in _diags(_TESTA + corpo)}
    assert atteso in got
    assert got & codes.CORREDO_CODES <= codes.CORREDO_CODES


def test_il_warning_condiviso_usa_il_codice_condiviso():
    got = [d for d in _diags(_SOTTO) if d.code in codes.SHARED]
    assert len(got) == 1
    assert got[0].code == codes.CORREDO_SOTTO_CONSUMATO


# --- la verifica incrociata col runtime, quando c'e' -------------------------

def _granstudies_codes():
    """I codici del runtime, se `granstudies` e' installato accanto."""
    try:
        from granstudies import diagnostics as gs  # type: ignore
    except Exception:
        return None
    return gs


@pytest.mark.skipif(_granstudies_codes() is None,
                    reason="granstudies non importabile: la verifica "
                           "incrociata vale per chi ha entrambi i repo")
def test_il_codice_condiviso_coincide_col_runtime():
    """Il cuore del contratto: se il runtime rinomina, questo test cade."""
    gs = _granstudies_codes()
    assert gs.CORREDO_SOTTO_CONSUMATO == codes.CORREDO_SOTTO_CONSUMATO


@pytest.mark.skipif(_granstudies_codes() is None,
                    reason="granstudies non importabile")
def test_ogni_codice_del_runtime_e_dichiarato_condiviso():
    """Un codice nuovo lato runtime non deve restare ignoto a gl-ls: o e'
    condiviso e va in SHARED, o e' fuori dal corredo e non riguarda questo
    registro."""
    gs = _granstudies_codes()
    del_runtime = {
        v for k, v in vars(gs).items()
        if k.isupper() and isinstance(v, str) and v.startswith("corredo")
    }
    assert del_runtime <= codes.SHARED, (
        "codici del runtime non dichiarati in codes.SHARED: "
        f"{sorted(del_runtime - codes.SHARED)}"
    )
