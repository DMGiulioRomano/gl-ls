"""Lo stato del processo stack e' per-stream, non di documento.

Il runtime valida il documento **merged per stream** (``study_spec:836``): la
``stack:`` di una entry di ``streams:`` diventa top-level del documento di
quello stream, quindi il processo puo' essere attivo per uno solo, e una
camminata-X puo' comparire — o sparire, con ``asse: null`` — a livello di
override. gl-ls leggeva entrambe le cose sul documento base:

- ``stack-duration`` usciva subito se non c'era un ``stack:`` top-level, e
  taceva su uno stream che ne dichiarava uno proprio senza risolvere una
  durata (falso negativo);
- ``n-ownership`` leggeva la camminata solo dal blocco di documento: una
  camminata dichiarata in un override non la vedeva (falso positivo), e una
  annullata in un override non la vedeva sparire (falso negativo).

Qui si fissano i tre casi e i loro contrari, cosi' che nessuna delle due
diagnostiche torni a decidere sul documento invece che sullo stream.
"""
from glls import diagnostics, model, yamlpos

# banda-Y senza 'n' (la n-ownership la pretende dalla X) e nessuna durata di
# documento: le due cose che le due diagnostiche guardano
DOC = """study_id: t
base:
  onset: 0
  sample: corpus.wav
axes:
  density: {baseline: 20, base: 5, range: 10}
"""


def codes(tail):
    doc = yamlpos.parse(DOC + tail)
    m = model.build(doc)
    return sorted(d.code for d in diagnostics.collect(doc, m))


def message(tail, code):
    doc = yamlpos.parse(DOC + tail)
    m = model.build(doc)
    return next(d.message for d in diagnostics.collect(doc, m) if d.code == code)


# --- stack-duration: la presenza dello stack e' per-stream ------------------


def test_stack_in_the_document_still_asks_for_a_duration():
    assert codes("stack:\n  density: {base: 5}\n") == ["stack-duration"]


def test_stack_declared_only_in_a_stream_override():
    # nessuno 'stack:' top-level: prima era muto, e il runtime alzava SpecError
    tail = """streams:
  a:
    stack:
      density: {base: 5}
"""
    assert "stack-duration" in codes(tail)
    assert "'a'" in message(tail, "stack-duration")


def test_stack_in_a_stream_with_its_own_duration_is_clean():
    assert codes("""streams:
  a:
    duration: 30
    stack:
      density: {base: 5}
""") == []


def test_stack_in_a_stream_covered_by_the_document_default():
    doc = yamlpos.parse(
        DOC.replace("  onset: 0\n", "  onset: 0\n  duration: 30\n")
        + "streams:\n  a:\n    stack:\n      density: {base: 5}\n")
    m = model.build(doc)
    assert [d.code for d in diagnostics.collect(doc, m)] == []


def test_a_stream_without_its_own_stack_is_not_in_the_process():
    # nessuno stack da nessuna parte: la durata non serve a nessuno
    assert "stack-duration" not in codes("streams:\n  a:\n    base: {volume: -6}\n")


def test_only_the_stream_that_declares_the_stack_is_flagged():
    tail = """streams:
  a:
    stack: {density: {base: 5}}
  b:
    base: {volume: -6}
"""
    assert message(tail, "stack-duration").count("'a'") == 1
    assert "'b'" not in message(tail, "stack-duration")


# --- n-ownership: anche la camminata e' per-stream --------------------------


def test_walk_declared_in_an_override_is_seen():
    # falso positivo storico: la camminata c'e', ma non nel blocco di documento
    assert "n-ownership" not in codes("""streams:
  a:
    duration: 30
    stack:
      density: {base: 5}
""")


def test_walk_declared_with_a_dotted_key_is_seen():
    assert "n-ownership" not in codes("""streams:
  a:
    duration: 30
    stack.density.base: 5
""")


def test_walk_missing_in_one_stream_still_flagged():
    # basta un gruppo scoperto: quello stream fallisce davvero
    assert "n-ownership" in codes("""streams:
  a:
    duration: 30
    stack: {density: {base: 5}}
  b:
    duration: 30
    base: {volume: -6}
""")


def test_walk_annulled_by_an_override_uncovers_that_stream():
    # falso negativo speculare: 'asse: null' riporta a linear per quello
    # stream, e la banda-Y senza 'n' resta senza padrone
    tail = """stack:
  density: {base: 5}
streams:
  a:
    duration: 30
    stack: {density: null}
"""
    assert "n-ownership" in codes(tail)
    # il messaggio deve dire chi la annulla, altrimenti sembra sbagliato
    assert "'a'" in message(tail, "n-ownership")


def test_document_walk_inherited_by_an_untouched_stream():
    assert "n-ownership" not in codes("""stack:
  density: {base: 5}
streams:
  a:
    duration: 30
    base: {volume: -6}
""")


def test_annulled_walk_with_an_own_n_is_covered():
    assert "n-ownership" not in codes("""stack:
  density: {base: 5}
streams:
  a:
    duration: 30
    stack: {density: null}
    axes: {density: {n: 4}}
""")


def test_annulled_walk_with_an_enumerating_generator_is_covered():
    # l'override rimpiazza il generatore: la banda senza 'n' non c'e' piu'
    assert "n-ownership" not in codes("""stack:
  density: {base: 5}
streams:
  a:
    duration: 30
    stack: {density: null}
    axes: {density: {values: [10, 20, 30]}}
""")


def test_walk_for_a_dotted_axis_name():
    # 'grain.duration' e' un asse dotted: il confine del nome non va risolto
    doc = yamlpos.parse("""study_id: t
base:
  onset: 0
  sample: corpus.wav
axes:
  grain.duration: {baseline: 0.05, base: 0.01, range: 0.02}
streams:
  a:
    duration: 30
    stack:
      grain.duration: {base: 5}
""")
    m = model.build(doc)
    assert "n-ownership" not in [d.code for d in diagnostics.collect(doc, m)]


# --- il modello ------------------------------------------------------------


def test_model_tracks_declared_and_annulled_walks():
    doc = yamlpos.parse(DOC + """stack:
  density: {base: 5}
streams:
  a:
    stack: {density: null}
  b:
    stack: {density: {base: 9}}
  c:
    base: {volume: -6}
""")
    m = model.build(doc)
    assert m.streams["a"].stack_nulled == frozenset({"density"})
    assert m.walk_in_stream("density", "a") is False    # annullata
    assert m.walk_in_stream("density", "b") is True     # propria
    assert m.walk_in_stream("density", "c") is True     # ereditata
