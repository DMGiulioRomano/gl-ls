# gl-ls per VS Code

Client LSP per i file yaml di granulation-studies che dichiarano il server nel
contenuto (vedi sotto), non nel nome file.

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

Se `glls` e' nel `PATH` non serve nulla. L'estensione si attiva sui file yaml
la cui **prima riga** e' esattamente:

```yaml
# gl-ls
```

Questo permette di avere piu' language server yaml nello stesso repository
(anche nella stessa directory): ognuno riconosce solo i file con la propria
etichetta.

## Sviluppo rapido (senza .vsix)

Apri `clients/vscode` in VS Code e premi F5 (Run Extension): parte una finestra
Extension Development Host con il client attivo.
