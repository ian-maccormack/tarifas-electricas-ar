"""Residential tariff schedules for the cost simulator.

Each builder reads the already-extracted tables of one distributor (no new numbers are
introduced) and returns {"periodo", "criterio", "categorias": [...]}; a category is
{"hasta": kWh per billing period or None (open-ended), "fijo": $, "escalones": [[hasta, $/kWh], ...]}.
Escalón limits are cumulative kWh within the period. Any value that is missing stays None and
the site then leaves the result empty. Distributors without a builder are not simulated."""
import re

BUILDERS = {}


def builder(*ids):
    def deco(fn):
        for i in ids:
            BUILDERS[i] = fn
        return fn
    return deco


def _limit(text):
    """Upper kWh limit of a category described in words; None if open-ended."""
    t = text.lower()
    m = re.search(r"(?:inferior|menor)(?:es)?(?: [oe] igual)?(?: a)? (\d[\d.]*)\s*kwh", t) or \
        re.search(r"hasta (\d[\d.]*)\s*kwh", t)
    if m:
        return int(m.group(1).replace(".", ""))
    if re.search(r"(mayor|superior|excedente|más de)", t):
        return None
    raise ValueError(f"límite no reconocido: {text}")


def _row(filas, rx):
    for f in filas:
        if re.search(rx, f["concepto"], re.I):
            return f
    return None


def _val(f, col=0):
    if f is None or col >= len(f["valores"]):
        return None
    return f["valores"][col]


@builder("edenor", "edesur")
def enre(tablas):
    cats = []
    for t in tablas:
        if not re.match(r"R\d+ — Tarifa 1 - R sin subsidio$", t["titulo"]):
            continue
        fijo, var = _row(t["filas"], r"^Cargo Fijo"), _row(t["filas"], r"^Cargo Variable")
        m = re.search(r"(\d+)\s*-\s*(\d+)", fijo["concepto"]) if fijo else None
        cats.append({"nombre": t["titulo"].split(" ")[0], "hasta": int(m.group(2)) if m else None,
                     "fijo": _val(fijo), "escalones": [[None, _val(var)]]})
    return {"periodo": "mes", "criterio": "Tarifa 1-R sin subsidio", "categorias": cats}


def _grouped(tablas, fijo_rx, var_rx, group_rx, col=0, periodo="mes", criterio=""):
    cats, seen = [], set()
    for t in tablas:
        for f in t["filas"]:
            g = f.get("grupo") or ""
            if g in seen or not re.search(group_rx, g):
                continue
            seen.add(g)
            filas = [x for x in t["filas"] if x.get("grupo") == g]
            cats.append({"nombre": g, "hasta": _limit(g), "fijo": _val(_row(filas, fijo_rx), col),
                         "escalones": [[None, _val(_row(filas, var_rx), col)]]})
    return {"periodo": periodo, "criterio": criterio, "categorias": cats}


@builder("refsa")
def refsa(tablas):
    return _grouped(tablas, r"^Cargo Fijo", r"^Cargo Variable", r"^T\.1-R\d", criterio="T1-R (sin subsidio)")


@builder("epen")
def epen(tablas):
    return _grouped(tablas, r"^Cargo fijo", r"SIN SUBSIDIO", r"^T1-R\d", criterio="T1-R sin subsidio")


@builder("edese")
def edese(tablas):
    return _grouped(tablas, r"^Cargo fijo", r"^Cargo variable", r"^T1 R\d", periodo="bimestre",
                    criterio="T1 Residencial")


@builder("esj")
def esj(tablas):
    t = tablas[0]
    filas = [f for f in t["filas"] if f.get("grupo") == "Sin SEN"]
    fijo, var = _row(filas, r"^Cargo fijo"), _row(filas, r"^Cargo variable")
    cats = []
    for i, col in enumerate(fijo["columnas"]):
        hasta = None if re.search(r">|más|mayor", col, re.I) else int(re.findall(r"\d+", col)[-1])
        cats.append({"nombre": col, "hasta": hasta, "fijo": _val(fijo, i), "escalones": [[None, _val(var, i)]]})
    if cats and cats[-1]["hasta"] is not None:
        cats.append({"nombre": f"más de {cats[-1]['hasta']} kWh", "hasta": None, "fijo": None, "escalones": [[None, None]]})
    return {"periodo": "bimestre", "criterio": "Uso residencial sin SEN", "categorias": cats}


@builder("edersa")
def edersa(tablas):
    t = tablas[0]
    cats = []
    for g in dict.fromkeys(f.get("grupo") for f in t["filas"]):
        filas = [f for f in t["filas"] if f.get("grupo") == g]
        fijo = _row(filas, r"^CARGO FIJO")
        col = fijo["columnas"].index("Sin Subsidio (m)") if fijo and fijo.get("columnas") else None
        excedente = _row(filas, r"excedente")
        var = _row(filas, r"^CARGO VARIABLE$")
        cats.append({"nombre": g, "hasta": _limit(g), "fijo": _val(fijo, col) if col is not None else None,
                     # the excedente threshold is not in the extracted table, so that category stays incomplete
                     "escalones": [[None, _val(var, col) if var and col is not None and not excedente else None]]})
    return {"periodo": "bimestre", "criterio": "Sin subsidio, monofásico", "categorias": cats}


@builder("dpec")
def dpec(tablas):
    filas = tablas[0]["filas"][:3]
    fijo, base, exc = filas[0], filas[1], filas[2]
    m = re.search(r"Excedente de (\d+) kWh/bim", exc["concepto"])
    ok = re.search(r"NO BONIFICADOS", base["concepto"]) and m
    return {"periodo": "bimestre", "criterio": "Urbano no bonificado, tarifa sin bonificación",
            "categorias": [{"nombre": "Pequeñas demandas residenciales", "hasta": None, "fijo": _val(fijo),
                            "escalones": [[int(m.group(1)), _val(base)], [None, _val(exc)]] if ok else [[None, None]]}]}


@builder("eden", "edes")
def oceba(tablas):
    """Buenos Aires T1R: the monthly consumption sets the category, whose charges apply to all kWh."""
    filas, cats = tablas[0]["filas"], []
    for f in filas:
        m = re.match(r"^CARGO VARIABLE (R\d+)\b(.*)$", f["concepto"])
        if not m:
            continue
        lim = re.search(r"≤\s*(\d+)\)", m.group(2))
        if not lim and not re.search(r">\s*\d+\)", m.group(2)):
            raise ValueError(f"límite no reconocido: {f['concepto']}")
        cats.append({"nombre": m.group(1), "hasta": int(lim.group(1)) if lim else None,
                     "fijo": _val(_row(filas, rf"^CARGO FIJO {m.group(1)}$")), "escalones": [[None, _val(f)]]})
    return {"periodo": "mes", "criterio": "T1R residencial", "categorias": cats}


@builder("epe")
def epe(tablas):
    """EPE: monthly values in cumulative blocks (Primeros / Siguientes / Excedente)."""
    for t in tablas:
        f = next((f for f in t["filas"] if re.search(r"\b1AA\b", f["concepto"]) and f.get("columnas")), None)
        if not f:
            continue
        esc, acc = [], 0
        for col, precio in zip(f["columnas"][1:], f["valores"][1:]):
            m = re.match(r"(Primeros|Siguientes) (\d+)", col)
            if m:
                acc += int(m.group(2))
                esc.append([acc, precio])
            else:
                esc.append([None, precio])
        return {"periodo": "mes", "criterio": "Residencial urbano sin subsidio (1AA)",
                "categorias": [{"nombre": "1AA Urbano", "hasta": None, "fijo": f["valores"][0], "escalones": esc}]}
    return {"periodo": "mes", "criterio": "", "categorias": []}


def build(entry):
    fn = BUILDERS.get(entry["id"])
    if not fn or entry.get("estado") != "ok" or entry.get("ocr"):
        return None
    try:
        sim = fn(entry["tablas"])
    except Exception:
        return None
    return sim if sim["categorias"] else None


def cost(sim, kwh_mes):
    """Monthly cost without taxes, or None if any needed value is missing (mirrors app.js)."""
    k = kwh_mes * (2 if sim["periodo"] == "bimestre" else 1)
    cat = next((c for c in sim["categorias"] if c["hasta"] is None or k <= c["hasta"]), None)
    if cat is None or cat["fijo"] is None:
        return None
    total, prev = cat["fijo"], 0
    for hasta, precio in cat["escalones"]:
        tramo = max(0, min(k, hasta if hasta is not None else k) - prev)
        if tramo and precio is None:
            return None
        total += tramo * (precio or 0)
        prev = hasta if hasta is not None else k
        if prev >= k:
            break
    return total / (2 if sim["periodo"] == "bimestre" else 1)
