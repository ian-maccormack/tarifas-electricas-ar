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
        # the "excedente (*)" row only applies to the 'con subsidio' columns ("(*) Con Subsidio Excedente ...")
        var = _row(filas, r"^CARGO VARIABLE( BASE)?$")
        cats.append({"nombre": g, "hasta": _limit(g), "fijo": _val(fijo, col) if col is not None else None,
                     "escalones": [[None, _val(var, col) if var and col is not None else None]]})
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
    return _enersa(tablas, "Sin Subsidio", "T1-R uso residencial sin subsidio")


def _enersa(tablas, col, criterio):
    t = next(t for t in tablas if re.search(rf"T 1-R Uso residencial — {col}$", t["titulo"]))
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
    return {"periodo": "mes", "criterio": criterio,
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


def cost(sim, kwh_mes, mes=None):
    """Monthly cost without taxes, or None if any needed value is missing (mirrors app.js).
    A block limit "base" is the month's consumo base (sim["base_mes"], needs `mes` 1-12)."""
    k = kwh_mes * (2 if sim["periodo"] == "bimestre" else 1)
    cat = next((c for c in sim["categorias"] if c["hasta"] is None or k <= c["hasta"]), None)
    if cat is None or cat["fijo"] is None:
        return None
    total, prev = cat["fijo"], 0
    for hasta, precio in cat["escalones"]:
        if hasta == "base":
            if not mes or not sim.get("base_mes"):
                return None
            hasta = sim["base_mes"][mes - 1]
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


def _n(s):
    return re.sub(r"\s+", "", s or "").lower()


def _pk(rows, rx, col=0, grupo=None):
    """Value of the first row whose label (spaces removed, lowercase) matches rx; grupo='' means no group."""
    for f in rows:
        g = _n(f.get("grupo"))
        if grupo is not None and (bool(g) if grupo == "" else not re.search(grupo, g)):
            continue
        if re.search(rx, _n(f["concepto"])):
            return f["valores"][col] if col < len(f["valores"]) else None
    return None


TENSION = {"baja": "BT", "media": "MT", "alta": "AT"}
FRANJAS3 = ("pico", "resto", "valle")


def _t(nombre, tension, desde, hasta, fijo, potencia, energia):
    return {"nombre": nombre, "tension": tension, "desde_kw": desde, "hasta_kw": hasta, "fijo": fijo,
            "potencia": potencia, "energia": energia}


@demanda_builder("epen")
def epen_demanda(tablas):
    out, seen = [], set()
    for t in tablas:
        m = re.match(r"^(t2|t3)\(.*?—servicioen(baja|media|alta)tensi", _n(t["titulo"]))
        if not m or m.groups() in seen:
            continue
        seen.add(m.groups())
        ten, rows = TENSION[m.group(2)], t["filas"]
        if m.group(1) == "t2":
            out.append(_t(f"T2 {ten}", ten, 10, 50, 0.0,
                          [["Capacidad de suministro contratada", _pk(rows, r"capacidaddesuministrocontratada")]],
                          {"unica": _pk(rows, r"variableporenerg")}))
            continue
        e = {"pico": r"energ.*horaspico", "resto": r"energ.*horasrestante", "valle": r"energ.*horasvalle"}
        for desde, hasta, pot_g, en_g in ((50, 300, "", r"menora300"), (300, None, r"resto$", r"resto$")):
            out.append(_t(f"T3 {ten} ({'< 300' if hasta else '≥ 300'} kW)", ten, desde, hasta, 0.0,
                          [["Capacidad en horas pico", _pk(rows, r"enhoraspico$", grupo=pot_g)],
                           ["Capacidad en horas fuera de pico", _pk(rows, r"fueradepico$", grupo=pot_g)]],
                          {k: _pk(rows, rx, grupo=en_g) for k, rx in e.items()}))
    return {"criterio": "Límites de potencia del cuadro EPEN; el cuadro no tiene cargo fijo en T2/T3; T3 ≥ 300 kW: categoría 'Resto'",
            "tarifas": out}


@demanda_builder("refsa")
def refsa_demanda(tablas):
    out = []
    for t in tablas:
        m = re.search(r"grandesdemandasen(baja|media)tensi.*>=300", _n(t["titulo"]))
        if not m:
            continue
        ten, rows = TENSION[m.group(1)], t["filas"]
        out.append(_t(f"T3 {ten} ≥ 300 kW", ten, 300, None, 0.0,
                      [["Capacidad en horas de pico", _pk(rows, r"horasdepico$")],
                       ["Capacidad en horas fuera de pico", _pk(rows, r"horasfueradepico$")]],
                      {"pico": _pk(rows, r"punta$"), "resto": _pk(rows, r"restantes$"), "valle": _pk(rows, r"valle")}))
    return {"criterio": "Solo T3 ≥ 300 kW: el cuadro no indica dónde termina T2 y empieza T3 (< 300 kW); sin cargo fijo en el cuadro",
            "tarifas": out}


@demanda_builder("esj")
def esj_demanda(tablas):
    out = []
    t2 = next((t for t in tablas if t["titulo"].startswith("Tarifa N°2")), None)
    if t2:
        for col, (n, desde, hasta) in enumerate((("T2 SMP", 10, 20), ("T2 CMP", 20, 50))):
            pot = _pk(t2["filas"], r"^porcapacidad", col)
            out.append(_t(n, None, desde, hasta, _pk(t2["filas"], r"^cargofijo", col),
                          [["Capacidad de suministro contratada", pot]] if pot is not None or col else [],
                          {"unica": _pk(t2["filas"], r"^cargovariable", col)}))
    t3 = next((t for t in tablas if t["titulo"].startswith("Tarifa N°3")), None)
    if t3:
        rows = t3["filas"]
        for ten, col in (("BT", 0), ("AT", 4)):
            for desde, hasta, g in ((50, 300, r"menoresa300"), (300, None, r"mayoresoigualesa300kw-mes$")):
                out.append(_t(f"T3 {ten} ({'< 300' if hasta else '≥ 300'} kW)", ten, desde, hasta, _pk(rows, r"^cargofijo", col, ""),
                              [["Máxima capacidad contratada", _pk(rows, r"^pormáximacapacidad", col, "")],
                               ["Capacidad contratada en horas de punta", _pk(rows, r"^porcapacidad.*punta$", col, g)]],
                              {"pico": _pk(rows, r"^enhorasdepunta", col, g), "resto": _pk(rows, r"^enhorasrestantes", col, g),
                               "valle": _pk(rows, r"^enhorasdevalle", col, g)}))
    return {"criterio": "T2 SMP/CMP y T3 en BT y AT; T3 en media tensión queda afuera porque el cuadro no explica las variantes 'R' y 'B'",
            "tarifas": out}


@demanda_builder("dpec")
def dpec_demanda(tablas):
    out = []
    for t in tablas:
        ti = t["titulo"]
        m = re.search(r"desde (\d+) kW(?: (?:no mayor|y menor) a (\d+) kW)?", ti)
        if not m or not re.match(r"(Medianas|Grandes) Demandas", ti):
            continue
        mt = re.search(r"Suministro en (\w+) Tensi", ti)
        ten = TENSION[mt.group(1).lower()] if mt else None
        rows = t["filas"]
        e = ({"unica": _pk(rows, r"portodoelconsumo")} if _pk(rows, r"portodoelconsumo") is not None
             else {k: _pk(rows, rf"^horas{k}") for k in FRANJAS3})
        out.append(_t(ti.split(" — ")[0] + (f" {ten}" if ten else ""), ten, int(m.group(1)),
                      int(m.group(2)) if m.group(2) else None, 0.0,
                      [["Cargo fijo por potencia", _pk(rows, r"cargofijoporpotencia")]], e))
    return {"criterio": "Potencia convenida según el cuadro DPEC; el cargo fijo del cuadro es por kW (no hay cargo fijo mensual)",
            "tarifas": out}


@demanda_builder("edemsa", "edeste")
def mendoza_demanda(tablas):
    t = next((t for t in tablas if t["titulo"].startswith("Tarifa 2 (T2)")), None)
    out = []
    if t:
        rows = t["filas"]
        for ten, c0 in (("BT", 0), ("MT", 4), ("AT", 8)):
            for k, (desde, hasta) in enumerate(((10, 300), (300, None))):
                col = c0 + k
                out.append(_t(f"T2 R {ten} ({'10–300' if hasta else '≥ 300'} kW)", ten, desde, hasta, _pk(rows, r"comercializaci", col),
                              [["Uso de red", _pk(rows, r"^usodered", col)], ["Consumo de potencia", _pk(rows, r"^consumodepotencia", col)]],
                              {k2: _pk(rows, rf"^{k2}\(", col) for k2 in FRANJAS3}))
    return {"criterio": "T2 conectado a la red de distribución (columnas 'R'); no incluye suministros en bornes de transformador ('B')",
            "tarifas": out}


@demanda_builder("ejesa")
def ejesa_demanda(tablas):
    out = []
    for t in tablas:
        m = re.match(r"^(T2|T3 BT|T3 MT) - ", t["titulo"])
        if not m:
            continue
        rows = t["filas"]
        e = {"pico": r"horaspunta", "resto": r"horasresto", "valle": r"horasvalle"}
        if m.group(1) == "T2":
            out.append(_t("T2", None, 15, 50, _pk(rows, r"^cargofijo"), [["Uso de red", _pk(rows, r"usodered")]],
                          {k: _pk(rows, rx) for k, rx in e.items()}))
            continue
        ten = m.group(1)[-2:]
        for desde, hasta, g in ((50, 300, r"^menora300"), (300, None, r"^mayoroiguala300")):
            out.append(_t(f"T3 {ten} ({'< 300' if hasta else '≥ 300'} kW)", ten, desde, hasta, _pk(rows, r"^cargofijo", grupo=g),
                          [["Uso de red", _pk(rows, r"usodered", grupo=g)]], {k: _pk(rows, rx, grupo=g) for k, rx in e.items()}))
    return {"criterio": "Cargos plenos; T2 desde 15 kW según el cuadro (de 10 a 15 kW no hay tarifa en el cuadro)", "tarifas": out}


@demanda_builder("edesal")
def edesal_demanda(tablas):
    out = []
    for t in tablas:
        m = re.search(r"Usuarios de la Distribuidora (< 300|≥ 300) kW", t["titulo"])
        if not m:
            continue
        low, rows = m.group(1) == "< 300", t["filas"]
        cols = rows[0]["columnas"] or []
        for ten, name in (("BT", "T2 BT"), ("MT", "T2 MT13,2"), ("AT", "T2 AT")):
            if name not in cols:
                continue
            c = cols.index(name)
            out.append(_t(f"{name} ({'< 300' if low else '≥ 300'} kW)", ten, 10 if low else 300, 300 if low else None,
                          _pk(rows, r"^cargocomercial", c),
                          [["Uso de la red", _pk(rows, r"^cargoporusodelared", c)], ["Consumo de potencia", _pk(rows, r"^cargoporconsumopotencia", c)]],
                          {k: _pk(rows, rf"energíaenhs\.{k}", c) for k in FRANJAS3}))
    return {"criterio": "T2 BT, MT 13,2 kV y AT (sin variantes de riego ni 33 kV); cuadro de 06/2026", "tarifas": out}


@demanda_builder("edese")
def edese_demanda(tablas):
    out = []
    t2 = next((t for t in tablas if t["titulo"].startswith("Tarifa N°2")), None)
    if t2:
        out.append(_t("Tarifa N°2", None, 10, 50, 0.0, [["Capacidad de suministro contratada", _pk(t2["filas"], r"capacidaddesuministro")]],
                      {"unica": _pk(t2["filas"], r"cargovariable")}))
    for t in tablas:
        m = re.match(r"Tarifa N°3 \(Grandes Demandas\) — T3-(BT|MT)", t["titulo"])
        if not m:
            continue
        for desde, hasta, g in ((50, 300, r"<300"), (300, None, r"≥300")):
            rows = t["filas"]
            out.append(_t(f"T3-{m.group(1)} ({'< 300' if hasta else '≥ 300'} kW)", m.group(1), desde, hasta, 0.0,
                          [["Capacidad en punta", _pk(rows, r"enpunta$", grupo=g)], ["Capacidad fuera de punta", _pk(rows, r"fueradepunta$", grupo=g)]],
                          {"pico": _pk(rows, r"hs\.pico", grupo=g), "resto": _pk(rows, r"hs\.restantes", grupo=g),
                           "valle": _pk(rows, r"hs\.valle", grupo=g)}))
    return {"criterio": "Límites de potencia del cuadro EDESE; el cuadro no tiene cargo fijo en T2/T3", "tarifas": out}


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


# ---- 'Con subsidio' mode: only where the cuadro prints the subsidised charges and their consumption limits ----
SUB_BUILDERS = {}

def sub_builder(*ids):
    def deco(fn):
        for i in ids:
            SUB_BUILDERS[i] = fn
        return fn
    return deco


@sub_builder("enersa")
def enersa_sub(tablas):
    """The 'Con Subsidio Nacional' column already prints the subsidised blocks and where full price starts."""
    return _enersa(tablas, "Con Subsidio Nacional", "T1-R uso residencial con subsidio nacional")


@sub_builder("edersa")
def edersa_sub(tablas):
    """'Con Subsidio (m)': R1 one price; R2 base price up to the tope, excedente above it."""
    t = tablas[0]
    tope = t.get("tope_subsidio")
    cats = []
    for g in dict.fromkeys(f.get("grupo") for f in t["filas"]):
        filas = [f for f in t["filas"] if f.get("grupo") == g]
        fijo = _row(filas, r"^CARGO FIJO")
        col = fijo["columnas"].index("Con Subsidio (m)")
        var, exc = _row(filas, r"^CARGO VARIABLE( BASE)?$"), _row(filas, r"^CARGO VARIABLE excedente")
        esc = [[tope, _val(var, col)], [None, _val(exc, col)]] if exc else [[None, _val(var, col)]]
        if exc and not tope:
            esc = [[None, None]]
        cats.append({"nombre": g, "hasta": _limit(g), "fijo": _val(fijo, col), "escalones": esc})
    return {"periodo": "bimestre", "criterio": f"Con subsidio, monofásico (excedente desde {tope} kWh/bim)",
            "categorias": cats}


@sub_builder("edenor", "edesur")
def enre_sub(tablas):
    """'Tarifa 1 - R con subsidio': the consumption sets the category; the consumo base is billed at the
    subsidised price and the rest at the excedente price. The consumo base depends on the month."""
    cats, on, base = [], False, None
    for t in tablas:
        if re.match(r"R\d+ — Tarifa 1 - R con subsidio$", t["titulo"]):
            on = True
        elif not re.match(r"R\d+$", t["titulo"]):  # later tables of the block lose the subtitle
            on = False
        if not on:
            continue
        base = base or t.get("consumo_base")
        fijo = _row(t["filas"], r"^Cargo Fijo")
        m = re.search(r"(\d+)\s*-\s*(\d+)", fijo["concepto"]) if fijo else None
        b, ex = _row(t["filas"], r"consumo base$"), _row(t["filas"], r"excedente a consumo base")
        esc = [["base", _val(b)], [None, _val(ex)]] if b and ex else [[None, _val(_row(t["filas"], r"^Cargo Variable"))]]
        cats.append({"nombre": t["titulo"].split(" ")[0], "hasta": int(m.group(2)) if m else None,
                     "fijo": _val(fijo), "escalones": esc})
    if not base:
        raise ValueError("sin consumo base por mes")
    return {"periodo": "mes", "criterio": "Tarifa 1-R con subsidio (consumo base según el mes)",
            "base_mes": base, "categorias": cats}


@sub_builder("edemsa", "edeste")
def mendoza_sub(tablas):
    """'Con SEF' (second value). Residencial 2 and 3 split it into base and excedente with different fixed
    charges and the cuadro does not say which fixed charge applies, so they stay empty."""
    sim = mendoza(tablas)
    filas = tablas[0]["filas"]
    for c in sim["categorias"]:
        rows = [f for f in filas if f.get("grupo") == c["nombre"]]
        fijo, var = _row(rows, r"^Cargo Fijo$"), _row(rows, r"^Cargo Variable$")
        ok = fijo and var and len(fijo["valores"]) == 3 and len(var["valores"]) == 3
        c["fijo"] = _val(fijo, 1) if ok else None
        c["escalones"] = [[None, _val(var, 1) if ok else None]]
    sim["criterio"] = "Residencial con SEF (solo Residencial 1)"
    return sim


def build_subsidio(entry):
    fn = SUB_BUILDERS.get(entry["id"])
    if not fn or entry.get("estado") != "ok" or entry.get("ocr"):
        return None
    try:
        sim = fn(entry["tablas"])
    except Exception:
        return None
    return sim if sim["categorias"] else None


# ---- OCR documents: only used when the visitor turns on "Incluir OCR" ----
OCR_BUILDERS = {}


def ocr_builder(*ids):
    def deco(fn):
        for i in ids:
            OCR_BUILDERS[i] = fn
        return fn
    return deco


def _first_table(tablas, rx):
    return next((t for t in tablas if any(re.search(rx, f["concepto"]) for f in t["filas"])), None)


@ocr_builder("edesa")
def edesa_ocr(tablas):
    """Anexo I: T1R1/T1R2 categories by monthly consumption, one fixed and one variable charge each."""
    rx = r"^T[1I][IL]?R[12I]\s*\["
    t = _first_table(tablas, rx)
    cats = []
    for f in t["filas"]:
        c = f["concepto"]
        if not re.search(rx, c) or re.search(r"SEF|ED\b|- ?ED", c):
            continue
        m = re.search(r"<=?\s*(\d+)\s*(?:KWh/mes)?\s*\]", c, re.I)
        hasta = int(m.group(1)) if m else (None if re.search(r"E\s*>\s*\d+", c) else -1)
        if hasta == -1 or len(f["valores"]) < 2 or any(x["hasta"] == hasta for x in cats):
            continue
        cats.append({"nombre": c, "hasta": hasta, "fijo": f["valores"][0], "escalones": [[None, f["valores"][1]]]})
    if [c["hasta"] for c in cats] != sorted(cats and [c["hasta"] for c in cats if c["hasta"] is not None]) + ([None] if cats and cats[-1]["hasta"] is None else []):
        raise ValueError("categorías fuera de orden")
    return {"periodo": "mes", "criterio": "T1R Anexo I, categoría según consumo mensual (OCR)", "categorias": cats}


@ocr_builder("secheep")
def secheep_ocr(tablas):
    """First block of page 1 (residencial sin SEF), 'Total' column; cumulative blocks per month."""
    filas = tablas[0]["filas"][:5]
    labels = [r"^Cargo Fijo$", r"[1Ll]ros\.? 50", r"stes\.? 100", r"stes\.? 150", r"exc\.? 300"]
    if len(filas) < 5 or not all(re.search(rx, f["concepto"]) for rx, f in zip(labels, filas)):
        raise ValueError("estructura inesperada")
    tot = lambda f: f["valores"][2] if len(f["valores"]) > 2 else None
    esc = [[50, tot(filas[1])], [150, tot(filas[2])], [300, tot(filas[3])], [None, tot(filas[4])]]
    return {"periodo": "mes", "criterio": "Residencial sin SEF, columna Total (OCR)",
            "categorias": [{"nombre": "Residencial", "hasta": None, "fijo": tot(filas[0]), "escalones": esc}]}


@ocr_builder("dpe")
def dpe_ocr(tablas):
    """TR1 Nivel 1: fixed charge plus cumulative blocks 150 / 150 / excedente de 300 (monthly)."""
    t = _first_table(tablas, r"^Primeros 150")
    filas = t["filas"][:4]
    labels = [r"^[S$].{0,3}mes$", r"^Primeros 150", r"^Siguientes 150", r"^Excedente de 300"]
    if len(filas) < 4 or not all(re.search(rx, f["concepto"]) for rx, f in zip(labels, filas)):
        raise ValueError("estructura inesperada")
    v = [f["valores"][0] for f in filas]
    return {"periodo": "mes", "criterio": "TR1 Nivel 1 (OCR)",
            "categorias": [{"nombre": "TR1 Nivel 1", "hasta": None, "fijo": v[0], "escalones": [[150, v[1]], [300, v[2]], [None, v[3]]]}]}


def build_ocr(entry):
    fn = OCR_BUILDERS.get(entry["id"])
    if not fn or entry.get("estado") != "ok" or not entry.get("ocr"):
        return None
    try:
        sim = fn(entry["tablas"])
    except Exception:
        return None
    return sim if sim["categorias"] else None

