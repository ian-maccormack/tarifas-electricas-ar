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


@builder("enersa")
def enersa(tablas):
    """Cumulative blocks; the extracted table can carry rows of the next column after the excedente."""
    t = next(t for t in tablas if re.search(r"T 1-R Uso residencial — Sin Subsidio$", t["titulo"]))
    fijo = _row(t["filas"], r"^Cargo fijo")
    esc, acc = [], 0
    for f in t["filas"]:
        m = re.match(r"^(Primeros|Siguientes|Excedente de) (\d+) kWh/mes$", f["concepto"])
        if not m:
            continue
        if m.group(1) == "Excedente de":
            if int(m.group(2)) != acc:
                raise ValueError("los escalones no suman el límite del excedente")
            esc.append([None, _val(f)])
            break
        acc += int(m.group(2))
        esc.append([acc, _val(f)])
    else:
        raise ValueError("sin excedente")
    return {"periodo": "mes", "criterio": "T1-R uso residencial sin subsidio",
            "categorias": [{"nombre": "T1-R", "hasta": None, "fijo": _val(fijo), "escalones": esc}]}


@builder("edemsa", "edeste")
def mendoza(tablas):
    """Mendoza: the bimonthly consumption sets the category; first column is 'sin SEF'."""
    filas, cats = tablas[0]["filas"], []
    for g in dict.fromkeys(f.get("grupo") for f in filas if re.match(r"^Residencial \d", f.get("grupo") or "")):
        rows = [f for f in filas if f.get("grupo") == g]
        m = re.search(r"[Hh]asta (\d+)|entre \d+ y (\d+)|[Mm]ayor o igual", g)
        if not m:
            raise ValueError(f"límite no reconocido: {g}")
        hasta = int(m.group(1) or m.group(2)) if (m.group(1) or m.group(2)) else None
        cats.append({"nombre": g, "hasta": hasta, "fijo": _val(_row(rows, r"^Cargo Fijo$")),
                     "escalones": [[None, _val(_row(rows, r"^Cargo Variable$"))]]})
    return {"periodo": "bimestre", "criterio": "Residencial sin SEF (primera columna)", "categorias": cats}


@builder("ejesa")
def ejesa(tablas):
    """Jujuy: the monthly consumption sets the category; the energy price is uso de red + consumo de energía."""
    cats = []
    for f in tablas[0]["filas"]:
        c = f["concepto"]
        if c.startswith("RE ") or len(f["valores"]) != 3:
            continue
        m = re.search(r"Primeros (\d+)|menor o igual a (\d+)|Mayores a", c)
        if not m:
            raise ValueError(f"límite no reconocido: {c}")
        hasta = int(m.group(1) or m.group(2)) if (m.group(1) or m.group(2)) else None
        red, energia = f["valores"][1], f["valores"][2]
        cats.append({"nombre": c.split(" ")[0], "hasta": hasta, "fijo": f["valores"][0],
                     "escalones": [[None, red + energia if red is not None and energia is not None else None]]})
    return {"periodo": "mes", "criterio": "T1 residencial, cargos plenos (uso de red + energía)", "categorias": cats}


@builder("ape")
def ape(tablas):
    """La Pampa: the monthly consumption sets the category. Fixed part = cargo fijo + cargo por potencia
    + fondo cooperativo; energy = compra de energía (all kWh) + VAD in cumulative blocks. Column 0
    is the 'precio de venta máximo' (without the national subsidy)."""
    filas, cats = tablas[0]["filas"], []
    for g in dict.fromkeys(f.get("grupo") for f in filas if f.get("grupo")):
        rows = [f for f in filas if f.get("grupo") == g]
        m = re.findall(r"iguales a (\d+) kWh", g)
        hasta = int(m[-1]) if m else (None if re.search(r"mayores a \d+ kWh/mes$", g) else -1)
        if hasta == -1:
            raise ValueError(f"límite no reconocido: {g}")
        parts = [_val(_row(rows, rx)) for rx in (r"^Cargo Fijo$", r"^Cargo por Potencia$", r"^Fondo Cooperativo")]
        compra = _val(_row(rows, r"^Costo Compra de Energ"))
        esc, acc = [], 0
        for f in rows:
            mm = re.match(r"^VAD (primeros|siguientes|excedente de) (\d+) kWh$", f["concepto"])
            if not mm:
                continue
            v = _val(f)
            precio = compra + v if compra is not None and v is not None else None
            if mm.group(1) == "excedente de":
                if int(mm.group(2)) != acc:
                    raise ValueError("los tramos VAD no suman el excedente")
                esc.append([None, precio])
            else:
                acc += int(mm.group(2))
                esc.append([acc, precio])
        if esc and esc[-1][0] is not None:
            esc.append([None, None])  # beyond the last block the document gives no price for this category
        cats.append({"nombre": g, "hasta": hasta, "fijo": sum(parts) if None not in parts else None,
                     "escalones": esc or [[None, None]]})
    return {"periodo": "mes", "criterio": "T1R Nivel 1, precio de venta máximo", "categorias": cats}


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


# ---- T2 / T3 (medianas y grandes demandas) ----
DEMANDA = {}


def demanda_builder(*ids):
    def deco(fn):
        for i in ids:
            DEMANDA[i] = fn
        return fn
    return deco


def _pick(rows, rx):
    f = next((f for f in rows if re.search(rx, f["concepto"])), None)
    return f["valores"][0] if f and f["valores"] else None


@demanda_builder("eden", "edes")
def oceba_demanda(tablas):
    """OCEBA: T2 (10 to <50 kW) and T3 (>= 50 kW, energy split at 300 kW), usuarios finales only."""
    tarifas = []
    t2 = next(t for t in tablas if t["titulo"].startswith("T2 -"))
    for v in ("BT", "MT"):
        rows = [f for f in t2["filas"] if (f.get("grupo") or "").startswith(f"T2{v}")]
        tarifas.append({"nombre": f"T2{v}", "tension": v, "desde_kw": 10, "hasta_kw": 50,
                        "fijo": _pick(rows, r"^CARGO FIJO$"),
                        "potencia": [["Potencia en pico", _pick(rows, r"POTENCIA EN PICO")],
                                     ["Potencia fuera de pico", _pick(rows, r"POTENCIA FUERA PICO")]],
                        "energia": {"pico": _pick(rows, r"ENERG.A DEMANDADA EN PICO"),
                                    "fuera_pico": _pick(rows, r"FUERA DE PICO")}})
    for v in ("BT", "MT"):
        t3 = next((t for t in tablas if t["titulo"].startswith(f"T3{v} ")), None)
        if t3 is None:
            continue
        fixed = [f for f in t3["filas"] if re.search(r"\(Usuarios Finales\)", f.get("grupo") or "")]
        for desde, hasta, rx in ((50, 300, r"^USUARIOS FINALES Suministros entre 50 y 300"),
                                 (300, None, r"^USUARIOS FINALES Suministros Mayor o igual a 300")):
            rows = [f for f in t3["filas"] if re.search(rx, f.get("grupo") or "")]
            tarifas.append({"nombre": f"T3{v} ({desde}{'–' + str(hasta) if hasta else '+'} kW)", "tension": v,
                            "desde_kw": desde, "hasta_kw": hasta, "fijo": _pick(fixed, r"^CARGO FIJO$"),
                            "potencia": [["Potencia en pico", _pick(fixed, r"POTENCIA EN PICO")],
                                         ["Potencia fuera de pico", _pick(fixed, r"POTENCIA FUERA PICO")]],
                            "energia": {k: _pick(rows, rf"DEMANDADA EN {k.upper()}") for k in ("pico", "resto", "valle")}})
    return {"criterio": "Usuarios finales; límites de potencia según el cuadro OCEBA", "tarifas": tarifas}


@demanda_builder("edenor", "edesur")
def enre_demanda(tablas):
    """ENRE: the cuadro splits T3 at 300 kW; the T2/T3 limit (50 kW) comes from the ENRE tariff regime."""
    tarifas = []
    for t in tablas:
        if "PEAJE" in t["titulo"]:
            break
        m2 = re.match(r"^Tarifa 2\b", t["titulo"])
        m3 = re.match(r"^Tarifa 3 - (BT|MT|AT) ?([<>]) ?300", t["titulo"])
        if not (m2 or m3) or any(x["nombre"] == t["titulo"].split(" — ")[0] for x in tarifas):
            continue
        rows = t["filas"]
        pot = [["Potencia contratada", _pick(rows, r"Potencia Contratada")],
               ["Potencia adquirida", _pick(rows, r"Potencia Adquirida")]]
        if m2:
            tarifas.append({"nombre": "Tarifa 2", "tension": None, "desde_kw": 10, "hasta_kw": 50,
                            "fijo": _pick(rows, r"^Cargo Fijo$"), "potencia": pot,
                            "energia": {"unica": _pick(rows, r"^Cargo [Vv]ariable$")}})
        else:
            low = m3.group(2) == "<"
            tarifas.append({"nombre": t["titulo"].split(" — ")[0], "tension": m3.group(1),
                            "desde_kw": 50 if low else 300, "hasta_kw": 300 if low else None,
                            "fijo": _pick(rows, r"^Cargo Fijo$"), "potencia": pot,
                            "energia": {k: _pick(rows, rf"^Cargo Variable {k.capitalize()}$") for k in ("pico", "resto", "valle")}})
    return {"criterio": "Cuadro ENRE; T2 de 10 a 50 kW y T3 desde 50 kW según el régimen tarifario ENRE (no figura en el cuadro)",
            "tarifas": tarifas}


def build_demanda(entry):
    fn = DEMANDA.get(entry["id"])
    if not fn or entry.get("estado") != "ok" or entry.get("ocr"):
        return None
    try:
        d = fn(entry["tablas"])
    except Exception:
        return None
    return d if d["tarifas"] else None


def match_demanda(d, tension, kw):
    return next((t for t in d["tarifas"] if t["tension"] in (None, tension) and kw >= t["desde_kw"]
                 and (t["hasta_kw"] is None or kw < t["hasta_kw"])), None)


def cost_demanda(d, tension, kw, kwh, pico, valle):
    """Monthly cost without taxes; every power charge is applied to the kW entered (mirrors app.js)."""
    t = match_demanda(d, tension, kw)
    if t is None:
        return None
    e = t["energia"]
    if "unica" in e:
        reparto = {"unica": 1}
    elif "fuera_pico" in e:
        reparto = {"pico": pico, "fuera_pico": 1 - pico}
    else:
        reparto = {"pico": pico, "resto": 1 - pico - valle, "valle": valle}
    parts = [t["fijo"]] + [None if p is None else p * kw for _, p in t["potencia"]]
    parts += [None if e.get(k) is None else e[k] * kwh * share for k, share in reparto.items()]
    return None if None in parts else sum(parts)

