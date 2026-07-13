# Client editor per gl-ls

gl-ls parla LSP standard su stdio: qualunque editor con un client LSP lo puo'
usare. Client pronti:

- [`vscode/`](vscode/) — estensione VS Code (vsix)
- [`nvim/`](nvim/) — Neovim (`vim.lsp`, con e senza nvim-lspconfig)
- [`pulsar/`](pulsar/) — Pulsar/Atom (atom-languageclient)

Prerequisito comune: il server installato (`./setup.sh` nella radice del repo
crea `.venv/bin/glls`).

## Altri editor

### Helix

`~/.config/helix/languages.toml`:

```toml
[language-server.glls]
command = "glls"

[[language]]
name = "yaml"
language-servers = ["glls", "yaml-language-server"]
```

### Emacs (eglot)

```elisp
(add-to-list 'eglot-server-programs
             '(yaml-mode . ("glls")))
```

### Sublime Text (package LSP)

`LSP.sublime-settings`:

```json
{
  "clients": {
    "glls": {
      "enabled": true,
      "command": ["glls"],
      "selector": "source.yaml",
      "file_watcher": {"patterns": ["**/study.yml"]}
    }
  }
}
```

### Kate

Settings → LSP Client → User Server Settings:

```json
{
  "servers": {
    "yaml": {"command": ["glls"], "highlightingModeRegex": "^YAML$"}
  }
}
```

### Debug senza editor

```bash
glls --tcp --port 8791     # ascolta su TCP
glls --version
```
