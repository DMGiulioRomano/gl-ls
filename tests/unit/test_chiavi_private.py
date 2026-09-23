"""Chiavi private al root: ``_assi:`` e compagnia (gl-ls #48).

Convenzione degli studi: una chiave top-level che inizia con ``_`` e' un
magazzino — tiene i ``values`` in un posto solo per riusarli via alias YAML
(``&ax_duration`` / ``*ax_duration``) — e la pipeline la ignora. gl-ls la
segnalava come sconosciuta, e con lei i suoi figli, letti nel contesto
``root`` fino a suggerire ``speed`` -> ``seed``.

La regola: al root una chiave che inizia con ``_`` non si valida, ne' lei ne'
il suo sottoalbero. Solo al root — altrove il vocabolario resta chiuso.
"""
from glls import diagnostics, hover, model, schema, semtokens, yamlpos

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

MAGAZZINO = """_assi:
  duration: &ax_duration [0.002, 0.005]
  speed: &ax_speed [0.5, 1, 2]
  pitch:
    semitones: 3
"""


def diags_of(text):
    doc = yamlpos.parse(text)
    return diagnostics.collect(doc, model.build(doc))


def test_la_chiave_privata_e_i_figli_non_sono_segnalati():
    assert diags_of(MAGAZZINO + BASE) == []


def test_il_valore_riusato_via_alias_arriva_dove_e_letto():
    """Il magazzino non e' validato, ma cio' che l'alias porta in ``axes:``
    si': il fuori-bounds resta un errore, sul punto d'uso."""
    text = ("_assi:\n  dens: &ax_dens [10, 9000]\n"
            + BASE.replace("values: [10, 30]", "values: *ax_dens"))
    got = [d for d in diags_of(text) if d.code == "out-of-bounds"]
    assert len(got) == 1
    assert "9000" in got[0].message


def test_il_contesto_del_sottoalbero_privato_e_aperto():
    """Prima ``("_assi",)`` ricadeva sul contesto ``root``: i figli venivano
    confrontati col vocabolario del documento."""
    assert schema.context_for_path(("_assi",)) == "private"
    assert schema.context_for_path(("_assi", "pitch")) == "private"
    assert schema.context_for_path(("_assi", "pitch", "semitones")) == "private"
    assert "private" not in schema.CLOSED_CONTEXTS


def test_una_chiave_sconosciuta_senza_underscore_resta_segnalata():
    got = [d for d in diags_of("assi:\n  x: 1\n" + BASE) if d.code == "unknown-key"]
    assert any("'assi'" in d.message for d in got)


def test_il_prefisso_vale_solo_al_root():
    """Dentro un blocco a vocabolario chiuso ``_x`` resta una chiave ignota:
    la convenzione e' del documento, non di ogni mapping."""
    text = BASE.replace("  sample: corpus.wav\n",
                        "  sample: corpus.wav\n  _nota: 1\n")
    got = [d for d in diags_of(text) if d.code == "unknown-key"]
    assert any("'_nota'" in d.message for d in got)


def test_un_expr_nel_magazzino_non_e_valutato():
    """Nemmeno le espressioni: nel magazzino un nome e' in scope solo dove
    l'alias lo porta, e la pipeline il blocco non lo legge."""
    text = "_assi:\n  g: &g {expr: \"ignoto * 2\"}\n" + BASE
    assert diags_of(text) == []


def test_le_posizioni_puntate_del_magazzino_non_attivano_loop_unit():
    """Il rilievo ``loop-unit-implicito`` cerca le posizioni scritte per path
    puntato in tutto il documento: il magazzino non conta."""
    text = ("_assi:\n  p: &p {base.pointer.start: 0.3}\n"
            + BASE.replace("  sample: corpus.wav\n",
                           "  sample: corpus.wav\n  time_mode: normalized\n"))
    assert "loop-unit-implicito" not in {d.code for d in diags_of(text)}


def test_hover_sulla_chiave_privata_spiega_la_convenzione():
    text = MAGAZZINO + BASE
    doc = yamlpos.parse(text)
    h = hover.hover(doc, model.build(doc), 0, 2)
    assert h is not None
    assert "privata" in h.contents.value


def test_la_chiave_privata_non_prende_il_colore_del_linguaggio():
    """Un token ``keyword`` direbbe «sezione del linguaggio», e non lo e'."""
    text = MAGAZZINO + BASE
    doc = yamlpos.parse(text)
    data = semtokens.tokens(doc, model.build(doc))
    # il primo token del documento (riga 0) non deve cadere su '_assi'
    firsts = [(data[i], data[i + 1]) for i in range(0, len(data), 5)]
    assert firsts[0] != (0, 0)
