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
