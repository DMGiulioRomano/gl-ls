# gl-ls per Neovim

1. Installa il server (dal repo gl-ls): `./setup.sh` — crea `.venv/bin/glls`.
2. Copia `glls.lua` in `~/.config/nvim/lua/` e in `init.lua`:

```lua
require("glls")
```

3. Se `glls` non e' nel PATH, modifica `cmd` in `glls.lua` puntando al venv.

Con **nvim-lspconfig** puoi in alternativa registrare una config custom:

```lua
require("lspconfig.configs").glls = {
  default_config = {
    cmd = { "glls" },
    filetypes = { "yaml" },
    root_dir = require("lspconfig.util").root_pattern("study.yml", ".git"),
  },
}
require("lspconfig").glls.setup({})
```

Funziona tutto out-of-the-box: diagnostica (`vim.diagnostic`), completamento
(nvim-cmp / omnifunc), hover (`K`), code action (`vim.lsp.buf.code_action`,
dove vivono i ricalcoli hz/s/bpm e il riscala della duration), inlay hint,
semantic tokens, simboli, references.
