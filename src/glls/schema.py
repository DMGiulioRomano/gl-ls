"""Schema dichiarativo di ``study.yml``: contesti, chiavi, doc, enum, snippet.

Ogni posizione del documento appartiene a un *contesto* (root, axis, walk,
sweep, ...); ogni contesto elenca le chiavi ammesse con la documentazione
markdown mostrata in hover/completion. ``context_for_path`` mappa un key-path
concreto al contesto, gestendo la simmetria degli override di stream (che
rispecchiano il documento top-level) e la ricorsione dei generatori annidati
negli Env.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import engine_info as EI

KeyPath = Tuple[object, ...]


@dataclass(frozen=True)
class Key:
    name: str
    doc: str
    values: Optional[List[str]] = None      # enum per il completamento del valore
    snippet: Optional[str] = None           # insertText (formato snippet LSP)
    kind: str = "property"                  # semantic token / completion kind


def _k(name: str, doc: str, **kw) -> Key:
    return Key(name=name, doc=doc, **kw)


# ---------------------------------------------------------------------------
# Vocabolario condiviso dei generatori/Env (riusato in piu' contesti).

_GEN_DOC = {
    "values": "**Generatore Y — lista esplicita.** I valori cosi' come sono "
              "(rimpiazza, non concatena). Possiede `n` (= len).",
    "ramp": "**Generatore Y — rampa aritmetica** `{start, stop, step}`. "
            "`step > 0` (la direzione si deduce da start/stop); `step` e' un "
            "Env: con step mobile la rampa accelera o ritarda.",
    "base": "**Banda — estremo inferiore** di `[base, base+range]`. La presenza "
            "di `base` marca il generatore-banda. E' un **Env**: scalare · "
            "`[a, b]` · `[[t, v], ...]` (t in [0,1]) · `{type, points, curve}` "
            "· nodo generatore annidato · nodo-expr `{expr, let}`.",
    "range": "**Banda — ampiezza** (default 0 = banda collassata: la sequenza "
             "segue `base` deterministicamente). Env come `base`; un valore "
             "negativo in un punto della sequenza e' errore.",
    "n": "**Quanti valori** pescare nella banda (>= 1). Ricorda la "
         "*n-ownership*: con la camminata-X in `stack:` la X possiede `n` e "
         "la banda va dichiarata **senza** `n`.",
    "seed": "Seed della banda (riproducibilita'). Default: `axes.seed` globale, "
            "poi auto-derivazione stabile per-stream (decorrelazione gratuita).",
    "distribution": "Come si pesca dentro la banda: `uniform` (default, "
                    "equiprobabile) | `gaussian` (media al centro banda, "
                    "sigma = larghezza/6, clamp ai bordi).",
    "drift": "Pescaggio **correlato** (random walk): `precedente + passo` "
             "invece di estrazioni indipendenti. `{step, seed?}`; `step` e' "
             "frazione della banda corrente, Env. Riflessione ai bordi.",
    "expr": "**Nodo-expr**: Env calcolato da un'espressione aritmetica su "
            "sagome e scalari. Grammatica: numeri, nomi, `+ - * / **`, meno "
            "unario, parentesi. Env⊙scalare agisce sulle y; Env⊙Env e' "
            "errore. **Sempre tra virgolette.**",
    "let": "Nomi in scope per `expr`: scalari, forme *statiche* di Env, "
           "oppure altri nodi-expr `{expr, let}` (risoluzione lazy alla prima "
           "referenza: l'ordine non conta, un `let` interno ombreggia, i "
           "cicli sono errore). Niente nodi-generatore.",
    "type": "Interpolazione dei breakpoint dell'Env: `linear` | `step` "
            "(niente cubic nelle bande).",
    "points": "Breakpoint `[[t, v], ...]` con `t` in `[0, 1]`, hold fuori dai bordi.",
    "curve": "Piega non lineare del segmento (`u' = u^k`): 1 = lineare, >1 "
             "parte lento e accelera, <1 parte ripido. Deve essere > 0; con "
             "`type: step` e' errore.",
}

_ENV_KEYS = [
    _k("type", _GEN_DOC["type"], values=["linear", "step"], kind="macro"),
    _k("points", _GEN_DOC["points"], kind="macro"),
    _k("curve", _GEN_DOC["curve"], kind="macro"),
    _k("values", _GEN_DOC["values"], kind="macro"),
    _k("ramp", _GEN_DOC["ramp"], kind="macro",
       snippet="ramp: {start: ${1:5}, stop: ${2:100}, step: ${3:5}}"),
    _k("n", _GEN_DOC["n"], kind="macro"),
    _k("base", _GEN_DOC["base"], kind="macro"),
    _k("range", _GEN_DOC["range"], kind="macro"),
    _k("seed", _GEN_DOC["seed"], kind="macro"),
    _k("distribution", _GEN_DOC["distribution"], values=EI.DISTRIBUTIONS, kind="macro"),
    _k("drift", _GEN_DOC["drift"], kind="macro",
       snippet="drift:\n  step: ${1:0.1}"),
    _k("expr", _GEN_DOC["expr"], kind="macro", snippet='expr: "${1:env * 50}"'),
    _k("let", _GEN_DOC["let"], kind="macro"),
]

_RAMP_KEYS = [
    _k("start", "Primo valore della rampa."),
    _k("stop", "Ultimo valore (incluso se cade sulla griglia, mai oltrepassato). "
               "Omesso in spread: progressione aperta `start + i*step`."),
    _k("step", "Passo (> 0; la direzione la danno start/stop). E' un Env: con "
               "step mobile la rampa accelera (`[10, 1]`) o ritarda (`[1, 10]`); "
               "letto sul progresso in valore, non sull'indice."),
]

_DRIFT_KEYS = [
    _k("step", "Frazione della banda corrente per passo (Env, >= 0; 0 congela). "
               "Il passo reale e' `step(frac) * larghezza_banda(frac)`."),
    _k("seed", "Seed dell'RNG del passo (separato da quello della banda). "
               "Assente: derivato dal seed della banda con salt `:drift`."),
]

# ---------------------------------------------------------------------------
# Superficie engine dentro `base:` (e `streams.*.base:`).

_ENGINE_STREAM_KEYS = [
    _k("onset", "Tempo di inizio assoluto dello stream (s)."),
    _k("duration", "Durata dello stream (s); usata dalle varianti discrete. "
                   "Cambiandola, gl-ls offre il ricalcolo dei breakpoint "
                   "assoluti degli envelope."),
    _k("sample", "File audio sorgente (cercato in `samples_dir`).", kind="string"),
    _k("time_mode", "Unita' dell'asse X degli envelope: `absolute` (secondi, "
                    "default) | `normalized` ([0,1] mappato su duration alla "
                    "generazione).", values=EI.TIME_MODES),
    _k("time_scale", "Fattore di scala temporale globale (default 1.0)."),
    _k("clip_strategy", "Filtro grain out-of-bounds: `overflow_margin` "
                        "(default) | `passthrough`.", values=EI.CLIP_STRATEGIES),
    _k("clip_margin", "Tolleranza in secondi per la coda dei grain (default 0)."),
    _k("density", "Grani al secondo (scalare o envelope). Bounds [0.01, 4000]. "
                  "Mutuamente esclusivo con `fill_factor` (che ha priorita')."),
    _k("fill_factor", "density = fill_factor / grain.duration. Bounds [0.001, 50]."),
    _k("distribution", "Modello Truax: 0 = sincrono, 1 = asincrono; blend lineare. "
                       "Scalare o envelope."),
    _k("volume", "dB (default 0). Bounds [-120, 12]. Scalare o envelope."),
    _k("volume_range", "±dB randomizzazione per grano."),
    _k("pan", "Gradi: 0 centro, ±180 estremi. Bounds [-3600, 3600]."),
    _k("pan_range", "±gradi randomizzazione per grano."),
    _k("grain", "Blocco grano: duration, duration_range, duration_unit, "
                "envelope (finestra), reverse.",
       snippet="grain:\n  duration: ${1:0.05}\n  envelope: ${2:hanning}"),
    _k("pointer", "Posizione di lettura nel sample: start, speed_ratio, "
                  "offset_range, loop_start/loop_end/loop_dur, loop_unit."),
    _k("pitch", "Trasposizione unit-driven: UNA sola chiave-unita' tra "
                "semitones, quarter_tone, eighth_tone, cents, edo(+value), ratio."),
    _k("dephase", "Probabilita' di applicare i `_range` per-grano: false | null "
                  "(1%) | 0-100 | envelope | dict per-parametro."),
    _k("range_always_active", "true: i `_range` sono sempre attivi anche senza dephase."),
    _k("voices", "Multi-voice: num_voices, scatter, pitch, onset_offset, "
                 "pointer, pan (strategy per dimensione)."),
    _k("seed", "Seed per-stream (override del seed globale engine)."),
    _k("solo", "Solo gli stream con questo flag vengono renderizzati."),
    _k("mute", "Stream ignorato (salvo solo mode). In stack e' il gate "
               "d'ascolto: si esclude uno stream mutandolo col volume."),
]

_GRAIN_KEYS = [
    _k("duration", "Durata del grano in secondi (default 0.05) o campioni con "
                   "`duration_unit: samples`. Bounds [1 campione, 10 s]. "
                   "Scalare o envelope."),
    _k("duration_range", "± randomizzazione della durata per grano."),
    _k("duration_unit", "`seconds` (default) | `samples` (campioni a 48 kHz, "
                        "convertiti al parse; duration esplicita obbligatoria).",
       values=EI.DURATION_UNITS),
    _k("envelope", "Finestra del grano: nome, lista (selezione casuale), "
                   "`{from, to, curve}` (morphing) o `{states, curve}` "
                   "(percorso multi-stato).", values=sorted(EI.WINDOWS)),
    _k("reverse", "Chiave **presente vuota** = reverse forzato; assente = auto "
                  "(segue pointer.speed_ratio). `true`/`false` e' errore."),
]

_POINTER_KEYS = [
    _k("start", "Posizione iniziale in secondi (default 0). Scalare o envelope."),
    _k("speed_ratio", "Velocita' di lettura: 1 normale, -1 indietro, 0 fermo, "
                      "2 doppia. Bounds [-100, 100]."),
    _k("offset_range", "Deviazione per-grano in [-x, +x], scalata e confinata "
                       "alla finestra di loop (wrap modulare)."),
    _k("loop_start", "Inizio loop in secondi (richiesto per attivare il loop)."),
    _k("loop_end", "Fine loop (s). Mutuamente esclusivo con loop_dur "
                   "(loop_end ha priorita')."),
    _k("loop_dur", "Durata loop (s). Unica forma per un loop a cavallo della "
                   "fine del file."),
    _k("loop_unit", "`normalized`: i valori loop sono [0,1] scalati su "
                    "sample_dur (asse Y, non X).", values=["normalized"]),
]

_PITCH_KEYS = [
    _k("semitones", "Trasposizione in semitoni (12-EDO). Bounds [-36, 36]."),
    _k("quarter_tone", "Quarti di tono (24-EDO). Bounds [-72, 72]."),
    _k("eighth_tone", "Ottavi di tono (48-EDO). Bounds [-144, 144]."),
    _k("cents", "Cents (1200-EDO). Bounds [-3600, 3600]."),
    _k("edo", "Divisioni per ottava (intero); il valore va in `value:` a fianco."),
    _k("value", "Gradi EDO (solo con `edo:`). Scalare o envelope."),
    _k("ratio", "Moltiplicatore diretto. Bounds [0.001, 8]."),
    _k("range", "± variazione random per grano nell'unita' attiva."),
]

_VOICES_KEYS = [
    _k("num_voices", "Numero di voci (default 1, bounds [1, 256]). Envelope "
                     "ammesso; valori frazionari = fade della voce di confine."),
    _k("scatter", "0 = voci sincrone sullo stesso IOT, 1 = IOT indipendenti."),
    _k("pitch", "Strategy pitch: step | range | chord | chord_progression | "
                "stochastic | spectral (+ unit)."),
    _k("onset_offset", "Strategy onset: linear | geometric | stochastic."),
    _k("pointer", "Strategy pointer: linear | stochastic (+ normalized)."),
    _k("pan", "Strategy pan: range | stochastic | step."),
]

_VOICES_PITCH_KEYS = [
    _k("strategy", "step | range | chord | chord_progression | stochastic | spectral.",
       values=["step", "range", "chord", "chord_progression", "stochastic", "spectral"]),
    _k("step", "Semitoni per passo (voce i -> i*step). Scalare o envelope."),
    _k("pitch_range", "Ampiezza totale nell'unita' attiva (range/stochastic)."),
    _k("chord", "Nome accordo (maj, min7, dom9, ...).", values=EI.CHORDS),
    _k("inversion", "Rivolto (0 = root position)."),
    _k("progression", "Lista `[tempo, accordo(, inversione)]`, tempi non decrescenti."),
    _k("interp", "linear/cubic = glissando · step = blocchi.", values=EI.INTERPOLATIONS),
    _k("voice_leading", "nearest (default) | positional.", values=["nearest", "positional"]),
    _k("unit", "Geometria della distribuzione: semitones | cents | quarter_tone "
               "| eighth_tone | {edo: N} | ratio.",
       values=["semitones", "cents", "quarter_tone", "eighth_tone", "ratio"]),
]

_VOICES_ONSET_KEYS = [
    _k("strategy", "linear | geometric | stochastic.",
       values=["linear", "geometric", "stochastic"]),
    _k("step", "Secondi per passo (linear) o passo iniziale (geometric)."),
    _k("base", "Base esponenziale (geometric)."),
    _k("max_offset", "Offset massimo in secondi (stochastic)."),
]

_VOICES_POINTER_KEYS = [
    _k("strategy", "linear | stochastic.", values=["linear", "stochastic"]),
    _k("step", "Offset per voce (linear); negativo = voci indietro."),
    _k("pointer_range", "Range massimo (stochastic)."),
    _k("normalized", "true: i valori sono frazione di sample_dur invece di secondi.",
       values=["true", "false"]),
]

_VOICES_PAN_KEYS = [
    _k("strategy", "range | stochastic | step.", values=["range", "stochastic", "step"]),
    _k("spread", "Gradi totali distribuiti (range/stochastic)."),
    _k("step", "Gradi per voce (step; puo' essere negativo)."),
]

_DEPHASE_KEYS = [
    _k(name, f"Probabilita' 0-100 (o envelope) di applicare il range di `{name}` "
             "per grano. Chiave assente = range sempre attivo se dichiarato.")
    for name in ["volume", "pan", "duration", "pitch", "pointer", "reverse", "envelope"]
]

_GRAIN_ENVELOPE_KEYS = [
    _k("from", "Finestra di partenza (morphing).", values=sorted(EI.WINDOWS)),
    _k("to", "Finestra di arrivo (morphing).", values=sorted(EI.WINDOWS)),
    _k("states", "Percorso multi-stato: lista `[posizione 0..1, finestra]`."),
    _k("curve", "Envelope 0..1 che guida la transizione (0 = 100% from)."),
]

# ---------------------------------------------------------------------------
# Contesti del linguaggio degli studi.

_ROOT_KEYS = [
    _k("study_id", "Identificatore dello studio (usato come nome cartella).", kind="keyword"),
    _k("title", "Titolo libero; finisce nell'header dei file generati.", kind="keyword"),
    _k("seed", "Seed globale engine (render NumPy riproducibili).", kind="keyword"),
    _k("duration", "Durata condivisa (s): **obbligatoria se c'e' `stack:`** (la "
                   "durata su cui il processo normalizza i tempi). Cambiandola, "
                   "gl-ls offre il ricalcolo dei breakpoint assoluti.", kind="keyword"),
    _k("samples_dir", "Path relativo alla root del repo (default `samples/`).", kind="keyword"),
    _k("base", "Parametri fissi dello stream: tutto cio' che non e' un asse "
               "(superficie engine PGE).", kind="keyword",
       snippet="base:\n  onset: 0\n  duration: ${1:6}\n  sample: ${2:corpus.wav}\n"
               "  time_mode: normalized\n  grain:\n    envelope: hanning"),
    _k("axes", "Assi (parametri sotto osservazione): conosce solo Y — quali "
               "parametri si muovono, con che valori e con che curva. Il timing "
               "e' dello sweep.", kind="keyword"),
    _k("sweep", "Config del processo sweep (possiede X: plateau/transition, "
                "mode, orders, orderings).", kind="keyword"),
    _k("stack", "Processo stack (attivo per presenza, anche `stack: {}`): tutti "
                "gli stream sommati in un documento multi-stream. Chiavi "
                "riservate `seed`/`unit`; ogni altra chiave e' un asse con "
                "camminata-X.", kind="keyword"),
    _k("streams", "Varianti di ascolto con override parziali (deep-merge; le "
                  "liste rimpiazzano). Entry con `spread:` generano n stream.", kind="keyword"),
    _k("versions", "Genera piu' file (una batteria di studi): ogni chiave e' una "
                   "variabile-generatore Y (`values` | `ramp` | banda), il "
                   "prodotto cartesiano delle variabili fa i file. Chiavi "
                   "riservate `onset`/`duration` e `chunk` (raggruppamento "
                   "diagonale) non sono variabili del prodotto.", kind="keyword"),
]

_AXES_RESERVED = [
    _k("interpolation", "Default di studio per la curva Y tra i breakpoint: "
                        "linear | cubic | step. Ogni asse puo' fare override.",
       values=EI.INTERPOLATIONS, kind="keyword"),
    _k("seed", "Seed-Y globale (default per ogni banda Y senza seed proprio).",
       kind="keyword"),
]

_AXIS_KEYS = [
    _k("path", "**Path YAML nell'engine** da muovere (notazione punto): "
               "`density`, `grain.duration`, `volume`, ... **Opzionale**: se "
               "omesso, il path e' la chiave dell'asse stessa (anche dotted); "
               "dichiararlo serve solo come alias (nome leggibile diverso "
               "dal path reale).",
       values=EI.AXIS_PATHS),
    _k("baseline", "Valore a riposo dell'asse; obbligatorio se l'engine non ha "
                   "default per il path (density, pitch.*, loop_*)."),
    _k("interpolation", "Override per-asse della curva Y: linear | cubic | step. "
                        "`step` = tiene-e-salta (collasso durata solo se TUTTI "
                        "gli assi sono step).", values=EI.INTERPOLATIONS),
] + _ENV_KEYS

_SWEEP_KEYS = [
    _k("mode", "discrete | envelope | both (default discrete).", values=EI.SWEEP_MODES),
    _k("plateau", "Secondi di ascolto stabile per valore (default 5.0)."),
    _k("transition", "Secondi di transizione tra plateau (default 5.0)."),
    _k("orders", "Ordini da generare: 1 = un asse alla volta, 2 = coppie, ..."),
    _k("orderings", "Permutazioni esplicite: primo = asse lento (outer), "
                    "ultimo = veloce (inner)."),
    _k("stream_id", "(interno) id stream impostato dal resolver.", kind="internal"),
]

_VERSIONS_RESERVED = [
    _k("onset", "Chiave riservata di `versions:`: onset assoluto (s) condiviso, "
                "non una variabile del prodotto cartesiano.", kind="keyword"),
    _k("duration", "Chiave riservata di `versions:`: durata (s) condivisa, non "
                   "una variabile del prodotto cartesiano.", kind="keyword"),
    _k("chunk", "Chiave riservata di `versions:`: intero `>= 1`. Riordina le "
                "combinazioni per **traversata diagonale** della griglia (somma "
                "degli indici crescente, non nesting lessicografico) e le taglia "
                "in blocchi consecutivi di `chunk`, un file per blocco — cosi' "
                "ogni file attraversa tutte le variabili da subito. Assente = "
                "prodotto cartesiano lessicografico (un file per valore della "
                "prima variabile dichiarata).", kind="keyword"),
]

_STACK_RESERVED = [
    _k("seed", "Seed-X globale (chiave riservata; il per-asse vince).", kind="keyword"),
    _k("unit", "Unita' globale della banda X: `hz` (frequenza, default) | `s` "
               "(periodo) | `bpm` (battiti/minuto). Sceglie lo **spazio** della "
               "camminata, non una notazione.", values=sorted(EI.X_UNITS), kind="keyword"),
]

_WALK_KEYS = [
    _k("base", "Banda della camminata-X (Env, nell'unita' di `unit`): a ogni "
               "punto si pesca in `[base(t), base(t)+range(t)]` e il punto "
               "successivo cade a `t + passo`. **La X possiede n.**", kind="macro"),
    _k("range", "Ampiezza della banda X (Env). Assente = camminata "
                "deterministica (segue base; il seed non influisce sui tempi).", kind="macro"),
    _k("seed", "Seed-X per-asse (vince sul globale `stack.seed`).", kind="macro"),
    _k("unit", "Unit per-asse (vince sul globale): hz | s | bpm. gl-ls offre la "
               "**conversione con ricalcolo** di base/range.",
       values=sorted(EI.X_UNITS), kind="macro"),
    _k("distribution", _GEN_DOC["distribution"], values=EI.DISTRIBUTIONS, kind="macro"),
    _k("drift", "La frequenza (o il periodo) di generazione **deriva** invece "
                "di saltare: accelerandi/ritardandi stocastici. `{step, seed?}` "
                "sul tempo reale normalizzato.", kind="macro"),
]

_STREAM_OVERRIDE_KEYS = [
    _k("base", "Override parziale di `base` (deep-merge; i campi non toccati restano).", kind="keyword"),
    _k("axes", "Override parziale di `axes`: un generatore nuovo **rimpiazza** "
               "quello ereditato sullo stesso asse (via anche le chiavi banda).", kind="keyword"),
    _k("sweep", "Override parziale di `sweep` (es. orders, plateau).", kind="keyword"),
    _k("stack", "Override parziale di `stack` (deep-merge). `asse: null` annulla "
                "una camminata ereditata (torna linear).", kind="keyword"),
    _k("spread", "**Entry-spread**: genera `n` stream distribuendo valori su "
                 "path puntati. L'entry sparisce, compaiono `nome_1..nome_n`.",
       kind="keyword",
       snippet="spread:\n  n: ${1:8}\n  over:\n    ${2:base.onset}:\n"
               "      ramp: {start: ${3:0}, step: ${4:2}}"),
]

_SPREAD_KEYS = [
    _k("n", "Quanti stream generare. Se una strategy possiede il conteggio "
            "(values/ramp piena/banda con n) deve **coincidere**; se omesso lo "
            "definisce l'unico conteggio posseduto."),
    _k("over", "`{path puntato: strategy}` — i valori si appaiano **per "
               "indice** tra i path (niente prodotto cartesiano). Ammessa "
               "anche la forma dotted `over.<path>: ...` al primo livello."),
    _k("sweep", "Blocco sweep esplicito: **riattiva** lo sweep dei generati "
                "(di default spread lo spegne: ascolto verticale)."),
]

_SPREAD_STRATEGY_KEYS = _ENV_KEYS  # values | ramp | banda | expr (+n/seed/...)

_ENGINE_ENV_KEYS = [
    _k("type", "Interpolazione: linear (default) | cubic (Fritsch-Carlson, "
               "monotona) | step (hold-left).", values=EI.INTERPOLATIONS),
    _k("points", "Breakpoint `[[t, v], ...]`; ammessi `[t, v, type]` per-punto "
                 "e formati compatti `[pattern, end_time, n_reps, ...]`."),
    _k("time_mode", "Override locale: absolute (secondi) | normalized ([0,1] "
                    "su duration).", values=EI.TIME_MODES),
    _k("time_unit", "Alias locale di time_mode.", values=EI.TIME_MODES),
    _k("expr", _GEN_DOC["expr"], kind="macro"),
    _k("let", _GEN_DOC["let"], kind="macro"),
]

CONTEXTS: Dict[str, List[Key]] = {
    "root": _ROOT_KEYS,
    "engine_stream": _ENGINE_STREAM_KEYS,
    "grain": _GRAIN_KEYS,
    "grain_envelope": _GRAIN_ENVELOPE_KEYS,
    "pointer": _POINTER_KEYS,
    "pitch": _PITCH_KEYS,
    "voices": _VOICES_KEYS,
    "voices_pitch": _VOICES_PITCH_KEYS,
    "voices_onset": _VOICES_ONSET_KEYS,
    "voices_pointer": _VOICES_POINTER_KEYS,
    "voices_pan": _VOICES_PAN_KEYS,
    "dephase": _DEPHASE_KEYS,
    "engine_env": _ENGINE_ENV_KEYS,
    "axes": _AXES_RESERVED,          # + nomi d'asse liberi
    "axis": _AXIS_KEYS,
    "env": _ENV_KEYS,
    "ramp": _RAMP_KEYS,
    "drift": _DRIFT_KEYS,
    "sweep": _SWEEP_KEYS,
    "stack": _STACK_RESERVED,        # + nomi d'asse (camminate)
    "walk": _WALK_KEYS,
    "streams": [],                   # nomi liberi
    "versions": _VERSIONS_RESERVED,  # + variabili-generatore Y libere
    "stream_override": _STREAM_OVERRIDE_KEYS,
    "spread": _SPREAD_KEYS,
    "over": [],                      # path puntati
    "spread_strategy": _SPREAD_STRATEGY_KEYS,
    "let": [],
    "value": [],
}

# Contesti in cui una chiave sconosciuta e' un errore/warning (i contesti a
# chiavi libere — axes, stack, streams, over, let — non segnalano).
CLOSED_CONTEXTS = frozenset({
    "root", "engine_stream", "grain", "grain_envelope", "pointer", "pitch",
    "voices", "voices_pitch", "voices_onset", "voices_pointer", "voices_pan",
    "axis", "env", "engine_env", "ramp", "drift", "sweep", "walk",
    "stream_override", "spread", "spread_strategy",
})


def keys_for(ctx: str) -> List[Key]:
    return CONTEXTS.get(ctx, [])


def key_in(ctx: str, name: str) -> Optional[Key]:
    for k in CONTEXTS.get(ctx, []):
        if k.name == name:
            return k
    return None


# ---------------------------------------------------------------------------
# Risoluzione path -> contesto

_ENV_CHILD = {"base", "range"}          # figli che riaprono un ctx env
_GEN_MARKERS = {"values", "ramp", "base"}


def _engine_context(rest: KeyPath) -> str:
    if not rest:
        return "engine_stream"
    if "let" in rest:
        # stesso trattamento dei let negli Env: nomi liberi al primo livello,
        # contesto ricorsivo dentro i valori (nodi-expr annidati)
        return _env_context(rest[rest.index("let"):])
    head = rest[0]
    table: Dict[object, str] = {
        "grain": "grain", "pointer": "pointer", "pitch": "pitch",
        "voices": "voices", "dephase": "dephase",
    }
    if head == "grain" and len(rest) >= 2 and rest[1] == "envelope":
        return "grain_envelope" if len(rest) == 2 else "value"
    if head == "voices" and len(rest) >= 2:
        sub = {"pitch": "voices_pitch", "onset_offset": "voices_onset",
               "pointer": "voices_pointer", "pan": "voices_pan"}.get(rest[1])
        if sub:
            return sub if len(rest) == 2 else "engine_env"
    if head in table:
        return table[head] if len(rest) == 1 else "engine_env"
    return "engine_env"


def _env_context(rest: KeyPath) -> str:
    """Contesto dentro un Env/generatore (ricorsivo: nodi annidati)."""
    if not rest:
        return "env"
    head = rest[0]
    if head == "ramp":
        return "ramp" if len(rest) == 1 else _env_context(rest[2:]) if len(rest) > 1 and rest[1] == "step" else "value"
    if head == "drift":
        return "drift" if len(rest) == 1 else _env_context(rest[2:]) if len(rest) > 1 and rest[1] == "step" else "value"
    if head in _ENV_CHILD:
        return _env_context(rest[1:])
    if head == "let":
        if len(rest) == 1:
            return "let"  # i nomi dichiarati in let sono liberi
        # dentro il valore di una variabile: contesto env ricorsivo, cosi' un
        # nodo-expr annidato (o una banda-let) ha hover/completion delle sue
        # chiavi come un nodo top-level
        return _env_context(rest[2:])
    return "value"


def _expand_dotted(rest: KeyPath, axis_names=frozenset()) -> KeyPath:
    """Espande i segmenti puntati di un path di override nella forma annidata.

    ``("axes.density.ramp", "step")`` -> ``("axes", "density", "ramp",
    "step")``: la notazione a chiave puntata che il runtime espande negli
    override di stream (granstudies ``study_spec._expand_dotted_keys``),
    cosi' il contesto e' quello della forma annidata equivalente.

    Sotto ``axes.``/``stack.`` il primo identificatore e' un nome d'asse
    (eventualmente dotted, es. ``grain.duration``): il suo confine e' risolto
    da ``EI.split_axis_key`` (assi dichiarati > registro engine > primo
    segmento) e il nome resta un unico elemento del path espanso.
    """
    if not any(isinstance(s, str) and "." in s for s in rest):
        return rest
    out: List[object] = []
    for seg in rest:
        if not isinstance(seg, str):
            out.append(seg)
            continue
        parts = seg.split(".")
        if parts[0] in ("axes", "stack") and len(parts) > 1:
            axis, tail, _ = EI.split_axis_key(".".join(parts[1:]), axis_names)
            out.extend([parts[0], axis, *tail])
        elif out and out[-1] in ("axes", "stack") and "." in seg:
            axis, tail, _ = EI.split_axis_key(seg, axis_names)
            out.extend([axis, *tail])
        else:
            out.extend(parts)
    return tuple(out)


def context_for_path(path: KeyPath, axis_names=frozenset()) -> str:
    """Contesto schema di un key-path concreto del documento.

    ``axis_names``: nomi degli assi dichiarati nel documento base, usati per
    il boundary-match dei nomi d'asse dotted nelle chiavi puntate di override.
    """
    path = tuple(path)
    if not path:
        return "root"
    head = path[0]
    if head == "streams":
        if len(path) == 1:
            return "streams"
        if len(path) == 2:
            return "stream_override"
        sub = path[2:]
        # la notazione puntata degli override equivale alla forma annidata;
        # il sottoalbero ``spread`` resta com'e' (viene consumato prima
        # dell'espansione runtime e le chiavi di ``over`` sono path interi)
        if sub[0] != "spread":
            sub = _expand_dotted(sub, axis_names)
        if sub[0] == "spread":
            if len(sub) == 1:
                return "spread"
            if sub[1] == "over":
                if len(sub) == 2:
                    return "over"
                if len(sub) == 3:
                    return "spread_strategy"
                return _env_context(sub[3:])
            if isinstance(sub[1], str) and sub[1].startswith("over."):
                # dotted ``over.<path>`` al primo livello di spread: la chiave
                # collassa ``over`` + path, i figli sono la strategy
                if len(sub) == 2:
                    return "spread_strategy"
                return _env_context(sub[2:])
            if sub[1] == "sweep":
                return "sweep" if len(sub) == 2 else "value"
            if sub[1] == "n":
                return "value"
            return "value"
        return context_for_path(sub, axis_names)
    if head == "base":
        return _engine_context(path[1:])
    if head == "axes":
        if len(path) == 1:
            return "axes"
        if len(path) == 2:
            return "value" if path[1] in ("interpolation", "seed") else "axis"
        return _env_context(path[2:])
    if head == "sweep":
        return "sweep" if len(path) == 1 else "value"
    if head == "stack":
        if len(path) == 1:
            return "stack"
        if len(path) == 2:
            return "value" if path[1] in ("seed", "unit") else "walk"
        return _env_context(path[2:])
    if head == "versions":
        if len(path) == 1:
            return "versions"
        if len(path) == 2:
            # chiavi riservate = scalari; ogni altra chiave e' una
            # variabile-generatore Y (Env: values | ramp | banda)
            return "value" if path[1] in ("onset", "duration", "chunk") else "env"
        return _env_context(path[2:])
    return "value" if len(path) > 1 else "root"
