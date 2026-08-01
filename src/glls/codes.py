"""I codici diagnostici del corredo, e il contratto che li lega al runtime.

Un codice non e' un dettaglio di formattazione: e' l'identificatore stabile con
cui un consumatore **agisce** su una diagnostica — un editor che spegne una
regola, un test che ne cerca una, un filtro in CI. Per questo vive qui e non
come stringa sparsa nei siti di emissione.

## Il contratto

`granulation-studies` e gl-ls diagnosticano la stessa superficie YAML da due
lati: il runtime al load, l'editor mentre si scrive. Le due diagnostiche
divergono facilmente, e quando divergono l'editor diventa rumore.

La strada scartata e' la **dipendenza diretta**: far importare a gl-ls
`granstudies.diagnostics` toglierebbe la duplicazione, ma il server e' oggi
solo stdlib + pygls — deliberatamente, perche' gira dentro l'editor — e
legherebbe le versioni dei due repo. Il contratto e' piu' leggero e copre il
punto che conta davvero: **il nome con cui la diagnostica si chiama**.

Due categorie, con obblighi diversi:

- **Condivisi** (`SHARED`) — il runtime emette lo stesso codice, con lo stesso
  significato, dalla propria funzione pura. La stringa e' un'API fra i due
  repo: rinominarla da un lato e non dall'altro rompe silenziosamente chi
  filtra. `tests/unit/test_codici.py` la fissa alla lettera, e verifica
  l'accordo con il runtime quando `granstudies` e' importabile.
- **Anticipazioni** (`STATIC_ONLY`) — il runtime alza un errore fatale, senza
  codice, perche' al load un documento sbagliato non ha significato. L'editor
  puo' dire la stessa cosa *prima*, e su queste e' libero: sono nomi suoi.

Se un domani la duplicazione dovesse pesare, il passo successivo naturale non e'
la dipendenza dal runtime intero, ma estrarre i controlli puri in un pacchetto
terzo che entrambi importano. Il contratto sui codici resta valido comunque:
sopravvive a quel cambio senza toccare chi filtra.
"""
from __future__ import annotations

from typing import Dict, FrozenSet

# --- condivisi con granulation-studies ---------------------------------------

#: Un corredo che lo spread non consuma fino in fondo. **Warning**: e'
#: legittimo — si sta ascoltando un sottoinsieme dell'accordo — ma e' anche il
#: sintomo piu' comune di un refuso. Emesso da `granstudies.diagnostics`
#: (`CORREDO_SOTTO_CONSUMATO`) alla generazione, e da gl-ls mentre si scrive.
CORREDO_SOTTO_CONSUMATO = "corredo-sotto-consumato"

#: I codici che i due repo emettono entrambi, con lo stesso significato.
SHARED: FrozenSet[str] = frozenset({CORREDO_SOTTO_CONSUMATO})

# --- anticipazioni di un errore fatale del runtime ---------------------------

#: Una dichiarazione `{list: ...}` malformata, o una politica `cycle` senza
#: corredo, o un corredo dichiarato dove non puo' vivere (`spread.let`).
CORREDO = "corredo"

#: `versions:`/`percorso:` muovono il valore di una manopola, mai il suo tipo
#: ne' la sua politica di `cycle`.
CORREDO_MOSSO = "corredo-mosso"

#: Un generatore nudo dove la lista si legge **per tempo**: va marcato il ruolo
#: con `linear_env:` (Famiglia 1 in posizione di Famiglia 2).
LINEAR_ENV_MIGRAZIONE = "linear-env-migrazione"

#: `linear_env:` dove la lista si legge **per indice** — assi, strategy di
#: `spread.over`, `versions` Forma 1. L'errore simmetrico al precedente.
LINEAR_ENV_RUOLO = "linear-env-ruolo"

#: I codici che gl-ls emette in anticipo su un errore fatale del runtime.
STATIC_ONLY: FrozenSet[str] = frozenset({
    CORREDO,
    CORREDO_MOSSO,
    LINEAR_ENV_MIGRAZIONE,
    LINEAR_ENV_RUOLO,
})

#: Tutti i codici che riguardano il corredo e i due ruoli di una lista.
CORREDO_CODES: FrozenSet[str] = SHARED | STATIC_ONLY

#: Una riga di spiegazione per codice, per un consumatore che voglia mostrarla
#: accanto alla regola (un pannello di impostazioni, un `--explain`).
DESCRIZIONI: Dict[str, str] = {
    CORREDO_SOTTO_CONSUMATO:
        "il corredo ha piu' elementi delle voci che lo spread genera",
    CORREDO:
        "dichiarazione di corredo malformata, o in un blocco che non la ammette",
    CORREDO_MOSSO:
        "'versions:'/'percorso:' cambiano il tipo o la politica di un corredo",
    LINEAR_ENV_MIGRAZIONE:
        "generatore nudo dove la lista si legge per tempo: manca 'linear_env:'",
    LINEAR_ENV_RUOLO:
        "'linear_env:' dove la lista si legge per indice",
}
