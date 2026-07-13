#!/usr/bin/env bash
# Bootstrap di gl-ls: venv + installazione editable. Idempotente.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

if [ ! -d .venv ]; then
    echo "==> creo il venv (.venv)"
    "$PYTHON" -m venv .venv
fi

echo "==> installo gl-ls nel venv"
.venv/bin/pip install --upgrade pip >/dev/null
.venv/bin/pip install -e ".[dev]"

echo
echo "Fatto. Il server e': $(pwd)/.venv/bin/glls"
echo "Prova: .venv/bin/glls --version"
echo "Test:  make tests"
