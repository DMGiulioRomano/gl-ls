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

Con un'aggiunta, imparata dal giro dopo: granstudies indicizza **dodici** dei
ventisette path dello snapshot, e i quindici che restano fuori non erano
verificati da niente. Li' si erano fermati quattro bounds sbagliati — le
chiavi ``_range``, confrontate coi bounds del *valore* invece che con quelli
della *banda* — tutti nella direzione peggiore: piu' larghi del vero, quindi
l'editor taceva su cio' che il parser dell'engine rifiuta con
``ParameterBoundError``. La seconda meta' del file chiude quel buco chiedendo
all'engine, che granstudies porta con se' (submodule + patch di
``VOLUME_MAX_DB``): e' sempre il runtime, guardato un livello piu' sotto.
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
    ``(None, None)``.

    Fuori restano i path di ``RUNTIME_VALUE_FOR_RANGE``, dove il confronto
    sarebbe fra numeri che rispondono a domande diverse: il test sotto e' il
    posto dove quella divergenza si asserisce."""
    sr = gs_bounds.default_output_sr()
    diff = []
    for path in sorted(gs_bounds.known_paths()):
        if path in EI.RUNTIME_VALUE_FOR_RANGE:
            continue
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


@needs_runtime
def test_il_runtime_legge_ancora_il_valore_dove_la_chiave_e_una_banda():
    """L'altra divergenza dichiarata, anch'essa eseguibile.

    ``pointer.deviation`` e' indicizzato sul registry, quindi granstudies ne
    legge i bounds del *valore*; la sola meta' dichiarabile in YAML e' la
    banda ``offset_range``, i cui bounds sono ``min_range``/``max_range``. Il
    runtime accetta cosi' una deviazione negativa che il suo stesso engine
    rifiuta al parse — gl-ls no, e la differenza e' voluta. Il giorno in cui
    granstudies legge lo slot giusto questo test cade: si toglie la voce da
    ``RUNTIME_VALUE_FOR_RANGE``, non si aggiorna il test."""
    sr = gs_bounds.default_output_sr()
    for path in sorted(EI.RUNTIME_VALUE_FOR_RANGE):
        loro = gs_bounds.bounds_for(path, output_sr=sr)
        nostri = EI.bounds_for(_tradotto(path))
        assert loro is not None, (
            f"il runtime non conosce piu' '{path}': togli la voce da "
            "engine_info.RUNTIME_VALUE_FOR_RANGE"
        )
        assert tuple(loro) != tuple(nostri), (
            f"su '{path}' runtime e gl-ls dicono ora la stessa cosa: la "
            "divergenza e' chiusa, togli la voce da "
            "engine_info.RUNTIME_VALUE_FOR_RANGE"
        )


# ---------------------------------------------------------------------------
# Lo snapshot contro l'engine, riga per riga, guidato da ``ORIGINS``.
#
# La meta' sopra chiede a granstudies, e granstudies risponde per dodici path.
# Qui la domanda va all'engine che granstudies porta con se': lo stesso
# runtime — il submodule sotto ``engine/``, col ``max_val`` di ``volume``
# gia' alzato a ``VOLUME_MAX_DB`` — solo guardato un livello piu' sotto, dove
# stanno anche i quindici path che granstudies non indicizza.


def _engine():
    """Il registry, gli schema e le unita' di pitch del runtime, se ci sono.

    Passa da ``granstudies`` di proposito e non da un ``sys.path`` costruito
    qui: e' quell'import a mettere ``engine/src`` in cammino **e** ad alzare
    il tetto di ``volume``. Un engine raggiunto per conto proprio direbbe
    ``max_val=12`` e la verifica cadrebbe su una differenza che non esiste.
    """
    if gs_bounds is None:
        return None
    from pge.parameters import pitch_unit  # type: ignore
    from pge.parameters.parameter_definitions import (  # type: ignore
        GRANULAR_PARAMETERS,
    )
    from pge.parameters.parameter_schema import ALL_SCHEMAS  # type: ignore

    return GRANULAR_PARAMETERS, ALL_SCHEMAS, pitch_unit


# Prefisso YAML di ogni schema engine: i path di ``POINTER_PARAMETER_SCHEMA``
# sono relativi al blocco ``pointer:`` (``yaml_path='loop_start'``), quelli di
# stream e density sono gia' assoluti (``yaml_path='grain.duration'``).
_SCHEMA_PREFIX = {"stream": "", "pointer": "pointer.", "pitch": "pitch.",
                  "density": ""}


def _specs():
    """``path YAML dotted -> ParameterSpec`` da tutti gli schema dell'engine."""
    _, all_schemas, _ = _engine()
    return {_SCHEMA_PREFIX[name] + spec.yaml_path: spec
            for name, schema in all_schemas.items()
            for spec in schema}


def _attesi(path, origin):
    """I bounds che l'engine dice per ``path``, o ``None`` se non dice niente."""
    registry, _, pitch_unit = _engine()
    if origin.kind == "studio":
        return None
    if origin.kind == "pitch":
        b = pitch_unit.make_pitch_unit(origin.name).value_bounds()
        return (b.min_val, b.max_val)
    b = registry[origin.name]
    lo, hi = ((b.min_val, b.max_val) if origin.slot == "value"
              else (b.min_range, b.max_range))
    # Intervallo degenere = segnaposto per un parametro non numerico, come
    # nella meta' sopra: li' gl-ls scrive (None, None).
    if lo == hi:
        return (None, None)
    return (EI.STUDIO_FLOOR.get(path, lo), hi)


def _uguali(a, b):
    return tuple(None if x is None else float(x) for x in a) == \
           tuple(None if x is None else float(x) for x in b)


def test_ogni_riga_dello_snapshot_dice_da_dove_viene():
    """``ORIGINS`` totale su ``PARAMS``, e questo si verifica **sempre**.

    E' la guardia che tiene viva tutta la sezione: senza, un path aggiunto
    domani non verrebbe confrontato con niente e il buco si riaprirebbe in
    silenzio — che e' esattamente come i quattro bounds della banda sono
    rimasti sbagliati per un giro."""
    assert set(EI.ORIGINS) == set(EI.PARAMS), (
        "path senza provenienza dichiarata: "
        f"{sorted(set(EI.PARAMS) - set(EI.ORIGINS))}; "
        "provenienze senza path: "
        f"{sorted(set(EI.ORIGINS) - set(EI.PARAMS))}"
    )


def test_il_floor_di_studio_e_dichiarato_dove_lo_si_applica():
    """``STUDIO_FLOOR`` non e' un'eccezione del test ma una riga del modulo."""
    assert EI.STUDIO_FLOOR == {"grain.duration": EI.GRAIN_DURATION_MIN}
    assert EI.ORIGINS["grain.duration"].kind == "registry"


@needs_runtime
def test_i_bounds_di_ogni_path_sono_quelli_dell_engine():
    """Tutte e ventisette le righe, non le dodici che granstudies indicizza.

    Il caso che questa verifica esiste per prendere e' la chiave ``_range``:
    ``volume_range`` non si confronta con ``min_val``/``max_val`` di
    ``volume`` ma con ``min_range``/``max_range``, che sono altri numeri.
    Chi sbaglia slot ottiene bounds troppo larghi, e troppo larghi vuol dire
    muti su cio' che il parser rifiuta."""
    diff = []
    for path, origin in sorted(EI.ORIGINS.items()):
        attesi = _attesi(path, origin)
        if attesi is None:
            continue
        info = EI.PARAMS[path]
        if not _uguali((info.min, info.max), attesi):
            diff.append(f"{path} [{origin.kind}/{origin.name}/{origin.slot}]: "
                        f"gl-ls {(info.min, info.max)}, engine {attesi}")
    assert not diff, "bounds divergenti dall'engine:\n" + "\n".join(diff)


@needs_runtime
def test_la_banda_non_si_confonde_col_valore():
    """Il fatto su cui poggia lo slot, asserito invece che commentato.

    Se un giorno l'engine facesse coincidere le due coppie, lo slot
    smetterebbe di discriminare e l'errore tornerebbe invisibile: meglio
    saperlo da un test che scoprirlo da uno studio che non renderizza."""
    registry, _, _ = _engine()
    for name in ("volume", "pan", "grain_duration", "pointer_deviation"):
        b = registry[name]
        assert (b.min_val, b.max_val) != (b.min_range, b.max_range), name


@needs_runtime
def test_il_floor_di_studio_non_e_piu_largo_di_quello_dell_engine():
    """Il floor di studio stringe, non allarga: sotto il minimo dinamico
    dell'engine sarebbe un valore che gl-ls accetta e nessuno renderizza."""
    from pge.parameters.parameter_definitions import (  # type: ignore
        get_parameter_definition,
    )

    dinamico = get_parameter_definition(
        "grain_duration", output_sr=EI.OUTPUT_SR).min_val
    assert EI.GRAIN_DURATION_MIN >= dinamico


@needs_runtime
def test_i_default_sono_quelli_degli_schema_engine():
    """I default non sono decorazione: ``needs_baseline`` ci si appoggia, e un
    default inventato rende obbligatorio un ``baseline`` che non lo e' (o
    tace su uno che lo e')."""
    specs = _specs()
    diff = []
    for path, origin in sorted(EI.ORIGINS.items()):
        # Una chiave ``_range`` non ha un default suo nello schema: lo spec ne
        # dichiara uno solo, quello del valore.
        if origin.kind != "registry" or origin.slot != "value":
            continue
        spec = specs.get(path)
        if spec is None:
            continue
        nostro = EI.PARAMS[path].default
        if (nostro is None) != (spec.default is None) or (
                nostro is not None and nostro != spec.default):
            diff.append(f"{path}: gl-ls {nostro!r}, spec {spec.default!r}")
    assert not diff, "default divergenti:\n" + "\n".join(diff)


@needs_runtime
def test_i_due_path_del_blocco_voices_restano_fuori_dagli_schema():
    """``voices.num_voices`` e ``voices.scatter`` non hanno una
    ``ParameterSpec``: i loro default (1 e 0.0) vivono in
    ``Stream._init_voice_manager``. Sono percio' gli unici due default che il
    test sopra non copre, e vale la pena che il buco sia dichiarato invece che
    dedotto dal fatto che nessuno protesta."""
    specs = _specs()
    assert "voices.num_voices" not in specs
    assert "voices.scatter" not in specs
    assert EI.PARAMS["voices.num_voices"].default == 1
    assert EI.PARAMS["voices.scatter"].default == 0.0
