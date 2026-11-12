import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scraper"))
from inyeccion import READERS, TEXTOS, read_text


def read(i):
    return READERS[i](read_text(os.path.join(TEXTOS, i + ".txt")))


def test_values_are_positive_and_below_energy_price():
    for i in READERS:
        r = read(i)
        vals = [v for v in (r.get("residencial"), r.get("no_residencial")) if v is not None]
        assert vals, i
        assert all(0 < v < 1000 for v in vals), (i, vals)
