"""``spread.n`` come envelope (granstudies ``7d83362``, issue #32).

Il numero di voci *udibili* varia nel tempo dentro la singola versione: gli
stream si generano tutti fino al **picco** di ``n(t)`` (arrotondato in su) e un
gate su ``base.volume`` li accende e spegne con
``gain(voce i) = clamp(n(t) - i, 0, 1)``.

Qui si verifica che la forma non sia piu' un falso positivo, che il conteggio
per il cross-check con ``over`` sia il picco, e i conflitti sul volume — che il
runtime tratta come errore esplicito perche' gate e volume scritto a mano
scriverebbero lo stesso campo.
"""
from glls import completion, diagnostics, hover, model, yamlpos

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


def _fan(n, over="base.onset: {values: [0, 1, 2, 3]}", extra=""):
    return BASE + (
        "streams:\n"
        "  fan:\n"
        f"{extra}"
        "    spread:\n"
        f"      n: {n}\n"
        "      over:\n"
        f"        {over}\n"
    )


def _codes(text):
    doc = yamlpos.parse(text)
    return {d.code for d in diagnostics.collect(doc, model.build(doc))}


def _diags(text):
    doc = yamlpos.parse(text)
    return diagnostics.collect(doc, model.build(doc))


# --- riconoscimento -----------------------------------------------------------


def test_predicato_distingue_env_da_scalare_e_nodo_expr():
    assert model.is_n_env([[0, 1], [1, 4]])
    assert model.is_n_env([1, 4])                       # shorthand
    assert model.is_n_env({"type": "step", "points": [[0, 1]]})
    assert not model.is_n_env(4)
    assert not model.is_n_env({"expr": "2 + 2"})        # nodo-expr: scalare
    assert not model.is_n_env([])


def test_picco_arrotondato_in_su():
    assert model.n_env_peak([[0, 1], [1, 4]]) == 4
    assert model.n_env_peak([[0, 1], [1, 3.2]]) == 4    # 3.2 voci -> ne servono 4
    assert model.n_env_peak({"type": "step", "points": [[0, 1], [0.75, 4]]}) == 4
    assert model.n_env_peak([1, 4]) == 4
    assert model.n_env_peak([[0, 1], [1, "x"]]) is None


# --- niente piu' falso positivo -----------------------------------------------


def test_env_di_n_non_e_piu_un_errore():
    assert _codes(_fan("[[0, 1], [1, 4]]")) == set()


def test_forma_dict_con_type_step():
    text = _fan("{type: step, points: [[0, 1], [0.5, 2], [0.75, 4]]}")
    assert _codes(text) == set()


def test_shorthand_a_due_valori():
    assert _codes(_fan("[1, 4]")) == set()


def test_scalare_e_nodo_expr_restano_validi():
    assert _codes(_fan("4")) == set()
    assert _codes(_fan('{expr: "2 * 2"}')) == set()


def test_scalare_sbagliato_resta_errore():
    assert "bad-n" in _codes(_fan("0"))
    assert "bad-n" in _codes(_fan("'quattro'"))


# --- il conteggio per il cross-check e' il picco ------------------------------


def test_il_picco_e_il_conteggio_confrontato_con_over():
    # over possiede 3 valori, il picco di n e' 4: discordanti
    text = _fan("[[0, 1], [1, 4]]", over="base.onset: {values: [0, 1, 2]}")
    assert "spread-count" in _codes(text)


def test_il_messaggio_del_mismatch_riporta_il_picco():
    text = _fan("[[0, 1], [1, 4]]", over="base.onset: {values: [0, 1, 2]}")
    (d,) = [x for x in _diags(text) if x.code == "spread-count"]
    assert "n: 4" in d.message


def test_ne_il_primo_ne_l_ultimo_punto():
    # n(t) sale a 4 e ridiscende a 1: il conteggio resta 4, non 1
    text = _fan("[[0, 1], [0.5, 4], [1, 1]]")
    assert _codes(text) == set()


def test_il_modello_genera_gli_stream_del_picco():
    doc = yamlpos.parse(_fan("[[0, 1], [1, 4]]"))
    assert model.build(doc).streams["fan"].spread_n == 4


# --- vincoli propri dell'Env di n ---------------------------------------------


def test_picco_sotto_una_voce_e_errore():
    text = _fan("[[0, 0], [1, 0]]", over="base.onset: {values: [0]}")
    (d,) = [x for x in _diags(text) if x.code == "bad-n"]
    assert "almeno a 1 voce" in d.message


def test_valori_non_numerici_nei_punti():
    text = _fan("[[0, 1], [1, 'quattro']]")
    (d,) = [x for x in _diags(text) if x.code == "bad-n"]
    assert "valori numerici" in d.message


def test_forma_compatta_a_cicli_non_vale_per_n():
    # il runtime la legge come Env e trova un pattern al posto di un numero
    text = _fan("[[[0, 1], [25, 4]], 1, 4]")
    assert "bad-n" in _codes(text)


# --- conflitti sul volume (il gate scrive base.volume) ------------------------


def test_conflitto_con_over_base_volume():
    text = _fan("[[0, 1], [1, 4]]",
                over="base.volume: {values: [-6, -6, -6, -6]}")
    (d,) = [x for x in _diags(text) if x.code == "spread-n-gate"]
    assert "over.base.volume" in d.message


def test_conflitto_con_over_base_volume_in_forma_dotted():
    text = BASE + (
        "streams:\n"
        "  fan:\n"
        "    spread:\n"
        "      n: [[0, 1], [1, 4]]\n"
        "      over.base.volume.values: [-6, -6, -6, -6]\n"
    )
    assert "spread-n-gate" in _codes(text)


def test_volume_di_documento_gia_envelope():
    text = _fan("[[0, 1], [1, 4]]").replace(
        "  sample: corpus.wav\n", "  sample: corpus.wav\n  volume: [[0, -12], [1, 0]]\n")
    (d,) = [x for x in _diags(text) if x.code == "spread-n-gate"]
    assert "dev'essere uno scalare" in d.message


def test_volume_di_entry_gia_envelope():
    text = _fan("[[0, 1], [1, 4]]",
                extra="    base:\n      volume: [[0, -12], [1, 0]]\n")
    assert "spread-n-gate" in _codes(text)


def test_volume_scalare_di_entry_copre_quello_di_documento():
    # la entry dichiara il livello 'voce accesa': il documento non conta piu'
    text = _fan("[[0, 1], [1, 4]]",
                extra="    base:\n      volume: -6\n").replace(
        "  sample: corpus.wav\n", "  sample: corpus.wav\n  volume: [[0, -12], [1, 0]]\n")
    assert "spread-n-gate" not in _codes(text)


def test_volume_scalare_di_documento_va_bene():
    text = _fan("[[0, 1], [1, 4]]").replace(
        "  sample: corpus.wav\n", "  sample: corpus.wav\n  volume: -6\n")
    assert _codes(text) == set()


def test_volume_assente_vale_zero_db():
    assert "spread-n-gate" not in _codes(_fan("[[0, 1], [1, 4]]"))


def test_env_malformato_non_aggiunge_anche_il_gate():
    # il runtime si ferma in _resolve_n e non arriva mai a scrivere il gate:
    # un solo errore, quello sul picco
    text = _fan("[[0, 1], [1, 'quattro']]").replace(
        "  sample: corpus.wav\n", "  sample: corpus.wav\n  volume: [[0, -12], [1, 0]]\n")
    assert "spread-n-gate" not in _codes(text)


def test_nessun_gate_con_n_scalare():
    text = _fan("4", over="base.volume: {values: [-6, -6, -6, -6]}")
    assert "spread-n-gate" not in _codes(text)


def test_nodo_expr_sul_volume_che_da_uno_scalare_non_e_conflitto():
    text = _fan("[[0, 1], [1, 4]]").replace(
        "  sample: corpus.wav\n",
        "  sample: corpus.wav\n  volume: {expr: \"liv * 2\"}\n",
    ) + "let:\n  liv: -3\n"
    assert "spread-n-gate" not in _codes(text)


def test_nodo_expr_sul_volume_che_da_un_envelope_e_conflitto():
    text = _fan("[[0, 1], [1, 4]]").replace(
        "  sample: corpus.wav\n",
        "  sample: corpus.wav\n  volume: {expr: \"profilo + 2\"}\n",
    ) + "let:\n  profilo: [[0, -12], [1, 0]]\n"
    assert "spread-n-gate" in _codes(text)


def test_il_blocco_spread_globale_da_solo_non_monta_il_gate():
    # il globale e' un default parziale: il gate lo monta la entry che lo
    # eredita, e quella entry puo' ridichiarare n scalare
    text = BASE.replace(
        "  sample: corpus.wav\n", "  sample: corpus.wav\n  volume: [[0, -12], [1, 0]]\n"
    ) + "spread:\n  n: [[0, 1], [1, 4]]\n"
    assert "spread-n-gate" not in _codes(text)


def test_il_gate_scatta_sulla_entry_che_eredita_il_globale():
    text = BASE.replace(
        "  sample: corpus.wav\n", "  sample: corpus.wav\n  volume: [[0, -12], [1, 0]]\n"
    ) + (
        "spread:\n"
        "  n: [[0, 1], [1, 4]]\n"
        "streams:\n"
        "  fan:\n"
        "    spread:\n"
        "      over:\n"
        "        base.onset: {values: [0, 1, 2, 3]}\n"
    )
    assert "spread-n-gate" in _codes(text)


# --- feature d'appoggio -------------------------------------------------------


def test_hover_su_n_documenta_la_forma_env():
    text = _fan("[[0, 1], [1, 4]]")
    doc = yamlpos.parse(text)
    row = next(i for i, l in enumerate(text.splitlines()) if l.strip().startswith("n:"))
    h = hover.hover(doc, model.build(doc), row, 6)
    assert h is not None
    assert "come envelope" in h.contents.value
    assert "clamp(n(t) - i, 0, 1)" in h.contents.value
    assert "generato" in h.contents.value


def test_snippet_n_nel_tempo_nel_contesto_spread():
    text = BASE + "streams:\n  fan:\n    spread:\n      \n"
    doc = yamlpos.parse(text)
    items = completion.complete(doc, model.build(doc), 12, 6)
    (item,) = [i for i in items if i.label == "n_nel_tempo"]
    assert item.insert_text.startswith("n: [[0, ${1:1}], [1, ${2:4}]]")
