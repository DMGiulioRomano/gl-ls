"""Allineamento dei bounds e dei path a granulation-studies (gl-ls #43).

Tre fatti, uno per sezione:

1. il minimo di ``grain.duration`` e' **1 campione** (``1/output_sr``), quello
   dell'engine: il floor di studio di 4 campioni non c'e' piu' (gl-ls #47), e
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


# --- 1. il floor di grain.duration: 1 campione, quello dell'engine ---------
#
# Fino a gl-ls #47 il minimo era 4 campioni, un floor di *studio*
# (``granstudies.bounds.MIN_GRAIN_SAMPLES``). granulation-studies l'ha tolto
# (mare-nostrum da95f26 / ec0a8ea): ``bounds_for("grain.duration")`` ora
# restituisce il minimo dell'engine, ``1/output_sr``. Un floor piu' alto qui
# segnerebbe in rosso valori fra 1 e 4 campioni che il runtime accetta.


def test_il_floor_e_un_campione():
    assert EI.PARAMS["grain.duration"].min == 1 / EI.OUTPUT_SR
    assert EI.GRAIN_DURATION_MIN == 1 / EI.OUTPUT_SR


def test_nessun_floor_di_studio_residuo():
    assert not hasattr(EI, "MIN_GRAIN_SAMPLES")
    assert not hasattr(EI, "STUDIO_FLOOR")
    assert "studio" not in EI.PARAMS["grain.duration"].doc


def test_fra_uno_e_quattro_campioni_in_secondi_passa():
    # 0.00005 s = 2.4 campioni a 48 kHz: era il falso positivo di #47
    assert "out-of-bounds" not in codes(_grain("    duration: 0.00005\n"))


def test_sotto_un_campione_in_secondi_e_fuori_bounds():
    # 0.00001 s = 0.48 campioni
    assert "out-of-bounds" in codes(_grain("    duration: 0.00001\n"))


def test_un_millisecondo_resta_legale():
    assert "out-of-bounds" not in codes(_grain("    duration: 0.001\n"))


def test_il_messaggio_non_parla_piu_di_vincolo_di_studio():
    d = next(d for d in diags_of(_grain("    duration: 0.00001\n"))
             if d.code == "out-of-bounds")
    assert "studio" not in d.message
    assert "4 campioni" not in d.message


def test_il_floor_in_campioni_e_uno():
    for n in (1, 2, 3, 4):
        assert "out-of-bounds" not in codes(
            _grain(f"    duration: {n}\n    duration_unit: samples\n")), n
    assert "out-of-bounds" in codes(
        _grain("    duration: 0.5\n    duration_unit: samples\n"))


def test_il_floor_in_millisecondi():
    # 0.05 ms = 2.4 campioni (passa); 0.01 ms = 0.48 campioni (no)
    assert "out-of-bounds" not in codes(
        _grain("    duration: 0.05\n    duration_unit: milliseconds\n"))
    assert "out-of-bounds" in codes(
        _grain("    duration: 0.01\n    duration_unit: milliseconds\n"))


def test_il_floor_vale_sui_valori_di_un_asse():
    text = _axis("  grain.duration:\n    baseline: 0.001\n"
                 "    values: [0.00001, 0.001]\n")
    assert "out-of-bounds" in codes(text)
    text = _axis("  grain.duration:\n    baseline: 0.001\n"
                 "    values: [0.00005, 0.001]\n")
    assert "out-of-bounds" not in codes(text)


def test_asse_in_campioni_dal_primo_pulito():
    # la scala in campioni puo' partire da 1, il campione dell'engine
    text = _grain("    duration: 1\n    duration_unit: samples\n").replace(
        "  density:\n    baseline: 20\n    values: [10, 30]\n",
        "  grain.duration:\n    baseline: 1\n    values: [1, 50]\n")
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


# --- 4. la banda ha bounds suoi, non quelli del valore ----------------------
#
# Quattro chiavi ``_range`` (l'ampiezza della randomizzazione per grano) non
# si confrontano con ``min_val``/``max_val`` del parametro ma con
# ``min_range``/``max_range``, che nell'engine sono numeri diversi e molto
# piu' stretti. Lo snapshot li aveva presi dal valore — o inventati — e nella
# direzione peggiore: piu' larghi del vero, quindi l'editor taceva su cio' che
# il parser dell'engine rifiuta con ``ParameterBoundError``.


def test_i_bounds_della_banda_sono_quelli_della_banda():
    assert EI.bounds_for("grain.duration_range") == (0, 1)
    assert EI.bounds_for("volume_range") == (0, 24)
    assert EI.bounds_for("pan_range") == (0, 360)
    # 'pointer.offset_range' e' la banda di 'pointer_deviation', il cui valore
    # non ha una chiave YAML propria (yaml_path='_dummy_fixed_zero_'): il
    # dominio dichiarabile e' [0, 1], non il [-1, 1] del valore.
    assert EI.bounds_for("pointer.offset_range") == (0, 1)


def test_una_banda_fuori_bounds_non_passa_muta():
    fuori = {
        "  volume_range: 100\n": "volume_range",
        "  pan_range: 1000\n": "pan_range",
    }
    for riga, path in fuori.items():
        text = BASE.replace("  sample: corpus.wav\n",
                            "  sample: corpus.wav\n" + riga)
        assert "out-of-bounds" in codes(text), path


def test_una_banda_di_durata_fuori_bounds_non_passa_muta():
    # 5 s di banda su una durata di grano: l'engine si ferma a 1 s
    assert "out-of-bounds" in codes(_grain("    duration_range: 5\n"))


def test_una_banda_di_deviazione_negativa_non_passa_muta():
    text = BASE.replace("  sample: corpus.wav\n",
                        "  sample: corpus.wav\n"
                        "  pointer:\n    offset_range: -0.5\n")
    assert "out-of-bounds" in codes(text)
