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
  (density [0.01, 4000], volume [-120, 24], ...), compreso il floor di
  `grain.duration` a **4 campioni** — vincolo di studio, non dell'engine, e il
  messaggio lo dice invece di lasciar cercare il limite dove non c'e';
- **grafie di registry** scambiate per chiavi YAML (`num_voices` invece di
  `voices.num_voices`, `pointer.deviation` invece di `pointer.offset_range`):
  l'unico errore di questa famiglia che a runtime resta muto — l'override
  atterra dove l'engine non guarda e il parametro resta al default;
- **slot strutturali**: `baseline` e gli elementi di `values` vogliono numeri —
  un nodo-expr, una stringa o una lista li' e' errore (a differenza di
  `base`/`range` di una banda, che sono Env e un `expr:` lo accettano);
- unit della camminata (`hz | s | bpm`), chiavi non ammesse nel walk,
  migrazione dei wrapper deprecati `rand:`/`cps:` (con quick fix);
- coerenza dei conteggi in `spread` (n dichiarato vs posseduti); con **`n` come
  envelope** il conteggio e' il picco di `n(t)`, e i conflitti col gate che il
  runtime genera su `base.volume` (`over.base.volume` dichiarato, volume gia'
  envelope) sono errore;
- **nodi-expr valutati davvero** (stessa grammatica del runtime): nomi ignoti,
  Env⊙Env, divisione per zero, `i`/`n` riservati in spread;
- **manopole `let:`** a tre livelli (documento / gruppo `streams.*` / voce
  `spread.let`): ombreggiamento fra i livelli vietato, manopola non
  referenziata da nessuna espressione, `values`/`ramp` in `spread.let`, nomi in
  scope delle expr risolti anche sulle manopole; collisione fra `spread.let` e
  le variabili di `versions:`;
- **forma compatta a cicli** (`[pattern, 1, n_reps, ...]`, il ventaglio
  asimmetrico ripetuto), ovunque il runtime la espanda: valore di `let:`, ma
  anche `base`/`range` di banda e camminata e `drift.step`. `end_time` diverso
  da 1 — che a runtime finisce in hold silenzioso — e punti del pattern a 3
  elementi sono errore (`type` e' globale), `x%` fuori da [0, 100] e' un
  warning;
- **BP group** (`[points, interp]`, la macrozona con interpolazione propria,
  PGE #64), in forma diretta e dentro un envelope misto: `interp` fuori da
  linear/cubic/step, gruppo con meno di 2 punti (nessun segmento interno),
  annidamento con la forma compatta — e i bounds sui punti del gruppo, che
  prima non venivano mai guardati. I suoi tempi sono **assoluti**, quindi i
  controlli sui breakpoint nudi e sulle `x%` del pattern non gli si applicano;
  se il primo punto non supera il bordo della zona precedente, l'engine trasla
  di `DISCONTINUITY_OFFSET` in silenzio e gl-ls avvisa;
- **`versions:` ad assi ortogonali**: discriminatore Forma 1 (manopole
  co-varianti) / Forma 2 (stati nominati) e segnalazione degli assi misti;
- guardia anti-runaway: stima dei breakpoint della camminata-X (> 10000 = errore
  a runtime);
- **superficie PGE v7-v9**: `pointer.loop_unit` non eredita piu' da
  `time_mode` (engine #222), quindi una posizione nel sample lasciata senza
  unita' sotto `time_mode: normalized` e' un **warning con codice condiviso col
  runtime** (`loop-unit-implicito`) e due quick fix — `normalized` per la
  lettura di prima, `seconds` per confermare i secondi; il vocabolario di
  `loop_unit` e' chiuso (`seconds` | `absolute` | `normalized`) e la chiave
  scritta-e-vuota non e' piu' «eredita», e' un errore;
- **`grain.read_direction`** (PGE #207): dominio `{-1, +1}` — un insieme, non
  l'intervallo fra i due — `step` come unica interpolazione dichiarabile
  (dict, per-punto o BP group), e la coppia con `grain.reverse` che l'engine
  rifiuta invece di risolvere per priorita';
- **`deviation_probability`**: `dephase` e' morta (PGE #204 rinomina senza
  alias, quick fix di rinomina), la chiave **scritta e lasciata vuota** e'
  jitter implicito all'1% e non «assente», e da PGE v8 un corpo che non si
  costruisce come envelope e' errore invece di ricadere su un gate al 100%;
- blocco pitch unit-driven, finestre sconosciute, `reverse: true`,
  `loop_end <= loop_start`, `curve` con `type: step`, tempi di banda fuori [0,1]...

**Completamento contestuale** — chiavi per contesto (root, asse, sweep, stack,
walk, spread, superficie engine dentro `base:`), valori enum (finestre,
interpolation, unit, mode...), nomi d'asse dentro `stack:` e `orderings`,
path engine per `path:`, path puntati per `spread.over`, file audio per
`sample:`, snippet (nuovo asse, camminata, entry-spread, manopola a cicli).
Funziona anche a documento sintatticamente rotto (inferenza dall'indentazione).

**Hover** — documentazione di ogni chiave del DSL; bounds/default/unita' dei
parametri engine; **zona percettiva della density** (ritmo / flutter / banda
audio, dal continuum di Truax); conversioni hz/s/bpm sui valori della
camminata; riepilogo dell'asse (generatore, n, strategy-X, unit risolta);
legenda dei posizionali di una manopola in forma compatta a cicli.

**Ricalcoli (code action)** — il cuore:

- **converti la camminata-X tra `hz`/`s`/`bpm` ricalcolando `base`/`range`**:
  il passaggio rate↔periodo inverte i bordi della banda
  (`[20, 25] hz` → `[0.04, 0.05] s`), gli envelope si convertono breakpoint
  per breakpoint sull'unione dei tempi;
- **cambia una `duration` e riscala i breakpoint assoluti**: il server ricorda
  il valore precedente di ogni durata dichiarata — `base.duration` e quella
  propria di ogni stream; dopo la modifica offre "riscala 20s → 30s (×1.5)"
  sugli envelope a tempi assoluti che vivono **su quella** durata (i
  `normalized` si riscalano da soli), compreso l'`end_time` dei formati
  compatti. `base.duration` e' un default, quindi tocca il documento e gli
  stream che non ne dichiarano una propria; la `duration:` di una entry tocca
  lei sola;
- **converti `time_mode` absolute ↔ normalized** ricalcolando i tempi;
- quick fix: rinomina chiave/valore, rimuovi generatore in piu', aggiungi
  `n`/`baseline`/`base.duration`/`pointer.loop_unit`, **sposta la `duration:`
  top-level** dove ora vive (`base.duration` o `versions.duration`),
  appiattisci `rand:`/`cps:`, `sweep.combine`.

**E ancora**: semantic tokens (sezioni, nomi d'asse, marcatori di banda, enum,
espressioni expr tokenizzate); outline del documento; **inlay hint** con la
banda convertita nell'altra unita', il **duty factor** (`density ×
grain.duration`) e il riassunto di una forma compatta (`4 cicli · vertice 25% ·
wrap`); legenda dei posizionali di un BP group (`3 punti · cubic · t 0–1
(assoluti)`) con snippet per scriverlo; **code lens** con le varianti sweep per
ordine, la durata
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
