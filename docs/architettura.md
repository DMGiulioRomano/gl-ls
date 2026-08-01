# Architettura di gl-ls

## Problema

Il linguaggio degli `study.yml` e' denso di invarianti non locali
(*n-ownership* tra Y e camminata-X, conteggi di spread, bounds engine, unita'
della banda) che oggi emergono solo lanciando `make sweep`/`make stack`. E i
numeri del file vivono in spazi diversi (rate vs periodo, tempi assoluti vs
normalizzati): cambiare `unit` o `duration` significa ricalcolare a mano.

## Modello

Tre strati, tutti puri e testabili senza LSP:

1. **Parsing posizionale** (`yamlpos`): `yaml.safe_load` per i dati +
   `yaml.compose` per gli span di chiavi e valori, indicizzati per key-path
   (`("stack", "density", "base") -> Span`). Tollerante: su errore di
   sintassi il documento porta la diagnostica e le feature testuali
   (completion) restano vive.
2. **Modello semantico** (`model`, `schema`, `engine_info`): la vista del
   linguaggio (assi con generatore e n, camminate con unit risolta per
   precedenza, spread con conteggio) e lo schema dichiarativo dei contesti
   (chiavi ammesse, doc, enum). Gli override di stream si mappano sugli
   stessi contesti del top-level (simmetria del deep-merge).
3. **Feature LSP** (diagnostics, completion, hover, actions, ...): funzioni
   `Document x StudyModel -> tipi lsprotocol`, senza stato proprio. Lo stato
   di sessione (memoria delle duration per la code action di riscala) vive
   nel `GllsServer`.

## Decisioni

- **Standalone**: gl-ls non importa granstudies/PGE. Replica la superficie
  osservabile (bounds, enum, regole di parse, grammatica expr) come snapshot
  dichiarativo. Costo: va tenuto allineato; beneficio: il server si installa
  ovunque senza l'engine, e non esegue codice del progetto aperto.
- **Ricalcoli come code action con TextEdit**, non come comandi custom: cosi'
  funzionano in ogni client senza supporto speciale (`workspace/applyEdit`
  non serve, l'edit viaggia nella risposta).
- **Memoria delle duration**: al parse il server confronta ogni durata
  dichiarata — `base.duration` e quella propria di ogni entry di `streams:` —
  con l'ultimo valore visto; una differenza arma la code action "riscala
  vecchio -> nuovo" finche' non si torna al valore di partenza. Nessun
  protocollo extra, funziona con qualsiasi client. La chiave della memoria e'
  un **key-path**, non una stringa: le durate per-stream vivono sotto un nome
  libero che puo' contenere punti, e una stringa andrebbe riparsata. La
  `duration:` top-level non si segue: e' vietata, e ha gia' due quick fix che
  la spostano.
- **La riscala ha uno scope**, non solo un fattore: `_roots_inheriting` e' la
  catena di `duration_for` letta al contrario — non "da dove viene la durata di
  questo stream" ma "di chi e' la durata che ho in mano". `base.duration` e' un
  *default*, quindi vale per il documento e per gli stream che non ne
  dichiarano una propria; la `duration:` di una entry vale per lei sola.
  Riscalare tutti i blocchi `base:` era corretto finche' la durata era una
  sola, e con la durata per-stream sposta breakpoint di stream la cui timeline
  non e' cambiata.
- **Lo stato del processo si legge per stream, non per documento**: il runtime
  valida il documento *merged* di ogni entry di `streams:`, dove il blocco
  `stack:` (o `duration:`) dell'override e' diventato top-level. Le domande
  "c'e' lo stack?" e "questo asse ha una camminata?" hanno quindi una risposta
  per stream — `StreamInfo.declares_stack`/`stack_paths`/`stack_nulled` e
  `StudyModel.walk_in_stream` — e le tre risposte possibili (dichiarata,
  ereditata, annullata con `asse: null`) sono tutte e tre diverse. Leggerle sul
  documento base costava un falso positivo e due falsi negativi.
- **La durata e' per-stream** (granstudies #42): non esiste una durata di
  documento dichiarata — quella e' dedotta, `max(onset + duration)`. Il
  modello espone una catena (`StudyModel.duration_for(stream)`: `duration:` di
  entry > `base.duration` > durata di replica di `versions:`/`percorso:`)
  invece di un campo, e ogni stima che dipende da una durata (anti-runaway
  della camminata, code lens dei breakpoint, inlay dei tempi normalizzati)
  passa da li'. Un campo unico li aveva fatti morire in silenzio quando il
  top-level e' stato vietato.
- **Conversione unit**: preserva la *banda* punto per punto (bordi invertiti
  nel passaggio rate<->periodo, unione dei tempi per envelope disallineati) e
  rifiuta esplicitamente le forme non statiche (nodi generatore, expr,
  `type: step`, `curve`): meglio nessuna azione che un ricalcolo sbagliato.
- **expr valutate davvero** in diagnostica, con la stessa grammatica
  whitelist del runtime (`exprlang` e' un port di `granstudies.expr`): il
  messaggio d'errore nell'editor coincide con quello di `make stack`.
- **Contratto sui codici, non dipendenza dal runtime** (`codes.py`).
  `granulation-studies` espone i propri controlli non fatali come funzioni pure
  con codici stabili, e importarli toglierebbe la duplicazione — ma il server
  e' solo stdlib + pygls di proposito, perche' gira dentro l'editor, e
  dipenderne legherebbe le versioni dei due repo. Si condivide invece la cosa
  su cui un consumatore **agisce**: il nome della regola. I codici condivisi
  stanno in `codes.SHARED`, fissati alla lettera da `test_codici.py`, che
  quando `granstudies` e' importabile verifica anche l'accordo con il runtime e
  segnala i codici nuovi non ancora dichiarati. In CI quella verifica si salta:
  e' precisamente il punto: la dipendenza non c'e'.

## Limiti noti

- La conversione unit non tratta i nodi generatore annidati dentro
  `base`/`range` (rifiutata con `ConversionError`, l'azione non compare).
- Il riscala della duration tocca gli envelope in forma lista e dict
  (`points`, con `time_mode` locale rispettato) e l'`end_time` dei compatti;
  non i `values` di spread (semantica ambigua).
- I bounds dinamici dell'engine (`loop_* <= sample_dur`) non sono verificati
  (servirebbe leggere il file audio). Da PGE v5.1.0 `pge.api.parameter_bounds()`
  li espone gia' risolti: chiuderebbe il drift della tabella di `engine_info`,
  al prezzo della scelta standalone.
- La superficie posizionale degli envelope engine (forma compatta a cicli, BP
  group `[points, interp]`) si valida per *forma*, non per grammatica: i
  predicati sono quelli ufficiali della disambiguazione — cornice a 3-6
  elementi con `end_time` numero e `n_reps` intero per la compatta, 2 elementi
  con lista di punti e stringa per il gruppo — e una forma che non ricade in
  nessuno dei due passa senza diagnostica invece di essere indovinata.

## Estendere

- **Nuova unita' X**: una entry in `engine_info.X_UNITS` + le lambda in
  `convert._TO_HZ`/`_FROM_HZ` + test in `test_convert.py`.
- **Nuova regola di diagnostica**: una funzione in `diagnostics.py` che
  aggiunge al `Bag`, con `code` stabile; se ha un fix, `data={"fix": ...}` e
  il ramo corrispondente in `actions.quickfixes`. Se il runtime emette la
  stessa regola, il codice va in `codes.SHARED` con la stessa stringa; se la
  anticipa e basta, in `codes.STATIC_ONLY`, dove il nome e' libero.
- **Nuova chiave del DSL**: una `Key` nel contesto giusto di `schema.py`
  (doc markdown inclusa): completion e hover la vedono da sole.
