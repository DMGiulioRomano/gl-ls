"""Unit test della diagnostica: ogni regola del runtime vista dall'editor."""
from glls import diagnostics, model, yamlpos

BASE = """study_id: t
duration: 20
base:
  onset: 0
  duration: 6
  sample: corpus.wav
axes:
  density:
    path: density
    baseline: 20
    values: [10, 30]
"""


def diags_of(text):
    doc = yamlpos.parse(text)
    m = model.build(doc)
    return diagnostics.collect(doc, m)


def codes(text):
    return {d.code for d in diags_of(text)}


def test_valid_study_no_diagnostics():
    assert diags_of(BASE) == []


def test_stack_requires_duration():
    text = BASE.replace("duration: 20\n", "") + "stack: {}\n"
    assert "stack-duration" in codes(text)


def test_axis_without_generator():
    text = BASE.replace("    values: [10, 30]\n", "")
    assert "no-generator" in codes(text)


def test_multiple_generators():
    text = BASE + "    ramp: {start: 1, stop: 5, step: 1}\n"
    assert "multi-generator" in codes(text)


def test_axis_missing_path():
    text = BASE.replace("    path: density\n", "")
    assert "axis-no-path" in codes(text)


def test_out_of_bounds_values():
    text = BASE.replace("values: [10, 30]", "values: [10, 9000]")
    assert "out-of-bounds" in codes(text)


def test_baseline_required_for_density():
    text = BASE.replace("    baseline: 20\n", "")
    assert "baseline-required" in codes(text)


def test_n_ownership_band_without_n_needs_walk():
    text = BASE.replace("values: [10, 30]", "base: 5\n    range: 10")
    assert "n-ownership" in codes(text)
    # con la camminata in stack l'errore sparisce
    ok = text + "stack:\n  density:\n    base: 5\n"
    assert "n-ownership" not in codes(ok)


def test_n_ownership_walk_with_enumerating_y():
    text = BASE + "stack:\n  density:\n    base: 5\n"
    assert "n-ownership" in codes(text)


def test_stack_unknown_axis():
    text = BASE + "stack:\n  densty:\n    base: 5\n"
    assert "unknown-axis" in codes(text)


def test_stack_rand_wrapper_migration():
    text = (BASE.replace("values: [10, 30]", "base: 5\n    range: 10")
            + "stack:\n  density:\n    rand: {cps: {base: 5, range: 2}}\n")
    assert "rand-wrapper" in codes(text)


def test_stack_bad_unit():
    text = (BASE.replace("values: [10, 30]", "base: 5\n    range: 10")
            + "stack:\n  unit: ms\n  density:\n    base: 5\n")
    assert "bad-unit" in codes(text)


def test_walk_extra_keys():
    text = (BASE.replace("values: [10, 30]", "base: 5\n    range: 10")
            + "stack:\n  density:\n    base: 5\n    curve: 2\n")
    assert "walk-keys" in codes(text)


def test_walk_nonpositive_band():
    text = (BASE.replace("values: [10, 30]", "base: 5\n    range: 10")
            + "stack:\n  density:\n    base: [[0, 5], [1, 0]]\n")
    assert "walk-nonpositive" in codes(text)


def test_walk_runaway_estimate():
    text = (BASE.replace("values: [10, 30]", "base: 5\n    range: 10")
            + "stack:\n  density:\n    base: 2000\n")
    assert "walk-runaway" in codes(text)


def test_sweep_combine_removed():
    text = BASE + "sweep:\n  combine: parallel\n"
    assert "sweep-combine" in codes(text)


def test_sweep_orderings_unknown_axis():
    text = BASE + "sweep:\n  orderings:\n    - [density, grain]\n"
    assert "unknown-axis" in codes(text)


def test_ramp_step_positive():
    text = BASE.replace("values: [10, 30]",
                        "ramp: {start: 1, stop: 5, step: 0}")
    assert "ramp-step" in codes(text)


def test_unknown_key_suggestion():
    text = BASE.replace("    values: [10, 30]\n",
                        "    valuse: [10, 30]\n")
    ds = diags_of(text)
    d = next(d for d in ds if d.code == "unknown-key")
    assert "values" in d.message


def test_pitch_multiple_units():
    text = BASE + "  pitch2:\n    path: pitch.semitones\n    baseline: 0\n    values: [0]\n"
    text = text.replace("base:\n", "base:\n  pitch:\n    semitones: 0\n    ratio: 1\n")
    assert "pitch-units" in codes(text)


def test_unknown_window():
    text = BASE.replace("base:\n", "base:\n  grain:\n    envelope: hannning\n")
    ds = diags_of(text)
    d = next(d for d in ds if d.code == "unknown-window")
    assert "hanning" in d.message


def test_grain_reverse_boolean_rejected():
    text = BASE.replace("base:\n", "base:\n  grain:\n    reverse: true\n")
    assert "grain-reverse" in codes(text)


def test_engine_envelope_bounds():
    text = BASE.replace("base:\n", "base:\n  volume: [[0, -6], [20, 40]]\n")
    assert "out-of-bounds" in codes(text)


def test_grain_duration_samples_scalar_not_flagged():
    # 512 campioni ~ 10.7 ms: letti come secondi sarebbero > 10 (falso positivo)
    text = BASE.replace(
        "base:\n",
        "base:\n  grain:\n    duration: 512\n    duration_unit: samples\n")
    assert "out-of-bounds" not in codes(text)


def test_grain_duration_seconds_still_flagged():
    text = BASE.replace("base:\n", "base:\n  grain:\n    duration: 512\n")
    assert "out-of-bounds" in codes(text)


def test_grain_duration_samples_real_violation_flagged():
    # 500000 campioni a 48 kHz ~ 10.4 s: fuori bounds anche dopo la conversione
    text = BASE.replace(
        "base:\n",
        "base:\n  grain:\n    duration: 500000\n    duration_unit: samples\n")
    ds = diags_of(text)
    d = next(d for d in ds if d.code == "out-of-bounds")
    assert "campioni" in d.message


def test_grain_duration_samples_below_one_sample_flagged():
    # il floor in spazio-campioni e' 1 campione (1/output_sr secondi)
    text = BASE.replace(
        "base:\n",
        "base:\n  grain:\n    duration: 0.5\n    duration_unit: samples\n")
    assert "out-of-bounds" in codes(text)


def test_grain_duration_samples_envelope_not_flagged():
    text = BASE.replace(
        "base:\n",
        "base:\n  grain:\n    duration: [[0, 64], [6, 4096]]\n"
        "    duration_unit: samples\n")
    assert "out-of-bounds" not in codes(text)


def test_grain_duration_range_samples_not_flagged():
    # l'engine scala anche duration_range con duration_unit: samples
    text = BASE.replace(
        "base:\n",
        "base:\n  grain:\n    duration: 512\n    duration_range: 128\n"
        "    duration_unit: samples\n")
    assert "out-of-bounds" not in codes(text)


def test_grain_duration_samples_axis_values_not_flagged():
    text = BASE.replace(
        "base:\n",
        "base:\n  grain:\n    duration: 512\n    duration_unit: samples\n")
    text += """  grain_duration:
    path: grain.duration
    baseline: 512
    values: [128, 2048]
"""
    assert "out-of-bounds" not in codes(text)


def test_grain_duration_axis_values_seconds_still_flagged():
    text = BASE + """  grain_duration:
    path: grain.duration
    baseline: 0.05
    values: [11, 50]
"""
    assert "out-of-bounds" in codes(text)


def test_grain_duration_samples_stream_override_not_flagged():
    text = BASE + """streams:
  a:
    base:
      grain:
        duration: 512
        duration_unit: samples
"""
    assert "out-of-bounds" not in codes(text)


def test_grain_duration_samples_inherited_by_stream():
    text = BASE.replace(
        "base:\n",
        "base:\n  grain:\n    duration: 512\n    duration_unit: samples\n")
    text += """streams:
  a:
    base:
      grain:
        duration: 1024
"""
    assert "out-of-bounds" not in codes(text)


def test_grain_duration_stream_seconds_override_still_flagged():
    # lo stream torna esplicitamente ai secondi: 512 e' di nuovo fuori bounds
    text = BASE.replace(
        "base:\n",
        "base:\n  grain:\n    duration: 512\n    duration_unit: samples\n")
    text += """streams:
  a:
    base:
      grain:
        duration: 512
        duration_unit: seconds
"""
    assert "out-of-bounds" in codes(text)


def test_density_fill_factor_exclusive():
    text = BASE.replace("base:\n", "base:\n  density: 20\n  fill_factor: 2\n")
    assert "density-fill" in codes(text)


def test_spread_count_mismatch():
    text = BASE + """streams:
  fan:
    spread:
      n: 4
      over:
        base.onset:
          values: [0, 1, 2]
"""
    assert "spread-count" in codes(text)


def test_spread_no_n_source():
    text = BASE + """streams:
  fan:
    spread:
      over:
        base.onset:
          ramp: {start: 0, step: 2}
"""
    assert "spread-no-n" in codes(text)


def test_spread_unknown_axis_in_over():
    text = BASE + """streams:
  fan:
    spread:
      n: 2
      over:
        axes.densty.baseline:
          values: [1, 2]
"""
    assert "unknown-axis" in codes(text)


def test_expr_unknown_name():
    text = BASE.replace(
        "values: [10, 30]",
        'n: 4\n    base:\n      expr: "env * 50"\n      let:\n        env2: [[0, 1], [1, 2]]',
    )
    ds = diags_of(text)
    assert any(d.code == "expr" and "env" in d.message for d in ds)


def test_expr_env_times_env():
    text = BASE.replace(
        "values: [10, 30]",
        'n: 4\n    base:\n      expr: "a * b"\n      let:\n        a: [[0, 1], [1, 2]]\n        b: [[0, 1], [1, 2]]',
    )
    ds = diags_of(text)
    assert any(d.code == "expr" and "due Env" in d.message for d in ds)


def test_expr_valid_is_clean():
    text = BASE.replace(
        "values: [10, 30]",
        'n: 4\n    base:\n      expr: "env * 50"\n      let:\n        env: [[0, 1], [1, 2]]',
    )
    assert not any(d.code == "expr" for d in diags_of(text))


def test_duplicate_key_warning():
    text = BASE + "seed: 1\nseed: 2\n"
    assert "duplicate-key" in codes(text)


def test_syntax_error_single_diag():
    ds = diags_of("axes:\n  density\n    path: x\n")
    assert len(ds) == 1
    assert ds[0].code == "yaml-syntax"


def test_band_time_out_of_range():
    text = BASE.replace("values: [10, 30]",
                        "n: 4\n    base: [[0, 5], [2, 10]]")
    assert "band-time" in codes(text)


def test_curve_with_step_rejected():
    text = BASE.replace(
        "values: [10, 30]",
        "n: 4\n    base: {type: step, points: [[0, 5], [1, 10]], curve: 2}",
    )
    assert "curve-step" in codes(text)


def test_loop_end_before_start():
    text = BASE.replace(
        "base:\n",
        "base:\n  pointer:\n    loop_start: 3\n    loop_end: 1\n",
    )
    assert "loop-order" in codes(text)


def test_expr_node_in_static_base_param_is_clean():
    # expr/let valgono anche nei parametri statici dello stream (base.*)
    text = BASE.replace(
        "base:\n",
        'base:\n  volume:\n    expr: "v - 1"\n    let: {v: -19}\n',
    )
    assert not any(d.code == "unknown-key" for d in diags_of(text))


def test_stream_level_seed_in_base_is_known():
    text = BASE.replace("base:\n", "base:\n  seed: 256\n")
    assert "unknown-key" not in codes(text)


def test_expr_in_spread_uses_containing_stream_n():
    # due entry-spread: l'expr vive nella seconda (n=5); 1/(n-5) deve dare
    # divisione per zero con n=5, non passare pulito con la n=3 della prima.
    text = BASE + """streams:
  primo:
    spread:
      n: 3
      over:
        base.onset:
          ramp: {start: 0, step: 2}
  secondo:
    spread:
      n: 5
      over:
        base.onset:
          expr: "1/(n-5)"
"""
    assert "expr" in codes(text)


def test_expr_outside_spread_not_marked_as_spread():
    # uno stream chiamato 'spread' non deve attivare lo scope i/n riservato
    text = BASE + """streams:
  spread:
    base:
      volume:
        expr: "i * 2"
"""
    # fuori da un vero blocco spread, 'i' e' un nome ignoto -> errore expr
    assert "expr" in codes(text)


def test_unknown_pitch_like_path_warns():
    text = BASE.replace("path: density", "path: pitchfoo")
    assert "unknown-path" in codes(text)


# ---------------------------------------------------------------------------
# spread.over: chiavi puntate (issue #3)


def _spread(over_block, n_line=""):
    body = n_line + "      over:\n" + over_block
    return BASE + "streams:\n  fan:\n    spread:\n" + body


def test_spread_dotted_values_clean():
    text = _spread("        base.pointer.start.values: [0.1, 0.25, 0.4]\n")
    assert diags_of(text) == []


def test_spread_dotted_values_owns_count():
    text = _spread("        base.onset.values: [0, 1, 2]\n", "      n: 4\n")
    assert "spread-count" in codes(text)


def test_spread_dotted_values_no_false_no_n():
    # prima del supporto: 'spread-no-n' anche se la forma puntata possiede n
    text = _spread("        base.onset.values: [0, 1, 2]\n")
    assert "spread-no-n" not in codes(text)


def test_spread_dotted_band_three_lines_clean():
    text = _spread(
        "        base.onset.base: 2\n"
        "        base.onset.range: 3\n"
        "        base.onset.seed: 42\n",
        "      n: 5\n",
    )
    assert diags_of(text) == []


def test_spread_dotted_band_n_owns_count():
    text = _spread(
        "        base.onset.base: 2\n"
        "        base.onset.n: 5\n",
    )
    assert "spread-no-n" not in codes(text)
    conflict = _spread(
        "        base.onset.base: 2\n"
        "        base.onset.n: 5\n",
        "      n: 4\n",
    )
    assert "spread-count" in codes(conflict)


def test_spread_dotted_conflict_two_generators():
    text = _spread(
        "        base.onset.values: [1, 2]\n"
        '        base.onset.expr: "i"\n',
    )
    ds = diags_of(text)
    d = next(d for d in ds if d.code == "spread-strategy")
    assert "base.onset.values" in d.message
    assert "base.onset.expr" in d.message


def test_spread_bare_scalar_needs_strategy():
    text = _spread("        base.onset: 5\n", "      n: 2\n")
    assert "spread-strategy" in codes(text)


def test_spread_bare_list_needs_strategy():
    # prima passava in silenzio (e il conteggio veniva dalla lista nuda)
    text = _spread("        base.onset: [0, 1, 2]\n")
    assert "spread-strategy" in codes(text)


def test_spread_dotted_unknown_axis():
    text = _spread("        axes.densty.baseline.values: [1, 2]\n")
    assert "unknown-axis" in codes(text)


def test_spread_dotted_bad_head_warns_on_effective_path():
    text = _spread("        pointer.start.values: [1, 2]\n")
    ds = diags_of(text)
    d = next(d for d in ds if d.code == "over-path")
    assert "'pointer.start'" in d.message


def test_spread_dotted_ramp_non_dict_is_error():
    text = _spread("        base.onset.ramp: [1, 2]\n", "      n: 2\n")
    assert "ramp-type" in codes(text)


def test_spread_dotted_negative_range_span_on_range_line():
    text = _spread(
        "        base.onset.base: 2\n"
        "        base.onset.range: -3\n",
        "      n: 2\n",
    )
    ds = diags_of(text)
    d = next(d for d in ds if d.code == "negative-range")
    lines = text.splitlines()
    row = next(i for i, l in enumerate(lines) if "base.onset.range" in l)
    assert d.range.start.line == row


def test_spread_dotted_expr_evaluated():
    text = _spread('        base.onset.expr: "1/(n-5)"\n', "      n: 5\n")
    assert "expr" in codes(text)


def test_spread_dotted_expr_valid_clean():
    text = _spread('        base.onset.expr: "i * 2"\n', "      n: 3\n")
    assert diags_of(text) == []


def test_spread_dotted_expr_functions_clean():
    text = _spread('        base.onset.expr: "floor(i / 2)"\n', "      n: 4\n")
    assert diags_of(text) == []


def test_spread_mixed_dotted_expr_nested_let_clean():
    text = _spread(
        '        base.onset.expr: "v * i"\n'
        "        base.onset:\n"
        "          let: {v: 2}\n",
        "      n: 3\n",
    )
    assert diags_of(text) == []


def test_spread_dotted_expr_reserved_names():
    text = _spread(
        '        base.onset.expr: "i"\n'
        "        base.onset:\n"
        "          let: {i: 1}\n",
        "      n: 3\n",
    )
    assert "expr-reserved" in codes(text)


def test_spread_nested_expr_band_let_clean():
    # parita' col runtime: la banda-let (variabile random per-stream) e'
    # ammessa nella strategy expr dello spread
    text = _spread(
        "        base.onset:\n"
        '          expr: "v * i"\n'
        "          let:\n"
        "            v: {base: 1, range: 2}\n",
        "      n: 3\n",
    )
    assert diags_of(text) == []


def test_spread_band_let_wrong_marker():
    text = _spread(
        "        base.onset:\n"
        '          expr: "v * i"\n'
        "          let:\n"
        "            v: {values: [1, 2]}\n",
        "      n: 2\n",
    )
    assert "expr-let-band" in codes(text)


def test_spread_band_let_with_n_rejected():
    text = _spread(
        "        base.onset:\n"
        '          expr: "v * i"\n'
        "          let:\n"
        "            v: {base: 1, n: 4}\n",
        "      n: 4\n",
    )
    assert "expr-let-band" in codes(text)


def test_spread_n_expr_node_not_bad_n():
    # percorso-v1: spread.n puo' essere un nodo-expr
    text = _spread(
        "        base.onset:\n"
        "          ramp: {start: 0, step: 2}\n",
        '      n: {expr: "k * 2", let: {k: 2}}\n',
    )
    assert "bad-n" not in codes(text)
    assert diags_of(text) == []


def test_spread_n_expr_counts_against_owned():
    text = _spread(
        "        base.onset.values: [0, 1, 2]\n",
        '      n: {expr: "k * 2", let: {k: 2}}\n',
    )
    assert "spread-count" in codes(text)


def test_spread_n_expr_non_integer_result():
    text = _spread(
        "        base.onset:\n"
        "          ramp: {start: 0, step: 2}\n",
        '      n: {expr: "0.5"}\n',
    )
    assert "bad-n" in codes(text)


def test_spread_n_expr_in_n_scope_is_unknown():
    # in spread.n il runtime non fornisce i/n: un nome fuori dal let e' ignoto
    text = _spread(
        "        base.onset:\n"
        "          ramp: {start: 0, step: 2}\n",
        '      n: {expr: "i + 1"}\n',
    )
    assert "expr" in codes(text)


def test_pitch_dotted_path_is_known():
    text = BASE.replace("path: density", "path: pitch.semitones")
    assert "unknown-path" not in codes(text)

# ---------------------------------------------------------------------------
# expr annidati dentro let (granulation-studies #28 / gl-ls #7)


def test_nested_expr_in_let_is_clean():
    # l'esempio della issue: 'shape' riferisce il fratello 'env'
    text = BASE.replace(
        "base:\n",
        'base:\n  volume:\n    expr: "shape - 21.2"\n    let:\n'
        "      env: [[0, 1], [0.1583, 1.5]]\n"
        '      shape: {expr: "min(env, 1.2)"}\n',
    )
    assert not any(d.code == "expr" for d in diags_of(text))


def test_nested_expr_not_rechecked_standalone():
    # il nodo annidato non va validato da solo: fuori dallo scope del
    # contenitore 'env' sarebbe un nome ignoto (falso positivo)
    text = BASE.replace(
        "base:\n",
        'base:\n  volume:\n    expr: "shape - 21.2"\n    let:\n'
        "      env: [[0, 1], [0.1583, 1.5]]\n"
        '      shape: {expr: "min(env, 1.2)"}\n',
    )
    assert diags_of(text) == []


def test_nested_expr_cycle_flagged():
    text = BASE.replace(
        "base:\n",
        'base:\n  volume:\n    expr: "a - 20"\n    let:\n'
        '      a: {expr: "b"}\n'
        '      b: {expr: "a"}\n',
    )
    ds = diags_of(text)
    assert any(d.code == "expr" and "ciclo" in d.message for d in ds)


def test_nested_expr_self_reference_from_shadowing_flagged():
    # un nome ridefinito nel let interno non vede il nome che ombreggia
    text = BASE.replace(
        "base:\n",
        'base:\n  volume:\n    expr: "v - 20"\n    let:\n'
        "      a: 1\n"
        '      v: {expr: "a", let: {a: {expr: "a + 1"}}}\n',
    )
    ds = diags_of(text)
    assert any(d.code == "expr" and "ciclo" in d.message for d in ds)


def test_nested_expr_syntactic_depth_flagged():
    inner = '{expr: "1"}'
    for _ in range(9):
        inner = '{expr: "v", let: {v: %s}}' % inner
    text = BASE.replace(
        "base:\n",
        "base:\n  volume:\n    expr: \"v - 20\"\n    let:\n      v: %s\n" % inner,
    )
    ds = diags_of(text)
    assert any(d.code == "expr" and "profondit" in d.message for d in ds)


def test_nested_expr_error_carries_let_context():
    text = BASE.replace(
        "base:\n",
        'base:\n  volume:\n    expr: "v - 20"\n    let:\n'
        '      v: {expr: "boh"}\n',
    )
    ds = diags_of(text)
    assert any(d.code == "expr" and "let.v" in d.message for d in ds)


def test_generator_in_let_still_flagged():
    text = BASE.replace(
        "base:\n",
        'base:\n  volume:\n    expr: "v - 20"\n    let:\n'
        "      v: {ramp: {start: 0, step: 1}}\n",
    )
    ds = diags_of(text)
    assert any(d.code == "expr" and "statiche" in d.message for d in ds)


def test_variable_named_let_is_container_not_skip_marker():
    # una variabile del let chiamata 'let': lo skip dei nodi annidati deve
    # riconoscere 'let' come chiave-contenitore (genitore = nodo-expr), non
    # come nome di variabile — il nodo annidato resta validato dal contenitore
    text = BASE.replace(
        "base:\n",
        'base:\n  volume:\n    expr: "let - 20"\n    let:\n'
        "      env: [[0, 1], [0.1583, 1.5]]\n"
        '      let: {expr: "min(env, 1.2)"}\n',
    )
    assert not any(d.code == "expr" for d in diags_of(text))


def test_spread_static_let_nested_expr_clean():
    # nella strategy expr dello spread il nodo annidato convive con la
    # banda-let e vede i nomi iniettati (i, n, pescaggi)
    text = _spread(
        "        base.onset:\n"
        '          expr: "v * i + k"\n'
        "          let:\n"
        "            v: {base: 1, range: 2}\n"
        '            k: {expr: "n * 2"}\n',
        "      n: 3\n",
    )
    assert diags_of(text) == []


def test_spread_static_let_nested_expr_error_on_expr():
    text = _spread(
        "        base.onset:\n"
        '          expr: "k * i"\n'
        "          let:\n"
        '            k: {expr: "boh"}\n',
        "      n: 3\n",
    )
    ds = diags_of(text)
    assert any(d.code == "expr" and "let.k" in d.message for d in ds)
