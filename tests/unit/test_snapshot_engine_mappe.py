"""Il mirror delle mappe caotiche messo a confronto col motore, quando c'e'.

Stessa forma di ``test_snapshot_granstudies.py``: gl-ls non importa il
motore, e questa verifica e' **opportunista**. Cerca i sorgenti di PGE in
``$PGE_SRC`` o nel checkout fratello (``../PythonGranularEngine/src``) e, se
non li trova, si salta. Confronta i letterali che ``engine_expr`` ed
``engine_info`` copiano (nomi, tetti, catalogo, campi) e un corpus di
espressioni compilato dai due lati: la grammatica e' una copia, e una copia
che diverge e' un falso rosso, o un silenzio dove il motore si ferma.
"""
import os
import sys
from pathlib import Path

import pytest

from glls import engine_expr as EX
from glls import engine_info as EI


def _engine():
    candidates = [os.environ.get("PGE_SRC"),
                  str(Path(__file__).resolve().parents[3]
                      / "PythonGranularEngine" / "src")]
    for c in candidates:
        if c and (Path(c) / "pge" / "maps" / "catalog.py").exists():
            if c not in sys.path:
                sys.path.insert(0, c)
            try:
                import pge.expressions.expression as expression  # type: ignore
                import pge.expressions.fields as fields  # type: ignore
                import pge.maps.catalog as catalog  # type: ignore
                import pge.maps.map_set as map_set  # type: ignore
                import pge.engine.expression_shelter as shelter  # type: ignore
                import pge.controllers.density_controller as dc  # type: ignore
                import pge.controllers.pointer_controller as pc  # type: ignore
                import pge.parameters.parameter_definitions as pd  # type: ignore
            except Exception:
                return None
            return dict(expression=expression, fields=fields, catalog=catalog,
                        map_set=map_set, shelter=shelter, dc=dc, pc=pc, pd=pd)
    return None


E = _engine()
pytestmark = pytest.mark.skipif(
    E is None, reason="sorgenti di PGE non trovati ($PGE_SRC o checkout "
                      "fratello): la verifica vale per chi ha entrambi i repo")


def test_il_linguaggio():
    ex = E["expression"]
    assert {k: (v[1], v[2]) for k, v in ex.FUNCTIONS.items()} == EX.FUNCTIONS
    assert list(ex.FUNCTIONS) == list(EX.FUNCTIONS)
    assert tuple(ex.CONSTANTS) == EX.CONSTANTS
    assert ex.MAX_DEPTH == EX.MAX_DEPTH
    assert ex.NAME_PATTERN == EX.NAME_PATTERN
    assert E["map_set"].TIME_NAME == EX.TIME_NAME
    assert tuple(E["map_set"].MAP_EQUATION_VARIABLES) == EX.MAP_EQUATION_VARIABLES
    assert E["shelter"].LOAD_TIME_NAMES == EX.LOAD_TIME_NAMES


def test_i_campi():
    assert tuple(E["fields"].EXPRESSION_FIELDS) == EX.EXPRESSION_FIELDS
    assert dict(E["fields"].EXPRESSION_REFUSALS) == EX.EXPRESSION_REFUSALS


def test_il_catalogo():
    cat, ms = E["catalog"], E["map_set"]
    assert tuple(cat.MAP_TYPES) == EI.MAP_TYPES
    assert cat.MAP_TYPE_CUSTOM == EI.MAP_TYPE_CUSTOM
    assert tuple(ms.MAP_KEYS) == EI.MAP_KEYS
    assert ms.MAP_ITERATE_MAX == EI.MAP_ITERATE_MAX
    assert ms.MAP_TRANSIENT_MAX == EI.MAP_TRANSIENT_MAX
    assert ms.MAP_TRANSIENT_DEFAULT == EI.MAP_TRANSIENT_DEFAULT
    assert ms.MAP_CLOCK_GRAIN == EI.MAP_CLOCK_GRAIN
    assert (ms.MAP_CUSTOM_X0, ms.MAP_CUSTOM_Y0) == (EI.MAP_CUSTOM_X0, EI.MAP_CUSTOM_Y0)
    assert frozenset(ms.RESERVED_MAP_NAMES) == EI.reserved_map_names()
    for name, k in cat.MAP_KINDS.items():
        mine = EI.MAP_KINDS[name]
        assert (k.x0, k.r_range, k.value_range, k.variables) == (
            mine.x0, mine.r_range, mine.value_range, mine.variables), name
        if k.variables == 2:
            assert (k.y0, k.y_range) == (mine.y0, mine.y_range), name
        assert (name in cat.SIN_BASED_TYPES) == mine.sin_based, name
    assert set(cat.MAP_KINDS) == set(EI.MAP_KINDS)


def test_modi_e_bounds():
    assert tuple(E["dc"].IOT_EXCLUSIVE_KEYS) == EI.IOT_EXCLUSIVE_KEYS
    assert tuple(E["pc"].POSITION_EXCLUSIVE_KEYS) == EI.POSITION_EXCLUSIVE_KEYS
    pd = E["pd"]
    wraps = {p for p, info in {"pointer.position": "pointer_position"}.items()
             if pd.parameter_wraps(info)}
    assert wraps == EI.WRAPPING_PATHS
    iot = pd.GRANULAR_PARAMETERS["grain_iot"]
    assert (iot.min_val, iot.max_val) == pytest.approx(EI.bounds_for("grain.iot"))
    pos = pd.GRANULAR_PARAMETERS["pointer_position"]
    assert (pos.min_val, pos.max_val) == EI.bounds_for("pointer.position")


CORPUS = [
    "(0.02 + 0.08*m1)", "(m1.y)", "(clip(m1, 0, 1))", "(clip(m1, 0))",
    "(min(1, 2, m1))", "(max())", "(pow(2, 3, 4))", "(-m1**2)", "(2**3**2)",
    "(m1 % 2)", "(m1 ^ 2)", "(boh(m1))", "(m9)", "(t)", "(pi*e)", "(0.02 +)",
    "((m1)", "(m1))", "(.5 + 1e-3)", "(1e)", "(sin(t) * cos(m1, 2))",
    "-30 + 20*m1", "(" * 50 + "m1" + ")" * 50, "(" * 51 + "m1" + ")" * 51,
    "(a.b.c)", "(m1 . y)", "", "   ",
]


@pytest.mark.parametrize("testo", CORPUS)
def test_compila_come_il_motore(testo):
    ex = E["expression"]
    variabili = ("m1", "m1.y", "t")
    try:
        compilata = ex.compile_expression(testo, variabili)
        atteso = (True, tuple(compilata.names))
    except Exception:
        atteso = (False, ())
    mia = EX.compile_expression(testo, variabili)
    assert (mia.ok, mia.names) == atteso


@pytest.mark.parametrize("testo", ["(a) + (b)", "((a))", "(a", "a)", " (a) "])
def test_parentesi_esterne(testo):
    assert EX.outer_parenthesized(testo) == E["expression"].outer_parenthesized(testo)
