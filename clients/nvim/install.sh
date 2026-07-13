#!/usr/bin/env bash
# Installa il client Neovim di gl-ls nella config utente. Idempotente:
# rilanciabile senza duplicare nulla, sia su una macchina nuova sia su
# una gia' configurata.
set -euo pipefail
cd "$(dirname "$0")"

REPO_DIR="$(cd .. && cd .. && pwd)"
GLLS_BIN="$REPO_DIR/.venv/bin/glls"
NVIM_CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/nvim"

if [ ! -x "$GLLS_BIN" ]; then
    echo "==> $GLLS_BIN non esiste: installo il server con setup.sh"
    (cd "$REPO_DIR" && ./setup.sh)
fi

echo "==> copio glls.lua in $NVIM_CONFIG/lua/glls.lua"
mkdir -p "$NVIM_CONFIG/lua"
sed "s#local cmd = { \"glls\" }#local cmd = { \"$GLLS_BIN\" }#" glls.lua \
    > "$NVIM_CONFIG/lua/glls.lua"

INIT_LUA="$NVIM_CONFIG/init.lua"
touch "$INIT_LUA"
if ! grep -qF 'require("glls")' "$INIT_LUA"; then
    echo "==> aggiungo require(\"glls\") a $INIT_LUA"
    printf '\nrequire("glls")\n' >> "$INIT_LUA"
else
    echo "==> $INIT_LUA carica gia' glls, nessuna modifica"
fi

echo
echo "Fatto. Apri un file yaml con \"# gl-ls\" come prima riga per testare:"
echo "  nvim \"$REPO_DIR/ci/fixtures/study.yml\""
