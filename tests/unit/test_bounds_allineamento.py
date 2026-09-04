"""Allineamento dei bounds e dei path a granulation-studies (gl-ls #43).

Tre fatti, uno per sezione:

1. il minimo di ``grain.duration`` e' **4 campioni**, non 1 — un floor di
   *studio* (``granstudies.bounds.MIN_GRAIN_SAMPLES``), non dell'engine, e
   vale sempre, anche con i valori scritti in secondi;
2. ``num_voices`` / ``scatter`` / ``pointer.deviation`` sono i nomi del
   *registry* engine, non le chiavi YAML: scritti come path finiscono in un
   posto che l'engine non legge, e nessuno dei due runtime protesta;
3. i path che granstudies ha appena imparato dagli schema
   (``pointer.loop_*``, ``grain.reverse``, ``grain.read_direction``,
   ``grain.envelope``) sono path noti anche qui.
"""
from glls import diagnostics, engine_info as EI, hover, model, yamlpos

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


def diags_of(text):
    doc = yamlpos.parse(text)
    m = model.build(doc)
    return diagnostics.collect(doc, m)


def codes(text):
    return {d.code for d in diags_of(text)}


def _grain(body):
    return BASE.replace("base:\n", f"base:\n  grain:\n{body}")


def _axis(body):
    return BASE.replace(
        "  density:\n    baseline: 20\n    values: [10, 30]\n", body)


# --- 1. il floor di grain.duration: 4 campioni ------------------------------


def test_il_floor_e_quattro_campioni():
    assert EI.MIN_GRAIN_SAMPLES == 4
    assert EI.PARAMS["grain.duration"].min == 4 / EI.OUTPUT_SR


def test_grain_duration_sotto_quattro_campioni_in_secondi_e_fuori_bounds():
    # 0.00005 s = 2.4 campioni a 48 kHz: renderizzabile dall'engine (che
    # scende a 1), rifiutato da granstudies al parse.
    assert "out-of-bounds" in codes(_grain("    duration: 0.00005\n"))


def test_grain_duration_a_quattro_campioni_in_secondi_passa():
    # 0.0001 s = 4.8 campioni: sopra il floor
    assert "out-of-bounds" not in codes(_grain("    duration: 0.0001\n"))


def test_un_millisecondo_resta_legale():
    # il vecchio fallback statico dell'engine (1 ms) sta ampiamente sopra
    assert "out-of-bounds" not in codes(_grain("    duration: 0.001\n"))


def test_il_messaggio_dice_che_il_floor_e_un_vincolo_di_studio():
    d = next(d for d in diags_of(_grain("    duration: 0.00005\n"))
             if d.code == "out-of-bounds")
    assert "4 campioni" in d.message
    assert "studio" in d.message


def test_il_floor_vale_anche_in_campioni():
    assert "out-of-bounds" in codes(
        _grain("    duration: 3\n    duration_unit: samples\n"))
    assert "out-of-bounds" not in codes(
        _grain("    duration: 4\n    duration_unit: samples\n"))


def test_il_floor_vale_anche_in_millisecondi():
    # 0.05 ms = 2.4 campioni; 0.1 ms = 4.8 campioni
    assert "out-of-bounds" in codes(
        _grain("    duration: 0.05\n    duration_unit: milliseconds\n"))
    assert "out-of-bounds" not in codes(
        _grain("    duration: 0.1\n    duration_unit: milliseconds\n"))


def test_il_floor_vale_sui_valori_di_un_asse():
    text = _axis("  grain.duration:\n    baseline: 0.001\n"
                 "    values: [0.00002, 0.001]\n")
    assert "out-of-bounds" in codes(text)


def test_asse_in_campioni_dal_quarto_pulito():
    # la scala '1-50smp' parte da 4 proprio per questo floor
    text = _grain("    duration: 4\n    duration_unit: samples\n").replace(
        "  density:\n    baseline: 20\n    values: [10, 30]\n",
        "  grain.duration:\n    baseline: 4\n    values: [4, 50]\n")
    assert "out-of-bounds" not in codes(text)


# --- 2. i nomi del registry non sono chiavi YAML ----------------------------


def test_la_mappa_delle_grafie_di_registry():
    assert EI.REGISTRY_SPELLINGS == {
        "num_voices": "voices.num_voices",
        "scatter": "voices.scatter",
        "pointer.deviation": "pointer.offset_range",
    }


def test_path_esplicito_col_nome_di_registry():
    text = _axis("  voci:\n    path: num_voices\n    baseline: 1\n"
                 "    values: [1, 4]\n")
    d = next(d for d in diags_of(text) if d.code == "registry-spelling")
    assert "voices.num_voices" in d.message
    assert d.data["fix"] == {"kind": "rename-value", "new": "voices.num_voices"}


def test_chiave_dasse_col_nome_di_registry():
    # senza 'path:' la chiave stessa e' il path: stessa diagnostica, fix di
    # rinomina sulla chiave
    text = _axis("  scatter:\n    baseline: 0\n    values: [0, 1]\n")
    d = next(d for d in diags_of(text) if d.code == "registry-spelling")
    assert "voices.scatter" in d.message
    assert d.data["fix"] == {"kind": "rename", "new": "voices.scatter"}


def test_pointer_deviation_e_il_nome_di_registry_di_offset_range():
    text = _axis("  dev:\n    path: pointer.deviation\n    baseline: 0\n"
                 "    values: [0, 0.5]\n")
    d = next(d for d in diags_of(text) if d.code == "registry-spelling")
    assert "pointer.offset_range" in d.message


def test_le_chiavi_yaml_vere_sono_pulite():
    for path in EI.REGISTRY_SPELLINGS.values():
        text = _axis(f"  a:\n    path: {path}\n    baseline: 0\n"
                     "    values: [0, 1]\n")
        cs = codes(text)
        assert "registry-spelling" not in cs, path
        assert "unknown-path" not in cs, path


def test_una_grafia_di_registry_non_e_un_path_noto():
    # non entra da nessuna porta: ne' PARAMS ne' known_paths
    for name in EI.REGISTRY_SPELLINGS:
        assert name not in EI.PARAMS
        assert name not in EI.known_paths()


# --- 3. i path che granstudies ha imparato dagli schema ---------------------

_NUOVI = ("grain.reverse", "grain.read_direction", "grain.envelope")


def test_i_path_nuovi_sono_noti():
    for p in _NUOVI + ("pointer.loop_start", "pointer.loop_end",
                       "pointer.loop_dur"):
        assert p in EI.known_paths(), p
        assert p in EI.AXIS_PATHS, p


def test_un_asse_sui_path_nuovi_non_e_sconosciuto():
    for p in _NUOVI:
        text = _axis(f"  a:\n    path: {p}\n    baseline: 1\n    values: [1]\n")
        assert "unknown-path" not in codes(text), p


def test_split_axis_key_vede_i_path_nuovi():
    assert EI.split_axis_key("grain.read_direction.values") == (
        "grain.read_direction", ("values",), None)


def test_read_direction_senza_default_vuole_il_baseline():
    # nello schema engine 'read_direction' ha default None (chiave non
    # dichiarata): granstudies pretende il baseline esplicito
    assert EI.needs_baseline("grain.read_direction")
    text = _axis("  a:\n    path: grain.read_direction\n    values: [-1, 1]\n")
    assert "baseline-required" in codes(text)


def test_reverse_ed_envelope_hanno_un_default_engine():
    assert not EI.needs_baseline("grain.reverse")
    assert not EI.needs_baseline("grain.envelope")


def test_grain_envelope_non_ha_bounds_numerici():
    assert EI.bounds_for("grain.envelope") == (None, None)
    assert "nessun bound numerico" in EI.bounds_phrase(
        EI.PARAMS["grain.envelope"])


def test_hover_su_un_path_senza_bounds_numerici_non_esplode():
    text = _axis("  a:\n    path: grain.envelope\n    values: [1]\n")
    doc = yamlpos.parse(text)
    m = model.build(doc)
    line = next(i for i, l in enumerate(text.splitlines())
                if "path: grain.envelope" in l)
    col = text.splitlines()[line].index("grain.envelope")
    h = hover.hover(doc, m, line, col)
    assert h is not None
    assert "grain.envelope" in h.contents.value


def test_read_direction_ha_i_bounds_col_segno():
    assert EI.bounds_for("grain.read_direction") == (-1, 1)
