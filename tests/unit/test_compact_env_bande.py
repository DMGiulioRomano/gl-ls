"""Forma compatta a cicli fuori da ``let:`` — bande e camminata (issue #29).

In granstudies l'espansione vive in ``value_generators.expand_env``, la seam che
attraversa *ogni* Env: non solo le manopole di ``let:``, ma anche i ``Threshold``
di banda e camminata, via ``expand_params``. Quindi la forma compatta funziona —
e i suoi due vincoli valgono — anche in ``axes.<p>.base``/``range``,
``stack.<p>.base``/``range``, ``drift.step`` e nelle bande di ``spread``.

Parita' verificata sul runtime: ``expand_params({'base': [[[0,0],[25,1]], 50, 4],
...})`` alza ``base: forma compatta, end_time deve essere 1 (ricevuto 50)`` in
tutte queste posizioni.
"""
from lsprotocol import types

from glls import diagnostics, hover, inlay, model, yamlpos

BASE = """study_id: t
duration: 20
base:
  onset: 0
  duration: 6
  sample: corpus.wav
axes:
  density:
    baseline: 20
    values: [10, 30]
"""

VENTAGLIO = "[[[0, 0], [25, 1]], 1, 4]"
IN_SECONDI = "[[[0, 0], [25, 1]], 50, 4]"


def _codes(text):
    doc = yamlpos.parse(text)
    return {d.code for d in diagnostics.collect(doc, model.build(doc))}


def _axis(base, extra=""):
    return BASE.replace("    values: [10, 30]\n",
                        f"    base: {base}\n    range: 1\n    n: 4\n{extra}")


# --- banda di asse ------------------------------------------------------------


def test_asse_base_end_time_in_secondi_e_errore():
    assert "compact-end-time" in _codes(_axis(IN_SECONDI))


def test_asse_base_forma_compatta_valida_resta_pulita():
    assert "compact-end-time" not in _codes(_axis(VENTAGLIO))


def test_asse_range_end_time_in_secondi_e_errore():
    text = BASE.replace("    values: [10, 30]\n",
                        f"    base: 20\n    range: {IN_SECONDI}\n    n: 4\n")
    assert "compact-end-time" in _codes(text)


def test_asse_punto_del_pattern_a_tre_elementi_e_errore():
    assert "compact-point" in _codes(_axis("[[[0, 0], [25, 1, 'step']], 1, 4]"))


def test_asse_x_fuori_scala_e_warning():
    doc = yamlpos.parse(_axis("[[[0, 0], [125, 1]], 1, 4]"))
    warns = [d for d in diagnostics.collect(doc, model.build(doc))
             if d.code == "compact-x"]
    assert len(warns) == 1
    assert warns[0].severity == types.DiagnosticSeverity.Warning


def test_il_messaggio_non_cita_piu_il_let():
    doc = yamlpos.parse(_axis(IN_SECONDI))
    (d,) = [x for x in diagnostics.collect(doc, model.build(doc))
            if x.code == "compact-end-time"]
    assert "let" not in d.message
    assert "asse normalizzato in [0, 1]" in d.message
    assert d.message.startswith("Asse 'density' base:")


def test_la_diagnostica_punta_all_end_time():
    text = _axis(IN_SECONDI)
    doc = yamlpos.parse(text)
    (d,) = [x for x in diagnostics.collect(doc, model.build(doc))
            if x.code == "compact-end-time"]
    line = text.splitlines()[d.range.start.line]
    assert line[d.range.start.character:d.range.end.character] == "50"


# --- drift --------------------------------------------------------------------


def test_drift_step_end_time_in_secondi_e_errore():
    text = _axis("20", extra=f"    drift:\n      step: {IN_SECONDI}\n")
    assert "compact-end-time" in _codes(text)


def test_drift_step_label_nomina_la_chiave():
    text = _axis("20", extra=f"    drift:\n      step: {IN_SECONDI}\n")
    doc = yamlpos.parse(text)
    (d,) = [x for x in diagnostics.collect(doc, model.build(doc))
            if x.code == "compact-end-time"]
    assert d.message.startswith("Asse 'density' drift.step:")


# --- camminata-X (stack) ------------------------------------------------------


STACK = BASE.replace("    values: [10, 30]\n", "    base: 5\n    range: 15\n")


def test_camminata_base_end_time_in_secondi_e_errore():
    text = STACK + f"stack:\n  density:\n    base: {IN_SECONDI}\n    range: 1\n"
    assert "compact-end-time" in _codes(text)


def test_camminata_base_forma_compatta_valida_resta_pulita():
    text = STACK + f"stack:\n  density:\n    base: {VENTAGLIO}\n    range: 1\n"
    assert "compact-end-time" not in _codes(text)


# --- bande di spread ----------------------------------------------------------


def test_spread_over_banda_end_time_in_secondi_e_errore():
    text = BASE + f"""streams:
  fan:
    spread:
      over:
        base.volume:
          base: {IN_SECONDI}
          range: 2
          n: 3
"""
    assert "compact-end-time" in _codes(text)


def test_spread_let_banda_end_time_in_secondi_e_errore():
    # la banda di spread.let passa da expand_params come le altre: il vincolo
    # vale (a differenza del valore *diretto* di una manopola di voce, che il
    # resolver dello spread non espande affatto)
    text = BASE + f"""streams:
  fan:
    spread:
      over:
        base.onset: {{values: [0, 1, 2]}}
      let:
        liv:
          base: {IN_SECONDI}
          range: 2
"""
    assert "compact-end-time" in _codes(text)


# --- feature d'appoggio -------------------------------------------------------


def test_hover_sulla_chiave_base_porta_la_legenda():
    text = _axis(VENTAGLIO)
    doc = yamlpos.parse(text)
    row = next(i for i, l in enumerate(text.splitlines())
               if l.startswith("    base:"))
    h = hover.hover(doc, model.build(doc), row, 4)
    assert h is not None
    assert "4 cicli · vertice 25%" in h.contents.value
    assert "end_time` deve essere `1`" in h.contents.value


def test_inlay_hint_sulla_banda_di_asse():
    text = _axis(VENTAGLIO)
    doc = yamlpos.parse(text)
    labels = [x.label
              for x in inlay.hints(doc, model.build(doc), 0,
                                   len(text.splitlines()))]
    assert "4 cicli · vertice 25%" in labels


# --- niente falsi positivi ----------------------------------------------------


def test_env_disegnato_in_banda_resta_pulito():
    assert _codes(_axis("[[0, 10], [1, 30]]")) == set()


def test_shorthand_in_banda_resta_pulito():
    assert _codes(_axis("[10, 30]")) == set()
