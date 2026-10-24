import gzip
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scraper"))

from common import parse_num  # noqa: E402
from parsers import PARSERS  # noqa: E402

FIX = ROOT / "tests" / "fixtures"

# Values checked by hand against the official documents stored as fixtures.
EXPECTED = {
    "edenor": (1812.81, 159.128),
    "edesur": (1771.06, 157.116),
    "epec": (None, None),
    "enersa": (3193.22, 243.94),
    "refsa": (1799.9, 208.2989),
    "edese": (4383.42, 218.149),
    "esj": (4557.54, 224.7631),
    "epen": (10185.04, 395.027),
    "edersa": (9715.62, 287.765),
    "edemsa": (7562.923, 280.5412),
    "edeste": (7562.923, 280.5412),
    "ejesa": (5116.0, None),
    "edesal": (5927.328, 131.9797),
    "ape": (1517.32, None),
    "emsa": (2309.1, 272.997),
    "edelar": (None, 176.9956),
    "dpec": (29710.0, 181.928),
    "eden": (4835.87, 210.8862),
    "edes": (5400.69, 212.2569),
    "epe": (3944.25564, 247.6447),
}


def run(id):
    fx = json.load(gzip.open(FIX / f"{id}.json.gz", "rt"))
    fn = PARSERS[fx["source"]["parser"]]
    return fn(fx["text"], content=None, source=fx["source"], sheets=fx["sheets"])


@pytest.mark.parametrize("id", sorted(EXPECTED))
def test_comparable(id):
    if not (FIX / f"{id}.json.gz").exists():
        pytest.skip("sin fixture")
    out = run(id)
    assert any(f["valores"] for t in out["tablas"] for f in t["filas"])
    fijo, var = EXPECTED[id]
    comp = out.get("comparable") or {}
    got = ((comp.get("cargo_fijo") or {}).get("valor"), (comp.get("cargo_variable") or {}).get("valor"))
    assert got == (fijo, var)


def test_ejsed_tdi():
    out = run("ejsed")
    f = next(f for f in out["tablas"][0]["filas"] if f["grupo"] == "TDI-004" and f["concepto"] == "Cargo Fijo")
    assert f["valores"] == [35180.3356]


def test_epec_rows():
    filas = run("epec")["tablas"][0]["filas"]
    sin = [f for f in filas if f["grupo"].startswith("Residenciales Sin Subsidio")]
    con = [f for f in filas if f["grupo"].startswith("Residenciales Con Subsidio")]
    assert sin and con
    assert any(f["valores"] == [1882.6359] for f in filas)


def test_epe_rows_and_columns():
    tablas = run("epe")["tablas"]
    urb = next(f for f in tablas[0]["filas"] if "1AA" in f["concepto"])
    assert "1NA" in urb["concepto"] and "1PA" in urb["concepto"]
    assert urb["valores"] == [3944.25564, 247.6447, 270.56492, 366.81394, 440.80713]
    assert urb["columnas"][4] == "Excedente de 300 kWh/mes ($/kWh)"
    jub = next(f for f in tablas[0]["filas"] if "1DA" in f["concepto"])
    assert jub["columnas"] is None
    assert tablas[1]["filas"][0]["columnas"][1].startswith("Primeros 150")


def test_oceba_blocks_newest_first():
    from sources import _oceba_blocks
    page = ('Tarifas aprobadas por <a href="adjuntos/x/Reso_1.pdf">R</a>, vigentes a partir de consumos del 1 de Mayo de 2026. '
            'TARIFA APLICABLE A "DEMANDA RESIDENCIAL", ... <a href="adjuntos/x/A.pdf">EDEN S.A.</a> '
            'TARIFA APLICABLE A DEMANDA RESIDENCIAL CATEGORIZADA COMO TARIFA SOCIAL <a href="adjuntos/x/TS.pdf">EDEN S.A.</a> '
            'Tarifas aprobadas por <a href="adjuntos/x/Reso_2.pdf">R</a>, vigentes a&nbsp;partir de consumos del 1 de Junio de 2026. '
            'TARIFA APLICABLE A "DEMANDA RESIDENCIAL", ... <a href="adjuntos/x/B.pdf">EDEN S.A.&nbsp;</a>')
    blocks = _oceba_blocks(page, "EDEN")
    assert [b[2].rsplit("/", 1)[-1] for b in blocks] == ["B.pdf", "A.pdf"]
    assert blocks[0][0] == "1 de Junio de 2026"


@pytest.mark.parametrize("s,dec,v", [
    ("1.882,6359", None, 1882.6359), ("1,812.81", None, 1812.81), ("7562,923", None, 7562.923),
    ("$ 35.180,3356", None, 35180.3356), ("-87,9650", None, -87.965), ("29.710", ",", 29710.0),
    ("3193.22", ".", 3193.22), ("159,128", ",", 159.128), ("abc", None, None),
])
def test_parse_num(s, dec, v):
    assert parse_num(s, dec) == v
