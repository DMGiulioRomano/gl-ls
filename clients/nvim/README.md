# gl-ls per Neovim

1. Installa il server (dal repo gl-ls): `./setup.sh` — crea `.venv/bin/glls`.
2. Copia `glls.lua` in `~/.config/nvim/lua/` e in `init.lua`:

```lua
require("glls")
```

3. Se `glls` non e' nel PATH, modifica `cmd` in `glls.lua` puntando al venv.

## Attivazione: marker, non nome file

Il client si attiva solo sui file yaml la cui **prima riga** e' esattamente:

```yaml
# gl-ls
```

Questo permette di avere piu' language server yaml diversi nello stesso
repository (anche nella stessa directory): ognuno controlla la propria
etichetta e si aggancia solo ai file che la dichiarano, senza conflitti e
senza dover rinominare nulla. Se scrivi un secondo language server yaml,
digli di cercare un'altra etichetta (es. `# altro-ls`) con la stessa logica
di `has_marker()` in `glls.lua`.

Funziona tutto out-of-the-box: diagnostica (`vim.diagnostic`), completamento
(nvim-cmp / omnifunc), hover (`K`), code action (`vim.lsp.buf.code_action`,
dove vivono i ricalcoli hz/s/bpm e il riscala della duration), inlay hint,
semantic tokens, simboli, references.
