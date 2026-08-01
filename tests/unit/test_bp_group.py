"""BP group ``[points, interp]`` degli envelope engine (PGE #64, gl-ls #34).

Un run di breakpoint avvolto in un gruppo che dichiara l'interpolazione della
**propria macrozona**, simmetrico ai loop block: si usa da solo (envelope a una
zona) o dentro un envelope misto, accanto a loop block e breakpoint nudi.

La cosa che la validazione deve tenere ferma e' che i tempi dei punti del
gruppo sono **assoluti** — non percentuali del ciclo come il ``pattern`` della
forma compatta, ne' normalizzati in [0, 1] come i breakpoint di banda. E la
disambiguazione: il gruppo e' l'unica lista a 2 elementi con ``elem[0]`` lista
di punti ed ``elem[1]`` stringa, quindi non collide ne' con un breakpoint nudo
(``elem[0]`` numerico) ne' con un loop block (3-6 elementi).
"""
from glls import completion, diagnostics, hover, model, semtokens, yamlpos
from glls.model import bp_group_summary, is_bp_group, is_compact_env

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


def _dm(text):
    doc = yamlpos.parse(text)
    return doc, model.build(doc)


def diags_of(text):
    doc, m = _dm(text)
    return diagnostics.collect(doc, m)


def codes(text):
    return {d.code for d in diags_of(text)}


def _with_density(env):
    return BASE.replace("  sample: corpus.wav\n",
                        f"  sample: corpus.wav\n  density: {env}\n")


# --- riconoscimento e disambiguazione ---------------------------------------


def test_direct_group_is_recognised():
    assert is_bp_group([[[0.0, 0], [0.5, 30], [1.0, 5]], "cubic"])


def test_bare_breakpoint_is_not_a_group():
    # elem[0] numerico: e' un breakpoint [t, v]
    assert not is_bp_group([0.5, 30])


def test_breakpoint_run_is_not_a_group():
    assert not is_bp_group([[0, 10], [1, 20]])


def test_loop_block_is_not_a_group():
    # 3-6 elementi: forma compatta a cicli, non un gruppo
    block = [[[0, 8], [50, 18], [100, 8]], 0.7, 4, "linear"]
    assert not is_bp_group(block) and is_compact_env(block)


def test_group_and_compact_do_not_collide():
    group = [[[0, 0], [1, 5]], "cubic"]
    assert is_bp_group(group) and not is_compact_env(group)


def test_group_needs_a_string_in_position_one():
    assert not is_bp_group([[[0, 0], [1, 5]], 4])


def test_summary_reads_the_positional_form():
    s = bp_group_summary([[[0.0, 0], [0.5, 30], [1.0, 5]], "cubic"])
    assert s == "3 punti · cubic · t 0–1 (assoluti)"


# --- diagnostiche nuove -----------------------------------------------------


def test_group_interp_out_of_set():
    d = next(d for d in diags_of(_with_density("[[[0, 10], [1, 20]], 'smooth']"))
             if d.code == "bp-group-interp")
    assert "smooth" in d.message and "linear | cubic | step" in d.message


def test_group_interp_typo_suggests():
    d = next(d for d in diags_of(_with_density("[[[0, 10], [1, 20]], 'cubik']"))
             if d.code == "bp-group-interp")
    assert d.data["fix"]["new"] == "cubic"


def test_group_valid_interp_clean():
    for interp in ("linear", "cubic", "step"):
        text = _with_density(f"[[[0, 10], [1, 20]], '{interp}']")
        assert diags_of(text) == [], interp


def test_group_with_a_single_point():
    d = next(d for d in diags_of(_with_density("[[[0, 10]], 'cubic']"))
             if d.code == "bp-group-points")
    assert "almeno 2" in d.message


def test_group_per_point_type_validated():
    text = _with_density("[[[0, 10, 'step'], [1, 20]], 'cubic']")
    assert diags_of(text) == []
    bad = _with_density("[[[0, 10, 'smooth'], [1, 20]], 'cubic']")
    assert "bad-enum" in codes(bad)


def test_group_point_must_be_a_pair_or_triple():
    d = next(d for d in diags_of(_with_density("[[[0, 10, 'step', 9], [1, 20]], 'cubic']"))
             if d.code == "bp-group-point")
    assert "[t, v]" in d.message


def test_group_nested_inside_a_compact_pattern():
    # gruppo dentro il pattern di una forma compatta: annidamento vietato
    text = BASE.replace(
        "    values: [10, 30]\n",
        "    base: [[[[0, 0], [1, 5]], 'cubic'], 1, 4]\n    range: 2\n    n: 4\n")
    assert "bp-group-nested" in codes(text)


def test_compact_form_nested_inside_a_group():
    text = _with_density("[[[[0, 0], [25, 1]], 1, 4], 'cubic']")
    assert "bp-group-nested" in codes(text)


# --- bounds dentro il gruppo (prima passavano muti) -------------------------


def test_group_points_are_bounds_checked():
    d = next(d for d in diags_of(_with_density("[[[0, 10], [1, 9000]], 'cubic']"))
             if d.code == "out-of-bounds")
    assert "density" in d.message


def test_group_points_in_a_mixed_envelope_are_bounds_checked():
    env = ("[[[[0.0, 10], [0.2, 9000]], 'cubic'], "
           "[[[0.75, 6], [1.0, 20]], 'step']]")
    assert "out-of-bounds" in codes(_with_density(env))


def test_group_points_respect_the_grain_duration_unit():
    # 650 ms dentro un gruppo: valido, non 650 s (issue #35 vale anche qui)
    text = BASE.replace(
        "  sample: corpus.wav\n",
        "  sample: corpus.wav\n  grain:\n    duration_unit: milliseconds\n"
        "    duration: [[[0, 100], [1, 650]], 'cubic']\n")
    assert "out-of-bounds" not in codes(text)


# --- esclusione dai controlli sui breakpoint nudi ---------------------------


def test_group_times_are_absolute_not_band_normalised():
    # in una banda Y i tempi vivono in [0, 1] e t=50 sarebbe 'band-time': in un
    # gruppo sono assoluti, il warning non deve scattare
    text = BASE.replace(
        "    values: [10, 30]\n",
        "    base: [[[0, 5], [50, 12]], 'cubic']\n    range: 2\n    n: 4\n")
    assert "band-time" not in codes(text)


def test_bare_band_breakpoints_still_flagged():
    text = BASE.replace(
        "    values: [10, 30]\n",
        "    base: [[0, 5], [50, 12]]\n    range: 2\n    n: 4\n")
    assert "band-time" in codes(text)


def test_mixed_envelope_with_groups_does_not_read_points_as_times():
    # due macrozone: ognuna e' una lista a 2 elementi, e senza l'esclusione il
    # controllo dei tempi leggerebbe una lista di punti al posto di un numero
    env = ("[[[[0.0, 10], [0.2, 12]], 'cubic'], "
           "[[[0.75, 6], [1.0, 20]], 'step']]")
    assert diags_of(_with_density(env)) == []


def test_mixed_envelope_with_a_loop_block_between_two_groups():
    # tre macrozone: gruppo, loop block, gruppo. La cornice della forma compatta
    # (end_time numero, n_reps intero in posizione 1 e 2) e' quello che
    # distingue questo da una compatta col pattern scritto come gruppo
    env = ("[[[[0.0, 1], [0.2, 12], [0.4, 8]], 'cubic'], "
           "[[[0, 8], [50, 18], [100, 8]], 0.7, 4, 'linear'], "
           "[[[0.75, 6], [0.9, 6], [1.0, 1]], 'step']]")
    assert diags_of(_with_density(env)) == []


def test_loop_block_end_time_is_the_previous_border():
    # il loop block finisce a 0.7: un gruppo che riparte a 0.5 collide
    env = ("[[[0, 8], [50, 18], [100, 8]], 0.7, 4, 'linear'], "
           "[[[0.5, 6], [1.0, 1]], 'step']")
    assert "bp-group-collision" in codes(_with_density(f"[{env}]"))


def test_border_collision_is_a_warning():
    # la seconda zona parte a t=0.2, non oltre la prima (che finisce a 0.5):
    # l'engine trasla di DISCONTINUITY_OFFSET senza dirlo
    env = ("[[[[0.0, 10], [0.5, 12]], 'cubic'], "
           "[[[0.2, 6], [1.0, 20]], 'step']]")
    d = next(d for d in diags_of(_with_density(env))
             if d.code == "bp-group-collision")
    assert "DISCONTINUITY_OFFSET" in d.message


def test_no_collision_when_the_zones_are_ordered():
    env = ("[[[[0.0, 10], [0.5, 12]], 'cubic'], "
           "[[[0.75, 6], [1.0, 20]], 'step']]")
    assert "bp-group-collision" not in codes(_with_density(env))


# --- hover, semantic token, completion --------------------------------------


def _hover_at(text, line, col):
    doc, m = _dm(text)
    h = hover.hover(doc, m, line, col)
    return h.contents.value if h is not None else None


def test_hover_on_the_key_carries_the_legend():
    text = _with_density("[[[0, 10], [1, 20]], 'cubic']")
    line = text.split("\n").index("  density: [[[0, 10], [1, 20]], 'cubic']")
    md = _hover_at(text, line, 3)
    assert "BP group" in md and "tempi assoluti" in md


def test_hover_on_the_interp_slot_explains_the_position():
    text = _with_density("[[[0, 10], [1, 20]], 'cubic']")
    src = text.split("\n")
    line = src.index("  density: [[[0, 10], [1, 20]], 'cubic']")
    col = src[line].index("'cubic'") + 1
    md = _hover_at(text, line, col)
    assert "`interp` del BP group" in md and "segmenti **interni**" in md


def test_semantic_token_on_the_group_interp():
    text = _with_density("[[[0, 10], [1, 20]], 'cubic']")
    doc, m = _dm(text)
    src = text.split("\n")
    line = src.index("  density: [[[0, 10], [1, 20]], 'cubic']")
    col = src[line].index("'cubic'")   # lo span dello scalare include gli apici
    data = semtokens.tokens(doc, m)
    found, cur_line, cur_col = False, 0, 0
    for i in range(0, len(data), 5):
        d_line, d_col, length, tok, _mod = data[i:i + 5]
        cur_line += d_line
        cur_col = cur_col + d_col if d_line == 0 else d_col
        if cur_line == line and cur_col == col:
            found = tok == semtokens.TOKEN_TYPES.index("enumMember")
    assert found


def test_completion_offers_the_group_snippet_on_an_engine_env_key():
    text = BASE.replace("  sample: corpus.wav\n",
                        "  sample: corpus.wav\n  density: \n")
    doc, m = _dm(text)
    src = text.split("\n")
    line = src.index("  density: ")
    items = completion.complete(doc, m, line, len("  density: "))
    (item,) = [i for i in items if i.label == "zona_interp"]
    assert "linear,cubic,step" in item.insert_text


def test_completion_does_not_offer_the_snippet_outside_engine_envelopes():
    text = BASE + "sweep:\n  plateau: \n"
    doc, m = _dm(text)
    line = text.split("\n").index("  plateau: ")
    items = completion.complete(doc, m, line, len("  plateau: "))
    assert not any(i.label == "zona_interp" for i in items)
