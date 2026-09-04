"""``pointer.loop_unit``: vocabolario chiuso e migrazione PGE v9 (engine #222).

Due regole che nascono dallo stesso cambiamento. Prima della v9 un
``loop_unit`` assente ereditava da ``time_mode``, e «tutto cio' che non e'
normalized» valeva assoluto: un refuso passava muto e uno stream
``normalized`` vedeva le proprie posizioni scalate sulla durata del sample.
Ora l'unita' e' un vocabolario di tre parole e il default e' ``seconds``,
qualunque cosa dica ``time_mode``.

Il rilievo sulla migrazione e' il gemello in editor di quello che
``granstudies.diagnostics.check_loop_unit`` fa al load e che l'engine stampa
a render time: stesso codice, stesso significato.
"""
from glls import codes, diagnostics, model, yamlpos

BASE = """study_id: t
base:
  onset: 0
  duration: 6
  sample: corpus.wav
%s
axes:
  density:
    baseline: 20
    values: [10, 30]
"""


def diags_of(text):
    doc = yamlpos.parse(text)
    return diagnostics.collect(doc, model.build(doc))


def codes_of(text):
    return {d.code for d in diags_of(text)}


def study(base_extra):
    """Uno studio valido con righe in piu' dentro ``base:``."""
    return BASE % base_extra


# --- il vocabolario ----------------------------------------------------------

def test_le_tre_unita_ammesse_passano():
    for unit in ("seconds", "absolute", "normalized"):
        text = study(f"  pointer:\n    loop_start: 1\n    loop_end: 2\n"
                     f"    loop_unit: {unit}\n")
        assert diags_of(text) == [], unit


def test_unita_fuori_vocabolario_e_errore_con_suggerimento():
    text = study("  pointer:\n    loop_unit: normalised\n")
    ds = [d for d in diags_of(text) if d.code == "loop-unit-sconosciuta"]
    assert len(ds) == 1
    assert "normalized" in ds[0].message
    assert ds[0].data["fix"] == {"kind": "rename-value", "new": "normalized"}


def test_unita_fuori_vocabolario_senza_suggerimento_resta_errore():
    text = study("  pointer:\n    loop_unit: campioni\n")
    assert "loop-unit-sconosciuta" in codes_of(text)


def test_chiave_scritta_e_lasciata_vuota_e_errore():
    """Prima era falsy, quindi ereditarieta'; ora e' un valore fuori dal
    vocabolario, cioe' un ``InvalidFieldValueError``."""
    text = study("  pointer:\n    start: 0.3\n    loop_unit:\n")
    assert "loop-unit-vuota" in codes_of(text)


def test_il_fix_della_chiave_vuota_scrive_il_valore_non_rinomina_la_chiave():
    """La diagnostica sta sulla chiave — un valore vuoto non ha uno span su cui
    puntare — quindi un 'rinomina' scriverebbe 'normalized:' al posto di
    'loop_unit:'."""
    from glls import actions

    uri = "file:///s.yml"
    text = study("  pointer:\n    start: 0.3\n    loop_unit:\n")
    doc = yamlpos.parse(text)
    ds = [d for d in diagnostics.collect(doc, model.build(doc))
          if d.code == "loop-unit-vuota"]
    edit = actions.quickfixes(doc, uri, ds)[0].edit.changes[uri][0]
    righe = text.splitlines(keepends=True)
    riga = righe[edit.range.start.line]
    nuova = (riga[:edit.range.start.character] + edit.new_text
             + riga[edit.range.end.character:])
    doc2 = yamlpos.parse("".join(righe[:edit.range.start.line]) + nuova
                         + "".join(righe[edit.range.start.line + 1:]))
    assert doc2.get(("base", "pointer", "loop_unit")) == "normalized"


def test_la_chiave_vuota_non_produce_anche_il_rilievo_di_migrazione():
    """Un errore e il warning che gli sta sopra sono la stessa riga: dirla due
    volte e' rumore, e il rimedio e' gia' nell'errore."""
    text = BASE % ("  time_mode: normalized\n  pointer:\n"
                   "    start: 0.3\n    loop_unit:\n")
    assert codes.LOOP_UNIT_IMPLICITO not in codes_of(text)


# --- la migrazione: posizioni senza unita' sotto normalized ------------------

def test_start_non_nullo_sotto_normalized_senza_unita():
    text = BASE % "  time_mode: normalized\n  pointer:\n    start: 0.3\n"
    ds = [d for d in diags_of(text) if d.code == codes.LOOP_UNIT_IMPLICITO]
    assert len(ds) == 1
    assert ds[0].severity == 2  # Warning: il documento ha un significato
    assert "start" in ds[0].message


def test_ogni_chiave_dello_scope_conta():
    for key in ("start", "loop_start", "loop_end", "loop_dur"):
        text = BASE % f"  time_mode: normalized\n  pointer:\n    {key}: 0.3\n"
        assert codes.LOOP_UNIT_IMPLICITO in codes_of(text), key


def test_lo_zero_non_si_muove():
    """Zero e' zero sotto qualunque fattore di scala: senza il filtro il
    rilievo cadrebbe su ogni stream che scrive ``start: 0``."""
    text = BASE % "  time_mode: normalized\n  pointer:\n    start: 0\n"
    assert codes.LOOP_UNIT_IMPLICITO not in codes_of(text)


def test_un_envelope_si_muove():
    text = BASE % ("  time_mode: normalized\n  pointer:\n"
                   "    start: [[0, 0.1], [1, 0.9]]\n")
    assert codes.LOOP_UNIT_IMPLICITO in codes_of(text)


def test_con_unita_dichiarata_nessun_rilievo():
    for unit in ("seconds", "absolute", "normalized"):
        text = BASE % (f"  time_mode: normalized\n  pointer:\n"
                       f"    start: 0.3\n    loop_unit: {unit}\n")
        assert codes.LOOP_UNIT_IMPLICITO not in codes_of(text), unit


def test_time_mode_assoluto_non_riguarda_la_migrazione():
    text = BASE % "  pointer:\n    start: 0.3\n"
    assert codes.LOOP_UNIT_IMPLICITO not in codes_of(text)


def test_lo_stream_eredita_l_unita_del_base():
    """Il caso di ``studies/stack``: ``loop_unit`` nel base, la sola ``start``
    nello stream. Si guarda il pointer efficace, non quello scritto."""
    text = BASE % ("  time_mode: normalized\n  pointer:\n"
                   "    loop_unit: normalized\n") + """streams:
  a:
    base:
      pointer:
        start: 0.4
"""
    assert codes.LOOP_UNIT_IMPLICITO not in codes_of(text)


def test_un_difetto_del_base_non_si_moltiplica_per_gli_stream():
    text = BASE % "  time_mode: normalized\n  pointer:\n    start: 0.3\n" + """streams:
  a:
    base:
      volume: -6
  b:
    base:
      volume: -3
  c: {}
"""
    ds = [d for d in diags_of(text) if d.code == codes.LOOP_UNIT_IMPLICITO]
    assert len(ds) == 1


def test_lo_stream_che_azzera_la_posizione_del_base_non_eredita_il_rilievo():
    text = BASE % "  time_mode: normalized\n  pointer:\n    start: 0.3\n" + """streams:
  a:
    base:
      pointer:
        start: 0
"""
    ds = [d for d in diags_of(text) if d.code == codes.LOOP_UNIT_IMPLICITO]
    assert ds == []


def test_il_rilievo_dello_stream_e_attribuito_allo_stream():
    text = BASE % "  time_mode: normalized\n" + """streams:
  a:
    base:
      pointer:
        start: 0.4
"""
    ds = [d for d in diags_of(text) if d.code == codes.LOOP_UNIT_IMPLICITO]
    assert len(ds) == 1
    riga = ds[0].range.start.line
    assert "pointer" in text.splitlines()[riga]


def test_il_time_mode_dello_stream_vince_su_quello_del_documento():
    text = BASE % "  pointer:\n    start: 0.3\n" + """streams:
  a:
    base:
      time_mode: normalized
"""
    assert codes.LOOP_UNIT_IMPLICITO in codes_of(text)


def test_una_posizione_scritta_per_path_puntato_conta():
    """La posizione non e' sempre dentro un blocco ``pointer:``: puo' arrivare
    da ``spread.over``, da ``versions:`` o da ``percorso:``."""
    text = BASE % "  time_mode: normalized\n" + """streams:
  g:
    spread:
      n: 2
      over: {base.pointer.start: {values: [0.1, 0.9]}}
"""
    assert codes.LOOP_UNIT_IMPLICITO in codes_of(text)


def test_il_path_puntato_col_marcatore_in_coda_conta():
    """La grafia del corpus: ``base.pointer.start.values`` in una entry-over."""
    text = BASE % "  time_mode: normalized\n" + """streams:
  g:
    spread:
      n: 2
      over:
        base.pointer.start.values: [0.1, 0.9]
"""
    assert codes.LOOP_UNIT_IMPLICITO in codes_of(text)


def test_il_quick_fix_offre_le_due_letture():
    """Quale sia l'unita' giusta lo sa solo chi ha scritto il numero: il fix
    non sceglie, offre le due letture."""
    from glls import actions

    uri = "file:///s.yml"
    text = BASE % "  time_mode: normalized\n  pointer:\n    start: 0.3\n"
    doc = yamlpos.parse(text)
    ds = [d for d in diagnostics.collect(doc, model.build(doc))
          if d.code == codes.LOOP_UNIT_IMPLICITO]
    acts = actions.quickfixes(doc, uri, ds)
    testi = {a.edit.changes[uri][0].new_text.strip() for a in acts}
    assert testi == {"loop_unit: normalized", "loop_unit: seconds"}


def test_il_quick_fix_scrive_dentro_il_blocco_pointer():
    from glls import actions

    uri = "file:///s.yml"
    text = BASE % "  time_mode: normalized\n  pointer:\n    start: 0.3\n"
    doc = yamlpos.parse(text)
    ds = [d for d in diagnostics.collect(doc, model.build(doc))
          if d.code == codes.LOOP_UNIT_IMPLICITO]
    fix = next(a for a in actions.quickfixes(doc, uri, ds)
               if "normalized" in a.title)
    edit = fix.edit.changes[uri][0]
    righe = text.splitlines(keepends=True)
    off = edit.range.start
    nuovo = "".join(righe[:off.line]) + edit.new_text + "".join(righe[off.line:])
    doc2 = yamlpos.parse(nuovo)
    assert doc2.syntax_error is None
    assert doc2.get(("base", "pointer", "loop_unit")) == "normalized"
    assert codes.LOOP_UNIT_IMPLICITO not in {
        d.code for d in diagnostics.collect(doc2, model.build(doc2))}


def test_su_un_pointer_in_forma_flow_il_fix_non_si_offre():
    """``_insert_first_key`` scrive una riga sopra la prima chiave del blocco:
    con la forma flow quella riga e' la riga del blocco stesso, e l'inserimento
    finirebbe fuori — meglio nessun fix che un fix che rompe il documento."""
    from glls import actions

    uri = "file:///s.yml"
    text = BASE % "  time_mode: normalized\n  pointer: {start: 0.3}\n"
    doc = yamlpos.parse(text)
    ds = [d for d in diagnostics.collect(doc, model.build(doc))
          if d.code == codes.LOOP_UNIT_IMPLICITO]
    assert len(ds) == 1
    assert actions.quickfixes(doc, uri, ds) == []
