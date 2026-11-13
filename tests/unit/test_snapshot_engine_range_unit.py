"""Il mirror di ``<param>_range_unit`` messo a confronto col motore, quando c'e'.

Stessa forma di ``test_snapshot_engine_mappe.py``: gl-ls non importa il
motore, e la verifica e' **opportunista** — sorgenti di PGE in ``$PGE_SRC`` o
nel checkout fratello, altrimenti si salta. Confronta i letterali che
``engine_info`` copia da PGE #267: il vocabolario, il default, il dominio
relativo, e *quale* banda e' governata da *quale* chiave
(``ParameterSpec.range_unit_path``). Quest'ultimo e' il punto che invecchia:
cablare la banda relativa su un secondo parametro, lato engine, e' aggiungere
una riga allo spec, e qui deve diventare rosso.
"""
import os
import sys
from pathlib import Path

import pytest

from glls import engine_info as EI


def _engine():
    candidates = [os.environ.get("PGE_SRC"),
                  str(Path(__file__).resolve().parents[3]
                      / "PythonGranularEngine" / "src")]
    for c in candidates:
        if c and (Path(c) / "pge" / "parameters" / "parameter_schema.py").exists():
            if c not in sys.path:
                sys.path.insert(0, c)
            try:
                import pge.parameters.parameter_definitions as pd  # type: ignore
                import pge.parameters.parameter_schema as ps  # type: ignore
            except Exception:
                return None
            if not hasattr(pd, "RANGE_UNITS"):
                return None   # motore precedente a PGE #267
            return dict(pd=pd, ps=ps)
    return None


E = _engine()
pytestmark = pytest.mark.skipif(
    E is None, reason="sorgenti di PGE (con #267) non trovati ($PGE_SRC o "
                      "checkout fratello): la verifica vale per chi ha "
                      "entrambi i repo")


def test_il_vocabolario():
    pd = E["pd"]
    assert tuple(pd.RANGE_UNITS) == EI.RANGE_UNITS
    assert pd.RANGE_UNIT_DEFAULT == EI.RANGE_UNIT_DEFAULT
    assert pd.RANGE_UNIT_RELATIVE == EI.RANGE_UNIT_RELATIVE


def test_il_dominio_relativo():
    assert tuple(E["pd"].RELATIVE_RANGE_BOUNDS) == EI.RELATIVE_RANGE_BOUNDS


def test_le_bande_governate():
    governate = {spec.range_path: spec.range_unit_path
                 for schema in E["ps"].ALL_SCHEMAS.values()
                 for spec in schema
                 if getattr(spec, "range_unit_path", None)}
    assert governate == EI.RANGE_UNIT_PATHS


def test_la_lettura_pura():
    pd = E["pd"]
    for unit in ("absolute", "relative", "relativ", None, "", 1):
        assert pd.range_unit_is_relative(unit) == EI.range_unit_is_relative(unit)
