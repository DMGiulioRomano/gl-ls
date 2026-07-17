#!/usr/bin/env bash
# Installa il client Pulsar di gl-ls: link del package nel profilo utente.
# Rilanciabile in sicurezza (ppm link -f sostituisce il link esistente).
set -euo pipefail
cd "$(dirname "$0")"

REPO_DIR="$(cd .. && cd .. && pwd)"
GLLS_BIN="$REPO_DIR/.venv/bin/glls"

if [ ! -x "$GLLS_BIN" ]; then
    echo "==> $GLLS_BIN non esiste: installo il server con setup.sh"
    (cd "$REPO_DIR" && ./setup.sh)
fi

if ! command -v ppm >/dev/null 2>&1; then
    echo "ERRORE: comando 'ppm' non trovato nel PATH (viene con Pulsar)." >&2
    exit 1
fi

echo "==> installo le dipendenze del package"
npm install

echo "==> collego il package a Pulsar"
ppm link -f .

echo
echo "Fatto. Imposta glls-client.serverPath se 'glls' non e' nel PATH"
echo "(Settings -> Packages -> glls-client):"
echo "  $GLLS_BIN"
echo
echo "Poi apri un file yaml con \"# gl-ls\" come prima riga per testare:"
echo "  pulsar \"$REPO_DIR/ci/fixtures/study.yml\""
