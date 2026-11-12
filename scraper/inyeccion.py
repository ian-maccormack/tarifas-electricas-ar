"""Price the distributor pays for energy injected by a user-generator ($/kWh), read from the
official tariff text. Only distributors whose table states it unambiguously; the rest stay None."""
import os
import re

TEXTOS = os.path.join(os.path.dirname(__file__), "..", "site", "data", "textos")


def _n(s):
    return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)


def _first(pat, text, flags=re.I | re.S):
    m = re.search(pat, text, flags)
    return _n(m.group(1)) if m else None


def _edersa(t):
    m = re.search(r"Con Subsidio\s+Sin Subsidio.*?TARIFA INYECCI[ÓO]N \$/kWh ([\d.,]+) ([\d.,]+) ([\d.,]+) ([\d.,]+)", t, re.S)
    return {"residencial": _n(m.group(3)) if m and m.group(3) == m.group(4) else None,
            "detalle": "Tarifa residencial sin subsidio, «Tarifa inyección»"}


def _esj(t):
    i = t.find("Energía Inyectada")
    if i < 0:
        return {}
    v = re.findall(r"Cargo variable por energía \$/kWh ([\d.]+)", t[i:i + 4000])
    return {"residencial": _n(v[0]) if v else None, "no_residencial": _n(v[1]) if len(v) > 1 else None,
            "detalle": "«Valores tarifarios a reconocer al usuario generador por la energía inyectada», T1 residencial y general"}


def _epec(t):
    return {"residencial": _first(r"Residenciales Sin Subsidio Energ[ée]tico Focalizado, y Residenciales Con Subsidio.*?\$ ([\d.,]+)", t),
            "detalle": "«Por cada kWh inyectado - Residenciales Sin Subsidio Energético Focalizado»"}


def _edelar(t):
    i = t.find("TARIFA POR LA ENERGIA INYECTADA")
    s = t[i:i + 800] if i >= 0 else ""
    return {"residencial": _first(r"Residencial No Subsidiado \$/kWh ([\d.,]+)", s),
            "no_residencial": _first(r"\nGeneral \$/kWh ([\d.,]+)", s),
            "detalle": "«Tarifa por la energía inyectada a la red de distribución»: residencial no subsidiado y general"}


def _secheep(t):
    return {"residencial": _first(r"\|\s*0112-0113\s*\|\s*\|\s*Por cada KWh inyectado a la red\s*\|\s*\$/KWh\s*\|\s*([\d.]+)", t),
            "no_residencial": _first(r"<50KW[^|\n]*\|\s*Por cada KWh inyectado a la red\s*\|\s*\$/KWh\s*\|\s*([\d.]+)", t),
            "detalle": "«Usuario-Generador»: residencial sin SEF y no residencial menor de 50 kW"}


def _edesa(t):
    v = _first(r"T_BN_SOL\s*\$ ?/ ?kwh\s*([\d.,]+)", t)
    return {"residencial": v, "no_residencial": v, "detalle": "«Tarifa Balance Neto - Origen Solar» (T_BN_SOL)"}


READERS = {"edersa": _edersa, "esj": _esj, "epec": _epec, "edelar": _edelar, "secheep": _secheep, "edesa": _edesa}


def read_text(path):
    return re.sub(r"[ \t\u00a0]+", " ", open(path, encoding="utf-8").read())


def build_inyeccion(entry):
    fn = READERS.get(entry["id"])
    path = os.path.join(TEXTOS, entry["id"] + ".txt")
    if not fn or entry.get("ocr") or not os.path.exists(path):
        return None
    r = fn(read_text(path))
    if r.get("residencial") is None and r.get("no_residencial") is None:
        return None
    r.update(unidad="$/kWh", documento=(entry.get("documento") or {}).get("url"))
    return r
