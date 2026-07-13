# gl-ls per Pulsar (ex Atom)

1. Installa il server: dal repo gl-ls, `./setup.sh` (crea `.venv/bin/glls`).
2. Installa il package client:

```bash
cd clients/pulsar
npm install
pulsar --package link .     # oppure: ppm link .
```

3. In Settings → Packages → `glls-client` imposta **serverPath** al `glls`
   del venv (o lascialo se e' nel PATH).

Il client parte solo sui file `study.yml` (grammar YAML). Diagnostica via
linter, completamento via autocomplete-plus, hover via datatip, outline,
definizioni e references via i package `atom-ide-*` / `pulsar-ide-*`.
Per l'esperienza completa: `pulsar -p install atom-ide-ui` (o i singoli
`linter`, `atom-ide-datatip`, `atom-ide-outline`).
