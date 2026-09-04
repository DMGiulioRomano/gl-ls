"""Lo snapshot di ``engine_info`` messo a confronto col runtime, quando c'e'.

gl-ls resta **standalone** (vedi `docs/architettura.md`): non importa
granstudies ne' l'engine, perche' gira dentro l'editor e non deve eseguire
codice del progetto aperto. Il costo di quella scelta e' il drift, e la
domanda di gl-ls #43 era se lo snapshot regga. La risposta e' la stessa gia'
data per i codici diagnostici (`test_codici.py`): non una dipendenza, ma una
**verifica opportunista** — chi ha entrambi i repo la esegue, in CI si salta.

Vale la pena notare *cosa* aveva davvero divergito, perche' non e' quello che
un import avrebbe chiuso: due dei tre path sbagliati venivano dai nomi di
*registry* di granstudies (`num_voices` per `voices.num_voices`), e il floor
di ``grain.duration`` e' una costante di studio che nell'engine non esiste.
``pge.api.parameter_bounds()`` non avrebbe detto niente su nessuno dei due.
Il confronto utile e' con **granstudies**, che di questi `study.yml` e' il
runtime.
"""
import pytest

from glls import engine_info as EI


def _granstudies_bounds():
    """Il modulo bounds del runtime, se importabile *e* col suo engine."""
    try:
        from granstudies import bounds as gs  # type: ignore

        gs.default_output_sr()
    except Exception:
        return None
    return gs


gs_bounds = _granstudies_bounds()
needs_runtime = pytest.mark.skipif(
    gs_bounds is None,
    reason="granstudies (col submodule engine) non importabile: la verifica "
           "incrociata vale per chi ha entrambi i repo",
)


def _tradotto(path: str) -> str:
    """Il path granstudies nella grafia YAML che gl-ls usa come chiave."""
    return EI.REGISTRY_SPELLINGS.get(path, path)


@needs_runtime
def test_la_frequenza_di_render_e_la_stessa():
    """Da ``OUTPUT_SR`` dipendono il floor e il fattore dell'unita' campioni."""
    assert gs_bounds.default_output_sr() == EI.OUTPUT_SR


@needs_runtime
def test_il_floor_di_grain_duration_e_quello_del_runtime():
    assert gs_bounds.MIN_GRAIN_SAMPLES == EI.MIN_GRAIN_SAMPLES
    lo, _ = gs_bounds.bounds_for("grain.duration",
                                 output_sr=gs_bounds.default_output_sr())
    assert lo == EI.PARAMS["grain.duration"].min


@needs_runtime
def test_ogni_path_del_runtime_e_noto_a_gl_ls():
    """Un path che il runtime conosce e l'editor no e' un buco: la diagnostica
    lo liquida come sconosciuto proprio dove il runtime lo accetta."""
    ignoti = {p for p in gs_bounds.known_paths()
              if _tradotto(p) not in EI.known_paths()}
    assert not ignoti, (
        "path noti al runtime e assenti da engine_info.PARAMS: "
        f"{sorted(ignoti)} (tradotti: {sorted(_tradotto(p) for p in ignoti)})"
    )


@needs_runtime
def test_i_bounds_coincidono_path_per_path():
    """Uguali, non 'compatibili': gl-ls piu' largo accetta cio' che il runtime
    rifiuta al parse, gl-ls piu' stretto segna in rosso cio' che renderizza.

    Un intervallo degenere (``lo == hi``) lato runtime non e' un bound: e' il
    segnaposto del registry per i parametri non numerici (``grain_envelope``,
    ``variation_mode='choice'``). Li' gl-ls dice la stessa cosa scrivendo
    ``(None, None)``."""
    sr = gs_bounds.default_output_sr()
    diff = []
    for path in sorted(gs_bounds.known_paths()):
        nostro = EI.bounds_for(_tradotto(path))
        loro = gs_bounds.bounds_for(path, output_sr=sr)
        if nostro is None or loro is None:
            continue
        lo, hi = loro
        atteso = (None, None) if lo == hi else loro
        if tuple(nostro) != tuple(atteso):
            diff.append(f"{path} -> {_tradotto(path)}: gl-ls {nostro}, "
                        f"runtime {loro}")
    assert not diff, "bounds divergenti:\n" + "\n".join(diff)


@needs_runtime
def test_le_grafie_di_registry_sono_ancora_quelle_del_runtime():
    """La divergenza dichiarata, resa eseguibile.

    ``REGISTRY_SPELLINGS`` esiste perche' il runtime indicizza questi tre
    parametri col nome del registry engine invece che con la chiave YAML.
    Il giorno in cui li rinomina, questo test cade — ed e' il momento di
    togliere la voce dalla mappa, non di aggiornare il test."""
    assert set(EI.REGISTRY_SPELLINGS) <= set(gs_bounds.known_paths()), (
        "grafie di registry che il runtime non usa piu': togli la voce da "
        "engine_info.REGISTRY_SPELLINGS "
        f"({sorted(set(EI.REGISTRY_SPELLINGS) - set(gs_bounds.known_paths()))})"
    )
    assert not (set(EI.REGISTRY_SPELLINGS.values())
                & set(gs_bounds.known_paths())), (
        "il runtime ha imparato la chiave YAML: la divergenza e' chiusa, "
        "togli la voce da engine_info.REGISTRY_SPELLINGS"
    )
