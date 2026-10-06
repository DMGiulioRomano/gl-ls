"""``sweep.orderings`` sotto ``mode: discrete`` (gl-ls #48).

Regola di ``study_spec``: se ``orders`` e' assente e ``orderings`` e'
popolato, ``orders`` diventa ``[]`` — assetto chirurgico: chi ha scelto le
combinazioni non se ne vede aggiungere altre a sua insaputa.

In ``mode: envelope`` e' corretto, gli orderings sono traversate temporali. In
``mode: discrete`` (il default) gli orderings **non hanno alcun effetto**:
``generate_discrete_variants`` legge solo ``orders``. La coppia azzera la
generazione, e lo sweep non produce niente in silenzio.
"""
from glls import actions, diagnostics, model, schema, yamlpos
from lsprotocol import types

HEAD = """study_id: t
base:
  onset: 0
  duration: 6
  sample: corpus.wav
axes:
  density:
    baseline: 20
    values: [10, 30]
  volume:
    baseline: 0
    values: [-6, 0]
"""


def diags_of(text):
    doc = yamlpos.parse(text)
    return diagnostics.collect(doc, model.build(doc))


def only(text, code="orderings-discrete"):
    return [d for d in diags_of(text) if d.code == code]


def test_discrete_esplicito_con_orderings_e_senza_orders_non_genera_niente():
    text = HEAD + ("sweep:\n  mode: discrete\n  orderings:\n"
                   "    - [density, volume]\n")
    got = only(text)
    assert len(got) == 1
    d = got[0]
    assert d.severity == types.DiagnosticSeverity.Warning
    assert "nessuna variante" in d.message
    line = text.splitlines().index("  orderings:")
    assert d.range.start.line == line


def test_il_default_e_discrete():
    """``mode`` assente vale ``discrete``: la trappola e' proprio li'."""
    text = HEAD + "sweep:\n  orderings:\n    - [density, volume]\n"
    got = only(text)
    assert len(got) == 1
    assert "default" in got[0].message


def test_in_envelope_e_both_gli_orderings_hanno_effetto():
    for mode in ("envelope", "both"):
        text = HEAD + (f"sweep:\n  mode: {mode}\n  orderings:\n"
                       "    - [density, volume]\n")
        assert only(text) == [], mode


def test_orderings_vuoti_non_contano():
    """``orderings: []`` e' la forma con cui uno stream spegne le traversate:
    non e' popolato, quindi ``orders`` resta al default."""
    text = HEAD + "sweep:\n  orderings: []\n"
    assert only(text) == []


def test_con_orders_esplicito_gli_orderings_restano_senza_effetto():
    """Gli ``orders`` generano, gli orderings no: il messaggio e' un altro,
    perche' lo sweep qualcosa produce."""
    text = HEAD + ("sweep:\n  orders: [1]\n  orderings:\n"
                   "    - [density, volume]\n")
    got = only(text)
    assert len(got) == 1
    assert "nessuna variante" not in got[0].message
    assert "orders" in got[0].message


def test_i_due_quick_fix():
    """Togliere gli orderings (``orders`` torna a ``[1..n]``) o passare a
    ``mode: envelope``: quale dei due lo sa solo chi li ha scritti."""
    uri = "file:///s.yml"
    text = HEAD + ("sweep:\n  mode: discrete\n  plateau: 5\n  orderings:\n"
                   "    - [density, volume]\n")
    doc = yamlpos.parse(text)
    d = only(text)[0]
    titles = {a.title: a for a in actions.quickfixes(doc, uri, [d])}
    assert "Rimuovi 'orderings'" in titles
    mode = [a for t, a in titles.items() if "envelope" in t]
    assert len(mode) == 1
    edits = mode[0].edit.changes[uri]
    assert [e.new_text for e in edits] == ["envelope"]
    assert edits[0].range.start.line == text.splitlines().index("  mode: discrete")


def test_il_quick_fix_del_mode_lo_aggiunge_se_manca():
    uri = "file:///s.yml"
    text = HEAD + "sweep:\n  plateau: 5\n  orderings:\n    - [density, volume]\n"
    doc = yamlpos.parse(text)
    d = only(text)[0]
    mode = [a for a in actions.quickfixes(doc, uri, [d]) if "envelope" in a.title]
    assert len(mode) == 1
    edit = mode[0].edit.changes[uri][0]
    assert edit.new_text == "  mode: envelope\n"


def test_override_di_stream_che_passa_a_discrete_eredita_gli_orderings():
    """Il runtime valida il documento *merged* per stream: il ``mode`` dello
    override si somma agli ``orderings`` del documento."""
    text = HEAD + ("sweep:\n  mode: envelope\n  orderings:\n"
                   "    - [density, volume]\n"
                   "streams:\n  a:\n    sweep:\n      mode: discrete\n")
    got = only(text)
    assert len(got) == 1
    line = text.splitlines().index("      mode: discrete")
    assert got[0].range.start.line == line


def test_un_override_che_non_tocca_mode_ne_orderings_non_ripete_il_rilievo():
    text = HEAD + ("sweep:\n  orderings:\n    - [density, volume]\n"
                   "streams:\n  a:\n    sweep:\n      plateau: 3\n")
    assert len(only(text)) == 1


def test_la_doc_di_mode_e_orderings_avverte_della_coppia():
    assert "discrete" in schema.key_in("sweep", "orderings").doc
    assert "orderings" in schema.key_in("sweep", "mode").doc
