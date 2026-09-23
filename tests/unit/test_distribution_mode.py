"""``distribution_mode`` e ``range_anchor``: la banda dei ``_range`` (gl-ls #48).

Due chiavi vere dello stream engine (``StreamConfig`` di PGE v9, documentate
in ``docs/reference/yaml.md`` sotto «La banda dei ``_range``»), che il
registro di ``engine_stream`` non conosceva: ``distribution_mode`` diventava
un ``unknown-key`` con il suggerimento di rinominarla ``distribution`` — che e'
un'altra cosa (il modello di Truax, 0..1) — e ``range_anchor`` finiva nello
stesso buco. Il vocabolario e' chiuso in entrambe: ``uniform`` | ``gaussian``
(``DistributionFactory``), ``center`` | ``min`` (``RANGE_ANCHORS``).
"""
from glls import completion, diagnostics, hover, model, schema, yamlpos

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


def diags_of(extra):
    doc = yamlpos.parse(BASE % extra)
    return diagnostics.collect(doc, model.build(doc))


def test_le_due_chiavi_sono_nel_registro_engine():
    assert schema.key_in("engine_stream", "distribution_mode") is not None
    assert schema.key_in("engine_stream", "range_anchor") is not None


def test_i_valori_ammessi_passano():
    for mode in ("uniform", "gaussian"):
        for anchor in ("center", "min"):
            extra = f"  distribution_mode: {mode}\n  range_anchor: {anchor}\n"
            assert diags_of(extra) == [], (mode, anchor)


def test_valgono_anche_negli_override_di_stream():
    text = (BASE % "") + ("streams:\n  a:\n    base:\n"
                          "      distribution_mode: gaussian\n"
                          "      range_anchor: min\n")
    doc = yamlpos.parse(text)
    assert diagnostics.collect(doc, model.build(doc)) == []


def test_distribution_mode_fuori_vocabolario_e_errore_con_suggerimento():
    got = [d for d in diags_of("  distribution_mode: gausian\n")
           if d.code == "bad-enum"]
    assert len(got) == 1
    assert "uniform | gaussian" in got[0].message
    assert got[0].data["fix"] == {"kind": "rename-value", "new": "gaussian"}


def test_range_anchor_fuori_vocabolario_e_errore():
    got = [d for d in diags_of("  range_anchor: centre\n") if d.code == "bad-enum"]
    assert len(got) == 1
    assert "center | min" in got[0].message


def test_non_e_distribution():
    """Il vecchio suggerimento portava a ``distribution``: la doc delle due
    chiavi deve dire che sono cose diverse, da entrambi i lati."""
    assert "distribution_mode" in schema.key_in("engine_stream", "distribution").doc
    assert "distribution`" in schema.key_in("engine_stream", "distribution_mode").doc


def test_completion_del_valore():
    text = BASE % "  distribution_mode: "
    doc = yamlpos.parse(text)
    line = text.splitlines().index("  distribution_mode: ")
    labels = {i.label for i in completion.complete(doc, model.build(doc), line, 21)}
    assert labels >= {"uniform", "gaussian"}


def test_hover():
    text = BASE % "  range_anchor: min\n"
    doc = yamlpos.parse(text)
    line = text.splitlines().index("  range_anchor: min")
    h = hover.hover(doc, model.build(doc), line, 4)
    assert h is not None
    assert "base + range" in h.contents.value
