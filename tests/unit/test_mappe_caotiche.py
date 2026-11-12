"""Le mappe caotiche di PGE (#307) dentro un blocco engine (gl-ls #63, #64).

``maps:``, le espressioni del motore, ``grain.iot`` e ``pointer.position``:
YAML che il motore rende non deve avere falsi ``unknown-key`` ne' falsi
fuori-bounds, e cio' che il motore rifiuta al caricamento va detto qui.
"""
import pytest

from glls import diagnostics, engine_expr as EX, engine_info as EI
from glls import hover, model, schema, semtokens, yamlpos
from glls.completion import complete

HEAD = "study_id: t\nbase:\n  onset: 0\n  duration: 6\n  sample: corpus.wav\n"
TAIL = "axes:\n  volume:\n    baseline: -6\n    values: [-12, -6]\n"


def diags(body, tail=TAIL):
    doc = yamlpos.parse(HEAD + body + tail)
    return diagnostics.collect(doc, model.build(doc))


def codes(body, tail=TAIL):
    return [d.code for d in diags(body, tail)]


# ---------------------------------------------------------------------------
# YAML valido del motore: zero diagnostiche (le tabelle di #63 e #64)

VALIDI = {
    "308": "  maps:\n    m1: {type: logistic, r: 3.5}\n"
           "  grain:\n    duration: (0.02 + 0.08*m1)\n",
    "310": "  maps:\n"
           "    m1: {type: logistic, r: [[0, 3.0], [6, 4.0]], clock: [[0, 2], [6, 20]]}\n"
           "    m2: {type: tent, r: 3.2, iterate: 8, x0: 0.4}\n"
           "  grain:\n    duration: (0.02 + 0.08*m2)\n",
    "311": "  maps:\n    m1: {type: logistic, r: 3.5}\n"
           "  grain:\n    iot: (0.020 + 0.180*m1)\n",
    "311-ms": "  grain:\n    iot: 500\n    duration: 50\n"
              "    duration_unit: milliseconds\n",
    "312": "  pointer:\n    position: 0.5\n",
    "312-loop": "  maps:\n    m1: {type: logistic, r: 3.5}\n"
                "  pointer:\n    position: (m1)\n    loop_start: 0.2\n"
                "    loop_dur: 0.5\n",
    "312-wrap": "  pointer:\n    position: 1.25\n",
    "312-env": "  pointer:\n    position: [[0, 0], [6, 3]]\n",
    "313-custom": "  maps:\n    m2:\n      type: custom\n      x: sin(r*x)*cos(x)\n"
                  "      y: 0.3*x\n      y0: 0.1\n      r: 3\n"
                  "  pitch:\n    semitones: (12*m2)\n",
    "313-henon": "  maps:\n    m1: {type: henon, r: 1.4}\n"
                 "  volume: (-18 + 4*m1)\n  pan: (100*m1.y)\n"
                 "  density: (10 + 40*m1)\n"
                 "  grain:\n    read_direction: (sign(m1 - 0.6))\n",
    "313-custom-no-r": "  maps:\n    m1: {type: custom, x: 1 - 1.4*x*x}\n"
                       "  distribution: (m1)\n",
    "309": "  volume: (max(-12, -6))\n  grain:\n    duration: (pow(10, -2))\n",
    "t": "  pan: (sin(t) * 90)\n",
    "costante-ovunque": "  pointer:\n    speed_ratio: (10/2)\n",
}


@pytest.mark.parametrize("name", sorted(VALIDI))
def test_yaml_valido_del_motore_non_ha_diagnostiche(name):
    assert diags(VALIDI[name]) == []


def test_tutti_i_tipi_del_catalogo_sono_validi():
    for tipo in EI.MAP_TYPES:
        r = EI.MAP_KINDS[tipo].r_range[1]
        assert codes(f"  maps:\n    m1: {{type: {tipo}, r: {r}}}\n") == [], tipo


# ---------------------------------------------------------------------------
# Vocabolari

def test_maps_e_le_sue_chiavi_sono_nel_registry():
    assert schema.key_in("engine_stream", "maps") is not None
    assert [k.name for k in schema.keys_for("map")] == list(EI.MAP_KEYS)
    assert schema.key_in("grain", "iot") is not None
    assert schema.key_in("pointer", "position") is not None


def test_contesti_di_maps():
    ctx = schema.context_for_path
    assert ctx(("base", "maps")) == "maps"
    assert ctx(("base", "maps", "m1")) == "map"
    assert ctx(("base", "maps", "m1", "r")) == "engine_env"
    assert ctx(("streams", "s", "base", "maps", "m1")) == "map"
    assert "map" in schema.CLOSED_CONTEXTS and "maps" not in schema.CLOSED_CONTEXTS


def test_una_chiave_sconosciuta_in_una_mappa_e_unknown_key():
    d = diags("  maps:\n    m1: {type: logistic, r: 3.5, clok: 3}\n")
    assert [x.code for x in d] == ["unknown-key"]
    assert "clock" in d[0].message


def test_completion_dei_tipi():
    text = HEAD + "  maps:\n    m1:\n      type: \n"
    doc = yamlpos.parse(text)
    items = complete(doc, model.build(doc), text.count("\n") - 1, 12)
    assert {i.label for i in items} >= set(EI.MAP_TYPE_VALUES)


def test_path_engine_nuovi():
    assert EI.bounds_for("grain.iot") == (1 / EI.OUTPUT_SR, 100)
    assert EI.bounds_for("pointer.position") == (0, 1)
    assert EI.needs_baseline("grain.iot") and EI.needs_baseline("pointer.position")


# ---------------------------------------------------------------------------
# Le regole di ``maps:`` (MapConfigError)

ERRORI_MAPPA = {
    "tipo": ("  maps:\n    m1: {type: lorenz, r: 3.5}\n", "bad-enum"),
    "manca-tipo": ("  maps:\n    m1: {r: 3.5}\n", "map-config"),
    "x-con-catalogo": ("  maps:\n    m1: {type: logistic, r: 3.5, x: r*x}\n",
                       "map-config"),
    "y0-una-variabile": ("  maps:\n    m1: {type: logistic, r: 3.5, y0: 0.1}\n",
                         "map-config"),
    "custom-senza-x": ("  maps:\n    m1: {type: custom, r: 3}\n", "map-config"),
    "custom-legge-y": ("  maps:\n    m1: {type: custom, x: x + y, r: 1}\n",
                       "map-config"),
    "custom-equazione": ("  maps:\n    m1: {type: custom, x: 'r*(x', r: 1}\n",
                         "engine-expr"),
    "manca-r": ("  maps:\n    m1: {type: logistic}\n", "map-config"),
    "r-stringa": ("  maps:\n    m1: {type: logistic, r: tanto}\n", "map-config"),
    "clock-e-iterate": ("  maps:\n    m1: {type: logistic, r: 3.5, clock: 2, "
                        "iterate: 4}\n", "map-config"),
    "iterate-tetto": ("  maps:\n    m1: {type: logistic, r: 3.5, iterate: 41}\n",
                      "map-config"),
    "iterate-zero": ("  maps:\n    m1: {type: logistic, r: 3.5, iterate: 0}\n",
                     "map-config"),
    "iterate-transient": ("  maps:\n    m1: {type: logistic, r: 3.5, iterate: 4, "
                          "transient: 10}\n", "map-config"),
    "transient-tetto": ("  maps:\n    m1: {type: logistic, r: 3.5, "
                        "transient: 100001}\n", "map-config"),
    "clock-zero": ("  maps:\n    m1: {type: logistic, r: 3.5, clock: 0}\n",
                   "map-config"),
    "clock-oltre-un-campione": ("  maps:\n    m1: {type: logistic, r: 3.5, "
                                "clock: 48001}\n", "map-config"),
    "clock-envelope": ("  maps:\n    m1: {type: logistic, r: 3.5, "
                       "clock: [[0, 2], [6, 0]]}\n", "map-config"),
    "nome-riservato": ("  maps:\n    sin: {type: logistic, r: 3.5}\n", "map-name"),
    "nome-cifra": ("  maps:\n    1m: {type: logistic, r: 3.5}\n", "map-name"),
    "vuoto": ("  maps: {}\n", "map-config"),
}


@pytest.mark.parametrize("name", sorted(ERRORI_MAPPA))
def test_cio_che_il_motore_rifiuta_di_una_mappa(name):
    body, code = ERRORI_MAPPA[name]
    assert code in codes(body)


def test_i_tetti_sono_inclusi():
    assert codes("  maps:\n    m1: {type: logistic, r: 3.5, iterate: 40}\n") == []
    assert codes("  maps:\n    m1: {type: logistic, r: 3.5, transient: 100000}\n") == []
    assert codes("  maps:\n    m1: {type: logistic, r: 3.5, clock: 48000}\n") == []


def test_una_mappa_dello_stream_eredita_dal_base():
    """Il deep-merge: la entry ritocca ``r`` di una mappa dichiarata in
    ``base:`` senza ripeterne il tipo."""
    body = "  maps:\n    m1: {type: logistic, r: 3.5}\n"
    tail = TAIL + "streams:\n  a:\n    base:\n      maps:\n        m1: {r: 3.9}\n"
    assert codes(body, tail) == []


# ---------------------------------------------------------------------------
# Le espressioni del motore

def test_un_nome_che_lo_stream_non_dichiara():
    d = diags("  maps:\n    m1: {type: logistic, r: 3.5}\n"
              "  grain:\n    duration: (0.02 + 0.08*m9)\n")
    assert [x.code for x in d] == ["engine-expr"]
    assert "m9" in d[0].message and "m1" in d[0].message


def test_m1_y_solo_su_una_mappa_a_due_variabili():
    body = "  maps:\n    m1: {type: logistic, r: 3.5}\n  pan: (100*m1.y)\n"
    assert codes(body) == ["engine-expr"]


def test_la_sintassi_e_quella_del_motore():
    for testo in ("(0.02 +)", "(clip(m1, 0))", "(m1 % 2)", "(m1 ^ 2)",
                  "(boh(m1))"):
        body = ("  maps:\n    m1: {type: logistic, r: 3.5}\n"
                f"  volume: '{testo}'\n")
        assert codes(body) == ["engine-expr"], testo


def test_l_annidamento_ha_un_tetto():
    profondo = "(" * 51 + "m1" + ")" * 51
    assert not EX.compile_expression(profondo, ("m1",)).ok
    assert EX.compile_expression("(" * 50 + "m1" + ")" * 50, ("m1",)).ok


def test_senza_parentesi_esterne_e_un_errore_che_le_propone():
    d = diags("  maps:\n    m1: {type: logistic, r: 3.5}\n  volume: -30 + 20*m1\n")
    assert [x.code for x in d] == ["engine-expr"]
    assert d[0].data == {"fix": {"kind": "rename-value", "new": "(-30 + 20*m1)"}}


def test_una_parola_non_e_un_espressione():
    """``density: not_a_number`` resta l'errore di una stringa nel motore:
    qui non si inventa un'espressione."""
    assert "engine-expr" not in codes("  density: forte\n")


@pytest.mark.parametrize("campo", sorted(EX.EXPRESSION_REFUSALS))
def test_dove_il_motore_la_rifiuta(campo):
    blocco, _, chiave = campo.partition(".")
    body = (f"  maps:\n    m1: {{type: logistic, r: 3.5}}\n"
            f"  {blocco}:\n    {chiave}: (m1)\n")
    d = [x for x in diags(body) if x.code == "engine-expr-refused"]
    assert len(d) == 1
    assert EX.EXPRESSION_REFUSALS[campo][:40] in d[0].message


def test_una_banda_la_rifiuta_col_suggerimento_generico():
    body = "  maps:\n    m1: {type: logistic, r: 3.5}\n  volume_range: (m1*6)\n"
    d = [x for x in diags(body) if x.code == "engine-expr-refused"]
    assert d and "valore base" in d[0].message


def test_una_costante_del_caricamento_vale_ovunque():
    assert codes("  pointer:\n    start: (10/2)\n") == []
    assert codes("  volume_range: (max(1, 3))\n") == []


def test_fuori_dai_campi_una_funzione_che_il_caricamento_non_sa():
    """``(clip(...))`` fuori da EXPRESSION_FIELDS: il caricamento non la sa
    valutare, resta una stringa, e il parser la rifiuta."""
    assert "engine-expr-refused" in codes("  pointer:\n    start: (clip(5, 0, 1))\n")


def test_un_nodo_expr_dello_studio_non_e_toccato():
    assert "engine-expr" not in codes("  volume: {expr: '-6'}\n")


# ---------------------------------------------------------------------------
# grain.iot

def test_iot_segue_duration_unit():
    assert codes("  grain:\n    iot: 500\n    duration: 50\n"
                 "    duration_unit: milliseconds\n") == []
    assert "out-of-bounds" in codes("  grain:\n    iot: 200000\n    duration: 50\n"
                                    "    duration_unit: milliseconds\n")


def test_iot_fuori_bounds_in_secondi():
    assert "out-of-bounds" in codes("  grain:\n    iot: 150\n")


@pytest.mark.parametrize("altro", EI.IOT_EXCLUSIVE_KEYS)
def test_iot_e_un_errore_non_una_priorita(altro):
    d = diags(f"  {altro}: 1\n  grain:\n    iot: 0.1\n")
    assert [x.code for x in d] == ["iot-exclusive"]
    assert d[0].severity == 1  # Error


def test_iot_vuota_e_gia_un_modo():
    assert "iot-exclusive" in codes("  density: 20\n  grain:\n    iot:\n")


def test_iot_attraverso_il_merge():
    tail = TAIL + "streams:\n  a:\n    base:\n      grain:\n        iot: 0.1\n"
    d = [x for x in diags("  density: 20\n", tail) if x.code == "iot-exclusive"]
    assert len(d) == 1
    assert d[0].range.start.line > HEAD.count("\n")


def test_un_asse_sull_altro_modo():
    tail = "axes:\n  density:\n    baseline: 20\n    values: [10, 30]\n"
    assert "iot-exclusive" in codes("  grain:\n    iot: 0.1\n", tail)
    tail = "axes:\n  grain.iot:\n    baseline: 0.1\n    values: [0.05, 0.2]\n"
    assert "iot-exclusive" in codes("  density: 20\n", tail)


# ---------------------------------------------------------------------------
# pointer.position

def test_position_rientra_a_capo():
    assert codes("  pointer:\n    position: -0.25\n") == []
    assert codes("  pointer:\n    position: {type: linear, points: [[0, 0], [6, 7]]}\n") == []


@pytest.mark.parametrize("v", [".nan", ".inf", "-.inf"])
def test_position_non_finita_e_un_errore(v):
    assert codes(f"  pointer:\n    position: {v}\n") == ["out-of-bounds"]


@pytest.mark.parametrize("altro", EI.POSITION_EXCLUSIVE_KEYS)
def test_position_esclusiva(altro):
    d = diags(f"  pointer:\n    position: 0.5\n    {altro}: 0\n")
    assert [x.code for x in d] == ["position-exclusive"]


def test_un_asse_su_position_non_e_fuori_bounds():
    tail = ("axes:\n  pointer.position:\n    baseline: 0.5\n"
            "    values: [0.25, 1.5]\n")
    assert codes("", tail) == []


def test_un_asse_su_start_accanto_a_position():
    tail = "axes:\n  pointer.start:\n    baseline: 0\n    values: [0, 1]\n"
    assert "position-exclusive" in codes("  pointer:\n    position: 0.5\n", tail)


def test_position_non_e_scalata_da_loop_unit():
    assert "pointer.position" not in EI.POSITION_PATHS


# ---------------------------------------------------------------------------
# Hover e semantic token

def _hover_at(text, needle, word, where_offset=0):
    doc = yamlpos.parse(text)
    lines = text.splitlines()
    row = next(i for i, l in enumerate(lines) if needle in l)
    col = lines[row].index(word) + where_offset
    return hover.hover(doc, model.build(doc), row, col)


def test_hover_di_un_espressione_dice_le_mappe_e_il_loro_intervallo():
    text = (HEAD + "  maps:\n    m1: {type: henon, r: 1.4}\n"
            "  pan: (100*m1.y + 0*m1)\n" + TAIL)
    h = _hover_at(text, "pan: (", "(", 2)
    assert h is not None
    v = h.contents.value
    assert "a ogni grano" in v and "-0.39" in v and "-1.3" in v


def test_hover_del_tipo_di_una_mappa():
    text = HEAD + "  maps:\n    m1:\n      type: sine\n      r: 2\n" + TAIL
    h = _hover_at(text, "type: sine", "sine", 1)
    assert "-1" in h.contents.value and "divergere" in h.contents.value


def test_semantic_token_dell_espressione():
    text = HEAD + "  maps:\n    m1: {type: logistic, r: 3.5}\n  volume: (-18 + 4*m1)\n" + TAIL
    doc = yamlpos.parse(text)
    data = semtokens.tokens(doc, model.build(doc))
    row = text.splitlines().index("  volume: (-18 + 4*m1)")
    lines_with_tokens = set()
    line = 0
    for i in range(0, len(data), 5):
        line += data[i]
        lines_with_tokens.add(line)
    assert row in lines_with_tokens
