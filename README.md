# gl-ls — Granulation Language Server

Language server (LSP) per il **linguaggio di granulazione** degli
`study.yml` di [granulation-studies], che incapsulano la superficie YAML del
[PythonGranularEngine]. Parla LSP standard su stdio: funziona identico in
**VS Code, Neovim, Pulsar**, Helix, Emacs, Sublime, Kate (vedi
[`clients/`](clients/README.md)).

[granulation-studies]: https://github.com/DMGiulioRomano/granulation-studies
[PythonGranularEngine]: https://github.com/DMGiulioRomano/PythonGranularEngine

## Cosa fa

**Diagnostica in tempo reale** — le stesse regole del runtime, mentre scrivi:

- errori di sintassi YAML con posizione; chiavi duplicate;
- chiavi sconosciute con suggerimento ("Forse intendevi `values`?") e quick fix;
- generatori Y mutuamente esclusivi (`values` | `ramp` | banda);
- **n-ownership** nelle due direzioni (banda senza `n` senza camminata-X;
  camminata-X con Y che enumera);
- bounds engine su `baseline`, `values` e sugli envelope di `base.*`
  (density [0.01, 4000], volume [-120, 12], ...);
- unit della camminata (`hz | s | bpm`), chiavi non ammesse nel walk,
  migrazione dei wrapper deprecati `rand:`/`cps:` (con quick fix);
- coerenza dei conteggi in `spread` (n dichiarato vs posseduti);
- **nodi-expr valutati davvero** (stessa grammatica del runtime): nomi ignoti,
  Env⊙Env, divisione per zero, `i`/`n` riservati in spread;
- guardia anti-runaway: stima dei breakpoint della camminata-X (> 10000 = errore
  a runtime);
- blocco pitch unit-driven, finestre sconosciute, `reverse: true`,
  `loop_end <= loop_start`, `curve` con `type: step`, tempi di banda fuori [0,1]...

**Completamento contestuale** — chiavi per contesto (root, asse, sweep, stack,
walk, spread, superficie engine dentro `base:`), valori enum (finestre,
interpolation, unit, mode...), nomi d'asse dentro `stack:` e `orderings`,
path engine per `path:`, path puntati per `spread.over`, file audio per
`sample:`, snippet (nuovo asse, camminata, entry-spread). Funziona anche a
documento sintatticamente rotto (inferenza dall'indentazione).

**Hover** — documentazione di ogni chiave del DSL; bounds/default/unita' dei
parametri engine; **zona percettiva della density** (ritmo / flutter / banda
audio, dal continuum di Truax); conversioni hz/s/bpm sui valori della
camminata; riepilogo dell'asse (generatore, n, strategy-X, unit risolta).

**Ricalcoli (code action)** — il cuore:

- **converti la camminata-X tra `hz`/`s`/`bpm` ricalcolando `base`/`range`**:
  il passaggio rate↔periodo inverte i bordi della banda
  (`[20, 25] hz` → `[0.04, 0.05] s`), gli envelope si convertono breakpoint
  per breakpoint sull'unione dei tempi;
- **cambia `duration` e riscala i breakpoint assoluti**: il server ricorda il
  valore precedente; dopo la modifica offre "riscala 20s → 30s (×1.5)" su
  tutti gli envelope a tempi assoluti di `base.*` (i `normalized` si riscalano
  da soli), compreso l'`end_time` dei formati compatti;
- **converti `time_mode` absolute ↔ normalized** ricalcolando i tempi;
- quick fix: rinomina chiave/valore, rimuovi generatore in piu', aggiungi
  `n`/`baseline`/`duration`, appiattisci `rand:`/`cps:`, `sweep.combine`.

**E ancora**: semantic tokens (sezioni, nomi d'asse, marcatori di banda, enum,
espressioni expr tokenizzate); outline del documento; **inlay hint** con la
banda convertita nell'altra unita' e il **duty factor** (`density ×
grain.duration`); **code lens** con le varianti sweep per ordine, la durata
stimata, i breakpoint stimati d'ogni camminata e gli stream generati da ogni
spread; go-to-definition/references sui nomi d'asse; link ai sample.

## Installazione

```bash
./setup.sh          # crea .venv e installa gl-ls (equivalente: make install)
.venv/bin/glls --version
```

Poi collega l'editor: [`clients/README.md`](clients/README.md). Per Neovim
c'e' anche `make install-nvim`, che installa il server e configura
`~/.config/nvim` in automatico.

## Test

```bash
make tests          # unit + e2e
make e2e-tests      # solo end-to-end: client LSP reale su subprocess
```

Gli e2e parlano il protocollo vero (JSON-RPC, framing Content-Length, stdio)
con il server in subprocess e applicano davvero i TextEdit delle code action,
verificando i numeri ricalcolati.

## Architettura

```
src/glls/
├── yamlpos.py      # parse YAML posizionale tollerante (span, duplicati)
├── model.py        # modello semantico (assi, camminate, spread, unit)
├── schema.py       # schema dichiarativo del DSL (contesti, doc, enum)
├── engine_info.py  # superficie engine PGE (bounds, finestre, unita')
├── exprlang.py     # valutatore del nodo-expr (allineato a granstudies)
├── convert.py      # conversioni hz/s/bpm e riscala tempi (pure, testate)
├── diagnostics.py  # le regole del runtime come diagnostiche LSP
├── completion.py   # inferenza contesto da indentazione + schema
├── hover.py · semtokens.py · symbols.py · inlay.py · lens.py
├── actions.py      # code action di ricalcolo e quick fix
├── navigation.py   # definition/references assi, link ai sample
└── server.py       # wiring pygls
```

Dettagli e decisioni: [`docs/architettura.md`](docs/architettura.md).

gl-ls e' **standalone**: non importa granstudies ne' l'engine; replica la loro
superficie osservabile (documentata in `docs/study-yml-reference.md` e
`docs/reference/yaml.md` dei rispettivi repo). Quando quella superficie cambia,
va aggiornato lo snapshot in `engine_info.py`/`schema.py`.
