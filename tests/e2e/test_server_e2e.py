"""Test end-to-end: il server vero, via protocollo LSP su stdio.

Ogni test esercita il flusso completo che farebbe un editor: initialize,
didOpen/didChange, richieste, e per le code action l'applicazione reale dei
TextEdit al testo, verificando i numeri ricalcolati.
"""
import re

import pytest
import yaml

from .lsp_client import LspClient, apply_edits

URI = "file:///tmp/study.yml"

STUDY = """study_id: e2e_test
duration: 20
base:
  onset: 0
  duration: 6
  sample: corpus.wav
  time_mode: normalized
  volume: -6
  grain:
    envelope: hanning
axes:
  density:
    path: density
    baseline: 20
    base: 5
    range: 10
  grain_duration:
    path: grain.duration
    n: 9
    base: 0.002
    range: 0.008
stack:
  density:
    base: [[0, 20], [1, 4]]
    range: 5
    seed: 7
streams:
  base: {}
  nube:
    spread:
      n: 4
      over:
        base.onset:
          values: [0, 2, 4, 6]
"""


@pytest.fixture(scope="module")
def client():
    c = LspClient()
    c.initialize()
    yield c
    c.shutdown()


def test_initialize_capabilities():
    c = LspClient()
    result = c.initialize()
    caps = result["capabilities"]
    assert caps.get("completionProvider")
    assert caps.get("hoverProvider")
    assert caps.get("codeActionProvider")
    assert caps.get("semanticTokensProvider", {}).get("legend", {}).get("tokenTypes")
    assert result["serverInfo"]["name"] == "gl-ls"
    c.shutdown()


def test_clean_study_has_no_diagnostics(client):
    diags = client.open(URI, STUDY)
    assert diags == []


def test_diagnostics_on_broken_study(client):
    uri = "file:///tmp/broken.yml"
    broken = STUDY.replace("    base: 5\n    range: 10\n",
                           "    base: 5\n    range: 10\n    values: [1, 2]\n")
    diags = client.open(uri, broken)
    codes = {d.get("code") for d in diags}
    assert "multi-generator" in codes
    # la Y enumera ma la camminata-X possiede n
    assert "n-ownership" in codes


def test_syntax_error_diagnostic(client):
    uri = "file:///tmp/syntax.yml"
    diags = client.open(uri, "axes:\n  density\n    path: x\n")
    assert len(diags) == 1
    assert diags[0]["code"] == "yaml-syntax"
    assert diags[0]["severity"] == 1


def test_completion_keys_in_axis(client):
    uri = "file:///tmp/completion.yml"
    text = STUDY + "  extra:\n    "
    client.open(uri, text)
    lines = text.split("\n")
    result = client.request("textDocument/completion", {
        "textDocument": {"uri": uri},
        "position": {"line": len(lines) - 1, "character": 4},
    })
    items = result["items"] if isinstance(result, dict) else result
    labels = {i["label"] for i in items}
    # contesto stream_override dentro streams
    assert {"base", "axes", "sweep", "stack", "spread"} <= labels


def test_completion_window_values(client):
    uri = "file:///tmp/completion2.yml"
    text = "base:\n  grain:\n    envelope: \n"
    client.open(uri, text)
    result = client.request("textDocument/completion", {
        "textDocument": {"uri": uri},
        "position": {"line": 2, "character": 14},
    })
    items = result["items"] if isinstance(result, dict) else result
    labels = {i["label"] for i in items}
    assert "hanning" in labels and "expodec" in labels and "kaiser" in labels


def test_completion_axis_names_in_stack(client):
    uri = "file:///tmp/completion3.yml"
    text = STUDY.replace("stack:\n  density:\n    base: [[0, 20], [1, 4]]\n    range: 5\n    seed: 7\n",
                         "stack:\n  \n")
    client.open(uri, text)
    line = text.split("\n").index("stack:") + 1
    result = client.request("textDocument/completion", {
        "textDocument": {"uri": uri},
        "position": {"line": line, "character": 2},
    })
    items = result["items"] if isinstance(result, dict) else result
    labels = {i["label"] for i in items}
    assert "density" in labels and "grain_duration" in labels
    assert "unit" in labels and "seed" in labels


def test_hover_on_key(client):
    client.open(URI, STUDY)
    lines = STUDY.split("\n")
    line = lines.index("stack:") + 1  # "  density:" nel blocco stack
    result = client.request("textDocument/hover", {
        "textDocument": {"uri": URI},
        "position": {"line": line, "character": 3},
    })
    assert result is not None
    value = result["contents"]["value"]
    assert "density" in value
    assert "camminata" in value.lower() or "X" in value


def test_hover_unit_conversion_on_walk_value(client):
    client.open(URI, STUDY)
    lines = STUDY.split("\n")
    line = next(i for i, l in enumerate(lines) if "range: 5" in l and i > lines.index("stack:"))
    col = lines[line].index("5")
    result = client.request("textDocument/hover", {
        "textDocument": {"uri": URI},
        "position": {"line": line, "character": col},
    })
    assert result is not None
    assert "hz" in result["contents"]["value"]


def test_document_symbols(client):
    client.open(URI, STUDY)
    syms = client.request("textDocument/documentSymbol",
                          {"textDocument": {"uri": URI}})
    names = {s["name"] for s in syms}
    assert {"base", "axes", "stack", "streams"} <= names
    axes = next(s for s in syms if s["name"] == "axes")
    assert {c["name"] for c in axes["children"]} == {"density", "grain_duration"}


def test_semantic_tokens(client):
    client.open(URI, STUDY)
    toks = client.request("textDocument/semanticTokens/full",
                          {"textDocument": {"uri": URI}})
    assert toks and len(toks["data"]) >= 5 * 10
    assert len(toks["data"]) % 5 == 0


def test_code_lens_counts(client):
    client.open(URI, STUDY)
    lenses = client.request("textDocument/codeLens",
                            {"textDocument": {"uri": URI}})
    titles = [l["command"]["title"] for l in lenses]
    assert any("spread: genera 4 stream" in t for t in titles)
    assert any("camminata-X in hz" in t for t in titles)


def test_inlay_hints_walk_conversion(client):
    client.open(URI, STUDY)
    hints = client.request("textDocument/inlayHint", {
        "textDocument": {"uri": URI},
        "range": {"start": {"line": 0, "character": 0},
                  "end": {"line": 60, "character": 0}},
    })
    labels = [h["label"] for h in hints]
    assert any("banda" in l and "s" in l for l in labels)


def test_references_on_axis(client):
    client.open(URI, STUDY)
    lines = STUDY.split("\n")
    axes_line = lines.index("axes:")
    refs = client.request("textDocument/references", {
        "textDocument": {"uri": URI},
        "position": {"line": axes_line + 1, "character": 3},
        "context": {"includeDeclaration": True},
    })
    # definizione in axes + camminata in stack
    assert len(refs) >= 2
    ref_lines = {r["range"]["start"]["line"] for r in refs}
    assert lines.index("stack:") + 1 in ref_lines


def test_definition_from_stack_to_axis(client):
    client.open(URI, STUDY)
    lines = STUDY.split("\n")
    stack_line = lines.index("stack:") + 1
    loc = client.request("textDocument/definition", {
        "textDocument": {"uri": URI},
        "position": {"line": stack_line, "character": 3},
    })
    assert loc["range"]["start"]["line"] == lines.index("axes:") + 1


# ---------------------------------------------------------------------------
# Code action: i ricalcoli


def _walk_conversion_action(client, uri, text, dst):
    lines = text.split("\n")
    line = lines.index("stack:") + 1
    result = client.request("textDocument/codeAction", {
        "textDocument": {"uri": uri},
        "range": {"start": {"line": line, "character": 0},
                  "end": {"line": line + 3, "character": 0}},
        "context": {"diagnostics": []},
    })
    return next((a for a in result if f"unit: {dst}" in a["title"]), None)


def test_unit_conversion_hz_to_s_recomputes_band(client):
    uri = "file:///tmp/convert.yml"
    client.open(uri, STUDY)
    action = _walk_conversion_action(client, uri, STUDY, "s")
    assert action is not None, "azione di conversione hz->s assente"
    edits = action["edit"]["changes"][uri]
    new_text = apply_edits(STUDY, edits)
    data = yaml.safe_load(new_text)
    walk = data["stack"]["density"]
    assert walk["unit"] == "s"
    # banda hz [20, 25] -> s [0.04, 0.05]; [4, 9] -> [1/9, 0.25]
    base, rng = walk["base"], walk["range"]
    assert base == [[0, pytest.approx(0.04)], [1, pytest.approx(1 / 9, abs=1e-6)]]
    # range scalare + base envelope -> range come rampa [a, b]
    assert base[0][1] + rng[0] == pytest.approx(0.05)
    assert base[1][1] + rng[1] == pytest.approx(0.25)
    # il resto del file e' intatto
    assert data["axes"]["density"]["baseline"] == 20


def test_unit_conversion_hz_to_bpm(client):
    uri = "file:///tmp/convert2.yml"
    client.open(uri, STUDY)
    action = _walk_conversion_action(client, uri, STUDY, "bpm")
    assert action is not None
    new_text = apply_edits(STUDY, action["edit"]["changes"][uri])
    walk = yaml.safe_load(new_text)["stack"]["density"]
    assert walk["unit"] == "bpm"
    assert walk["base"] == [[0, 1200], [1, 240]]
    assert walk["range"] == 300


def test_unit_conversion_roundtrip_s_to_hz(client):
    uri = "file:///tmp/convert3.yml"
    text = STUDY.replace("    base: [[0, 20], [1, 4]]\n    range: 5\n    seed: 7\n",
                         "    unit: s\n    base: 10\n    range: 4\n")
    client.open(uri, text)
    action = _walk_conversion_action(client, uri, text, "hz")
    assert action is not None
    new_text = apply_edits(text, action["edit"]["changes"][uri])
    walk = yaml.safe_load(new_text)["stack"]["density"]
    assert walk["unit"] == "hz"
    # periodi [10, 14] s -> frequenze [1/14, 0.1] hz
    assert walk["base"] == pytest.approx(1 / 14, abs=1e-6)
    assert walk["base"] + walk["range"] == pytest.approx(0.1, abs=1e-6)


def test_duration_rescale_action(client):
    uri = "file:///tmp/rescale.yml"
    text = """study_id: rescale_test
duration: 20
base:
  onset: 0
  duration: 20
  sample: corpus.wav
  volume: [[0, -60], [5, -6], [20, -60]]
  density: [[0, 5], [10, 40], [20, 5]]
axes:
  density:
    path: density
    baseline: 20
    values: [10, 30]
"""
    client.open(uri, text)
    # l'utente cambia la duration top-level 20 -> 30
    changed = text.replace("duration: 20\nbase:", "duration: 30\nbase:")
    client.change(uri, changed, 2)
    lines = changed.split("\n")
    dur_line = lines.index("duration: 30")
    result = client.request("textDocument/codeAction", {
        "textDocument": {"uri": uri},
        "range": {"start": {"line": dur_line, "character": 0},
                  "end": {"line": dur_line, "character": 12}},
        "context": {"diagnostics": []},
    })
    action = next((a for a in result if "riscala" in a["title"].lower()), None)
    assert action is not None, "azione di riscala assente dopo il cambio di duration"
    assert "20s → 30s" in action["title"]
    new_text = apply_edits(changed, action["edit"]["changes"][uri])
    data = yaml.safe_load(new_text)
    # tempi × 1.5, valori Y intatti
    assert data["base"]["volume"] == [[0, -60], [7.5, -6], [30, -60]]
    assert data["base"]["density"] == [[0, 5], [15, 40], [30, 5]]


def test_time_mode_conversion_action(client):
    uri = "file:///tmp/timemode.yml"
    text = """study_id: tm_test
base:
  onset: 0
  duration: 10
  sample: corpus.wav
  volume: [[0, -60], [5, -6], [10, -60]]
axes:
  density:
    path: density
    baseline: 20
    values: [10]
"""
    client.open(uri, text)
    lines = text.split("\n")
    dur_line = next(i for i, l in enumerate(lines) if "duration: 10" in l)
    result = client.request("textDocument/codeAction", {
        "textDocument": {"uri": uri},
        "range": {"start": {"line": dur_line, "character": 0},
                  "end": {"line": dur_line, "character": 5}},
        "context": {"diagnostics": []},
    })
    action = next((a for a in result if "time_mode: normalized" in a["title"]), None)
    assert action is not None
    new_text = apply_edits(text, action["edit"]["changes"][uri])
    data = yaml.safe_load(new_text)
    assert data["base"]["time_mode"] == "normalized"
    assert data["base"]["volume"] == [[0, -60], [0.5, -6], [1, -60]]


def test_quickfix_rename_unknown_key(client):
    uri = "file:///tmp/quickfix.yml"
    text = STUDY.replace("    baseline: 20\n", "    basline: 20\n")
    diags = client.open(uri, text)
    diag = next(d for d in diags if d.get("code") == "unknown-key")
    result = client.request("textDocument/codeAction", {
        "textDocument": {"uri": uri},
        "range": diag["range"],
        "context": {"diagnostics": [diag]},
    })
    fix = next((a for a in result if "baseline" in a["title"]), None)
    assert fix is not None
    new_text = apply_edits(text, fix["edit"]["changes"][uri])
    assert "baseline: 20" in new_text
    assert "basline" not in new_text


def test_quickfix_flatten_rand_wrapper(client):
    uri = "file:///tmp/wrapper.yml"
    text = STUDY.replace(
        "    base: [[0, 20], [1, 4]]\n    range: 5\n    seed: 7\n",
        "    rand: {cps: {base: 5, range: 2}}\n    seed: 7\n",
    )
    diags = client.open(uri, text)
    diag = next(d for d in diags if d.get("code") == "rand-wrapper")
    result = client.request("textDocument/codeAction", {
        "textDocument": {"uri": uri},
        "range": diag["range"],
        "context": {"diagnostics": [diag]},
    })
    fix = next((a for a in result if "piatto" in a["title"]), None)
    assert fix is not None
    new_text = apply_edits(text, fix["edit"]["changes"][uri])
    walk = yaml.safe_load(new_text)["stack"]["density"]
    assert walk == {"base": 5, "range": 2, "seed": 7}


def test_diagnostics_update_on_change(client):
    uri = "file:///tmp/live.yml"
    diags = client.open(uri, STUDY)
    assert diags == []
    broken = STUDY.replace("values: [0, 2, 4, 6]", "values: [0, 2, 4]")
    diags = client.change(uri, broken, 2)
    assert any(d.get("code") == "spread-count" for d in diags)
    diags = client.change(uri, STUDY, 3)
    assert diags == []
