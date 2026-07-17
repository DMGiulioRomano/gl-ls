#!/usr/bin/env bash
# Installa il client VS Code di gl-ls: pacchettizza l'estensione e la
# installa nell'editor locale. Rilanciabile in sicurezza (npm install e
# code --install-extension sono idempotenti).
set -euo pipefail
cd "$(dirname "$0")"

REPO_DIR="$(cd .. && cd .. && pwd)"
GLLS_BIN="$REPO_DIR/.venv/bin/glls"

if [ ! -x "$GLLS_BIN" ]; then
    echo "==> $GLLS_BIN non esiste: installo il server con setup.sh"
    (cd "$REPO_DIR" && ./setup.sh)
fi

if ! command -v code >/dev/null 2>&1; then
    echo "ERRORE: comando 'code' non trovato nel PATH." >&2
    echo "In VS Code: Cmd+Shift+P -> 'Shell Command: Install code command in PATH'." >&2
    exit 1
fi

echo "==> installo le dipendenze dell'estensione"
npm install

echo "==> pacchettizzo l'estensione (.vsix)"
npx @vscode/vsce package

VSIX="$(ls -t gl-ls-vscode-*.vsix | head -1)"
echo "==> installo $VSIX in VS Code"
code --install-extension "$VSIX"

echo
echo "Fatto. Imposta glls.serverPath in settings.json se 'glls' non e' nel PATH:"
echo "  \"glls.serverPath\": \"$GLLS_BIN\""
echo
echo "Poi apri un file yaml con \"# gl-ls\" come prima riga per testare:"
echo "  code \"$REPO_DIR/ci/fixtures/study.yml\""
