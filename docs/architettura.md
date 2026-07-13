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
- **Memoria delle duration**: al parse il server confronta `duration` e
  `base.duration` con l'ultimo valore visto; una differenza arma la code
  action "riscala vecchio -> nuovo" finche' non si torna al valore di
  partenza. Nessun protocollo extra, funziona con qualsiasi client.
- **Conversione unit**: preserva la *banda* punto per punto (bordi invertiti
  nel passaggio rate<->periodo, unione dei tempi per envelope disallineati) e
  rifiuta esplicitamente le forme non statiche (nodi generatore, expr,
  `type: step`, `curve`): meglio nessuna azione che un ricalcolo sbagliato.
- **expr valutate davvero** in diagnostica, con la stessa grammatica
  whitelist del runtime (`exprlang` e' un port di `granstudies.expr`): il
  messaggio d'errore nell'editor coincide con quello di `make stack`.

## Limiti noti

- La conversione unit non tratta i nodi generatore annidati dentro
  `base`/`range` (rifiutata con `ConversionError`, l'azione non compare).
- Il riscala della duration tocca gli envelope in forma lista e dict
  (`points`, con `time_mode` locale rispettato) e l'`end_time` dei compatti;
  non i `values` di spread (semantica ambigua).
- I bounds dinamici dell'engine (`loop_* <= sample_dur`) non sono verificati
  (servirebbe leggere il file audio).

## Estendere

- **Nuova unita' X**: una entry in `engine_info.X_UNITS` + le lambda in
  `convert._TO_HZ`/`_FROM_HZ` + test in `test_convert.py`.
- **Nuova regola di diagnostica**: una funzione in `diagnostics.py` che
  aggiunge al `Bag`, con `code` stabile; se ha un fix, `data={"fix": ...}` e
  il ramo corrispondente in `actions.quickfixes`.
- **Nuova chiave del DSL**: una `Key` nel contesto giusto di `schema.py`
  (doc markdown inclusa): completion e hover la vedono da sole.
