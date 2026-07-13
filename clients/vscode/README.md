# gl-ls per VS Code

Client LSP per gli `study.yml` di granulation-studies.

## Installazione dal sorgente

```bash
cd clients/vscode
npm install
npm run package          # produce gl-ls-vscode-0.1.0.vsix
code --install-extension gl-ls-vscode-0.1.0.vsix
```

## Configurazione

Il server va installato una volta (vedi README in radice: `./setup.sh` crea il
venv). Poi in `settings.json`:

```json
{
  "glls.serverPath": "/percorso/a/gl-ls/.venv/bin/glls"
}
```

Se `glls` e' nel `PATH` non serve nulla. L'estensione si attiva sui file che
combaciano con `glls.filePattern` (default `**/study.yml`).

## Sviluppo rapido (senza .vsix)

Apri `clients/vscode` in VS Code e premi F5 (Run Extension): parte una finestra
Extension Development Host con il client attivo.
