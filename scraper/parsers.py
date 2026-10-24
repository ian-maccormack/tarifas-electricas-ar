"""Per-source parsers. Each returns dict(vigencia=str|None, tablas=[...]) where a tabla is
{"titulo", "columnas": [..], "filas": [{"concepto", "unidad", "valores": [float|None,..]}]}.
Values are copied from the document; anything that cannot be matched unambiguously is omitted."""
import re

from common import parse_num

PARSERS = {}


def parser(name):
    def deco(fn):
        PARSERS[name] = fn
        return fn
    return deco


NUM = r"-?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|-?\d+(?:[.,]\d+)?"


def nums(line):
    return [parse_num(x) for x in re.findall(NUM, line)]


def find(pattern, text, flags=re.I):
    m = re.search(pattern, text, flags)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None

UNIT = re.compile(r"\[?\$\s*/\s*(?:kw\s*-?\s*mes|kwh|kw|mes|bimestre|bimes|bim)\b\.?\]?|\$/cargo fijo -mes", re.I)
NUMTOK = re.compile(r"^-?(?:\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)$")


def section(text, start, end=None):
    m = re.search(start, text, re.I | re.M)
    if not m:
        raise ValueError(f"no se encontró la sección /{start}/")
    sub = text[m.start():]
    if end:
        e = re.search(end, sub[len(m.group(0)):], re.I | re.M)
        if e:
            sub = sub[:len(m.group(0)) + e.start()]
    return sub


def squeeze(s):
    return re.sub(r"\s+", " ", s).strip(" :|-–")


def take_values(rest, dec, maxvals=None):
    vals, consumed = [], 0
    for tok in rest.split():
        if tok == "$":
            consumed += 1
            continue
        if tok in ("-", "—") and vals:
            vals.append(None)
        elif NUMTOK.match(tok):
            vals.append(parse_num(tok, dec))
        else:
            break
        consumed += 1
        if maxvals and len(vals) >= maxvals:
            break
    while vals and vals[-1] is None:
        vals.pop()
    return vals, " ".join(rest.split()[consumed:])


def assign(vals, cols):
    """Attach column names only when the value count matches exactly."""
    if not cols:
        return None
    if isinstance(cols, dict):
        return cols.get(len(vals))
    return cols if len(vals) == len(cols) else None


def line_table(text, titulo, start, end=None, dec=",", cols=None, header_re=None, maxvals=None,
               segments=1, unit_after=False, left_col_from=None):
    """Rows look like 'label  $/unit  v1 v2 ...' (or 'label v $/unit' when unit_after)."""
    sub = section(text, start, end)
    filas, groups = [], [None] * segments
    width = None
    if left_col_from:
        m0 = re.search(left_col_from, sub.splitlines()[0])
        width = m0.start() if m0 else None
    for raw in sub.splitlines():
        if width:
            raw = raw[:width]
        if not raw.strip():
            continue
        line = raw
        if header_re and re.search(header_re, raw, re.I) and not UNIT.search(raw):
            chunks = [squeeze(c) for c in re.split(r"\s{4,}", raw.strip()) if c.strip()]
            groups = [squeeze(raw)] if segments == 1 else (chunks + [None] * segments)[:segments]
            continue
        for seg in range(segments):
            m = UNIT.search(line)
            if not m:
                break
            unidad = squeeze(m.group(0)).strip("[]")
            if unit_after:
                pre = line[:m.start()].rstrip()
                mm = re.search(r"((?:\s-?[\d.,]+)+)$", " " + pre)
                if not mm:
                    break
                vals = [parse_num(t, dec) for t in mm.group(1).split()]
                label = squeeze(pre[:len(pre) - len(mm.group(1)) + 1])
                rest = line[m.end():]
            else:
                label = squeeze(line[:m.start()])
                vals, rest = take_values(line[m.end():], dec, maxvals)
            if label and vals:
                g = groups[seg]
                filas.append({"grupo": g, "concepto": label, "unidad": unidad, "valores": vals,
                              "columnas": assign(vals, cols)})
            line = rest
    return {"titulo": titulo, "filas": filas}


def sheet_table(sheets, titulo, start, end=None, dec=None, header_re=r"unidad|cargo"):
    rows = [r for sh in sheets for r in sh["filas"]]
    i0 = next((i for i, r in enumerate(rows) if re.search(start, " | ".join(r), re.I)), None)
    if i0 is None:
        raise ValueError(f"no se encontró la sección /{start}/")
    filas, header, grupo = [], None, None
    for r in rows[i0:]:
        joined = " | ".join(r)
        if end and filas and re.search(end, joined, re.I):
            break
        uidx = next((i for i, c in enumerate(r) if UNIT.fullmatch(c.strip())), None)
        numidx = [i for i, c in enumerate(r) if c and parse_num(c, dec) is not None and NUMTOK.match(c.replace(" ", ""))]
        if uidx is None and not numidx:
            if re.search(header_re, joined, re.I) and len([c for c in r if c]) >= 2:
                header = r
            else:
                grupo = squeeze(joined.replace("|", " "))
            continue
        if uidx is not None:
            label = squeeze(" ".join(c for c in r[:uidx] if c))
            first = uidx + 1
            unidad = r[uidx]
        else:
            first = numidx[0]
            label = squeeze(" ".join(c for c in r[:first] if c))
            unidad = None
        vals = [parse_num(c, dec) if c else None for c in r[first:]]
        cols = [squeeze(c) for c in header[first:first + len(vals)]] if header else None
        while vals and vals[-1] is None:
            vals.pop()
            cols = cols[:len(vals)] if cols else cols
        if cols and len(cols) < len(vals):
            cols = None
        if label and vals:
            filas.append({"grupo": grupo, "concepto": label, "unidad": unidad, "valores": vals,
                          "columnas": cols if cols and any(cols) else None})
    return {"titulo": titulo, "filas": filas}


def pick(tablas, concepto_re, col=0, grupo_re=None):
    for t in tablas:
        for f in t["filas"]:
            if re.search(concepto_re, f["concepto"], re.I) and (not grupo_re or re.search(grupo_re, f.get("grupo") or "", re.I)):
                if col < len(f["valores"]) and f["valores"][col] is not None:
                    return {"valor": f["valores"][col], "unidad": f["unidad"], "concepto": f["concepto"],
                            "grupo": f.get("grupo"), "columna": (f.get("columnas") or [None] * 99)[col]}
                return None
    return None


def comparable(tablas, fijo, variable, nota):
    out = {"cargo_fijo": pick(tablas, *fijo) if fijo else None,
           "cargo_variable": pick(tablas, *variable) if variable else None, "nota": nota}
    return out if out["cargo_fijo"] or out["cargo_variable"] else None


# ---------------------------------------------------------------- per-source

@parser("enre")
def p_enre(text, source, **_):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(text, "html.parser")
    col_name = source["empresa"]
    plain = soup.get_text(" ")
    dec = "," if len(re.findall(r"\d\.\d{3},\d|\d,\d{2,3}\b(?![.,]\d)", plain)) >= len(re.findall(r"\d,\d{3}\.\d", plain)) else "."
    tablas = []
    for t in soup.find_all("table"):
        rows = [[c.get_text(" ", strip=True) for c in r.find_all(["td", "th"])] for r in t.find_all("tr")]
        rows = [r for r in rows if any(r)]
        if len(rows) < 2 or col_name not in rows[0]:
            continue
        ci = rows[0].index(col_name)
        ctx = []
        for el in t.find_all_previous(["b", "strong", "h1", "h2", "h3", "h4", "font", "p"], limit=6):
            tx = squeeze(el.get_text(" ", strip=True))
            if tx and re.search(r"[A-Za-z]{4}", tx) and not re.search(r"EDENOR|EDESUR", tx) and len(tx) < 160:
                ctx.append(tx)
        filas = [{"grupo": None, "concepto": r[0], "unidad": r[1] or None,
                  "valores": [parse_num(r[ci], dec)], "columnas": None} for r in rows[1:] if len(r) > ci]
        sub = ctx[0] if ctx else ""
        tablas.append({"titulo": rows[0][0] + (f" — {sub}" if sub else ""), "filas": filas})
    vig = find(r"(Per[ií]odo\s*\d{2}/\d{2})", soup.get_text(" "))
    return {"vigencia": vig, "tablas": tablas,
            "comparable": comparable(tablas, (r"Cargo Fijo 0-150",), (r"Cargo Variable 0-150",),
                                     "R1 (0-150 kWh/mes), primera tabla del cuadro ENRE")}


@parser("ecsapem")
def p_ecsapem(text, **_):
    t = line_table(text, "T1 Residencial / General / AP", r"T1-R\s+USO RESIDENCIAL", r"T2\s+MEDIANAS",
                   dec=".", cols=["VAD", "MEM", "TOTAL"],
                   header_re=r"^\s*(RESTO|ELECTRODEPENDIENTES|T1 ?- ?G|T1 ?- ?AP|Cargo variable por consumo)")
    return {"vigencia": find(r"(CUADRO TARIFARIO[^\n]{0,60}20\d\d)", text), "tablas": [t]}


@parser("edese")
def p_edese(text, **_):
    t = line_table(text, "T1 Residencial", r"T1 R Residencial", r"T1 G Uso General", dec=".",
                   cols=["Valor"], header_re=r"^\s*T1 R\d", maxvals=1, left_col_from=r"T3-MT")
    return {"vigencia": find(r"rigen a partir del ([^.]+?20\d\d)", text), "tablas": [t],
            "comparable": comparable([t], (r"Cargo fijo", 0, r"T1 R1"), (r"Cargo variable", 0, r"T1 R1"),
                                     "T1 R1 (consumo bimestral ≤ 300 kWh), sin subsidio")}


@parser("edersa")
def p_edersa(text, **_):
    cols = ["Con Subsidio (m)", "Con Subsidio (t)", "Sin Subsidio (m)", "Sin Subsidio (t)"]
    t = line_table(text, "Tarifa Residencial (cargos bimestrales)", r"TARIFA RESIDENCIAL", r"TARIFA GENERAL",
                   dec=",", cols=cols, header_re=r"kWh/bimestre")
    return {"vigencia": find(r"Periodo:\s*([A-Z]+ 20\d\d)", text), "tablas": [t],
            "comparable": comparable([t], (r"^CARGO FIJO", 2), (r"^CARGO VARIABLE", 2),
                                     "T1R1 (hasta 300 kWh/bim), columna 'Sin Subsidio – T1R1 m'")}


@parser("esj")
def p_esj(text, **_):
    cols = ["Hasta 220 kWh", "220–580 kWh", "580–1000 kWh", "1000–1400 kWh", "1400–2800 kWh", "> 2800 kWh"]
    t = line_table(text, "Uso Residencial (consumo bimestral)", r"^\s*Uso Residencial", r"^\s*Uso General",
                   dec=".", cols=cols)
    con = next((i for i, f in enumerate(t["filas"]) if "Con SEN" in f["concepto"]), None)
    for i, f in enumerate(t["filas"]):
        f["grupo"] = "Sin SEN" if con is None or i < con else "Con SEN"
    return {"vigencia": find(r"VALORES VIGENTES (DESDE [^\n]+?20\d\d HASTA [^\n]+?20\d\d)", text), "tablas": [t],
            "comparable": comparable([t], (r"^Cargo fijo \(haya o no consumo\)$", 0),
                                     (r"^Cargo variable por energ[ií]a$", 0),
                                     "T1-R1 (hasta 220 kWh/bim), sin SEN")}


@parser("refsa")
def p_refsa(text, **_):
    t = line_table(text, "T1-R Uso Residencial", r"T1-R Uso Residencial", r"T1-G|Uso General", dec=",",
                   cols=["Importe"], header_re=r"^\s*(T\.1-R|Tarifas\s+Tarifa)")
    return {"vigencia": find(r"(Para consumos efectuados a partir del [0-9/]+)", text), "tablas": [t],
            "comparable": comparable([t], (r"Cargo Fijo", 0, r"T\.1-R1\b"), (r"Cargo Variable", 0, r"T\.1-R1\b"),
                                     "T.1-R1 (≤ 150 kWh/mes), residencial sin subsidio")}


@parser("mendoza")
def p_mendoza(text, **_):
    t = line_table(text, "Residencial (R) y General", r"RESIDENCIAL \(R\)", r"SEF: Subsidios", dec=",",
                   header_re=r"^\s*Residencial \d|GENERAL \(G\)", segments=2)
    return {"vigencia": find(r"Vigencia:\s*(desde el [^\n]+?20\d\d)", text), "tablas": [t],
            "comparable": comparable([t], (r"^Cargo Fijo$", 0, r"Residencial 1"), (r"^Cargo Variable$", 0, r"Residencial 1"),
                                     "Residencial 1 (hasta 299 kWh/bim), primera columna (Sin SEF)")}


@parser("epen")
def p_epen(text, **_):
    t = line_table(text, "T1 Residencial", r"^\s*T1-R1-Consumo mensual", r"^\s*T1-G|PEQUE[ÑN]AS DEMANDAS GENERALES",
                   dec=",", header_re=r"^\s*T1-R", unit_after=True)
    return {"vigencia": find(r"(PER[ÍI]ODO DE FACTURACI[ÓO]N [^\n]+?20\d\d)", text), "tablas": [t],
            "comparable": comparable([t], (r"^Cargo fijo$", 0, r"T1-R1-"), (r"SIN SUBSIDIO", 0, r"T1-R1-"),
                                     "T1-R1 (≤ 50 kWh/mes), sin subsidio")}


@parser("dpec")
def p_dpec(text, **_):
    cols = {1: ["Tarifa sin bonif."], 4: ["Tarifa sin bonif.", "Con bonif. FEB/2026", "Con bonif. MAR/2026", "Con bonif. ABR/2026"]}
    t = line_table(text, "Tarifas residenciales (bimestral)", r"TARIFAS RESIDENCIALES", r"TARIFAS? (GENERAL|COMERCIAL)|PEQUE[ÑN]AS DEMANDAS GENERALES",
                   dec=",", cols=cols)
    return {"vigencia": None, "tablas": [t],
            "comparable": comparable([t], (r"URBANOS NO BONIFICADOS|Cuota Fija", 0), (r"Primeros 600", 0),
                                     "Residencial urbano no bonificado")}


@parser("ejesa")
def p_ejesa(text, **_):
    sub = section(text, r"T1 - SERVICIOS RESIDENCIALES", r"T1 - SERVICIOS COMUNITARIOS")
    cols = ["Cargo Fijo ($/mes)", "Cargo por Uso de Red ($/kWh)", "Cargo por Consumo de Energía ($/kWh)"]
    filas = []
    for line in sub.splitlines():
        m = re.match(r"^\s*(R\d(?:\s*-\s*bis)?|RE)\s+(.*?(?:kWh/mes|Todo el consumo))\s+(.*)$", line)
        if m:
            vals, _ = take_values(m.group(3), ",", 3)
            if len(vals) == 3:
                filas.append({"grupo": None, "concepto": f"{m.group(1)} {squeeze(m.group(2))}", "unidad": None,
                              "valores": vals, "columnas": cols})
    t = {"titulo": "T1 - Servicios residenciales (cargos plenos)", "filas": filas}
    return {"vigencia": None, "tablas": [t],
            "comparable": comparable([t], (r"^R1 ", 0), None, "R1 (primeros 150 kWh/mes); el variable se compone de uso de red + energía (ver tabla)")}


@parser("epec")
def p_epec(text, **_):
    sub = section(text, r"TARIFA N[ºo°] 1 - RESIDENCIAL", r"^\s*TARIFA N[ºo°] 2 - GENERAL Y DE SERVICIOS")
    filas, grupo, label, head = [], None, None, "Residencial"
    for line in sub.splitlines():
        s = line.strip()
        if not s:
            continue
        if re.match(r"^RESIDENCIAL[A-ZÁÉÍÓÚÑ ]*$", s):
            head = squeeze(s.title())
            continue
        m = re.match(r"^\(Pesos[^)]*\)\s*\$\s*([\d.,]+)$", s)
        if m and label:
            unidad = "$/mes" if re.search(r"cargo fijo", label, re.I) else ("$/kWh" if re.search(r"kwh", label, re.I) else None)
            filas.append({"grupo": grupo, "concepto": label, "unidad": unidad, "valores": [parse_num(m.group(1), ",")],
                          "columnas": None})
        elif s.startswith("●"):
            grupo = f"{head} — {squeeze(s.lstrip('●'))}"
        elif not s.startswith("(") and len(s) < 90:
            label = squeeze(s)
        if len(filas) > 150:
            break
    t = {"titulo": "Tarifa Nº 1 - Residencial", "filas": filas}
    return {"vigencia": find(r"(PUBLICACION WEB EPEC - [0-9/]+)", text), "tablas": [t]}


@parser("enersa")
def p_enersa(text, sheets=None, **_):
    rows = [r for sh in sheets or [] for r in sh["filas"]]
    i0 = next((i for i, r in enumerate(rows) if any(re.search(r"T 1-R Uso residencial", c) for c in r)), None)
    if i0 is None:
        raise ValueError("no se encontró T 1-R")
    hdr = next(r for r in rows[i0 - 3:i0 + 1] if any("Sin Subsidio" in c for c in r))
    groups = [c for c in hdr if c]
    tabs = [{"titulo": f"T 1-R Uso residencial — {g}", "filas": []} for g in groups]
    for r in rows[i0:]:
        if any(re.search(r"T 1-Rural", c) for c in r):
            break
        cells = [c for c in r]
        k, i = 0, 0
        while i < len(cells):
            c = cells[i]
            if c and parse_num(c) is None and not re.search(r"T 1-R", c):
                j = i + 1
                while j < len(cells) and not cells[j]:
                    j += 1
                if j < len(cells) and parse_num(cells[j]) is not None and k < len(tabs):
                    um = UNIT.search(c)
                    tabs[k]["filas"].append({"grupo": None, "concepto": squeeze(UNIT.sub("", c)),
                                             "unidad": um.group(0) if um else "$/kWh", "valores": [parse_num(cells[j])],
                                             "columnas": None})
                    k, i = k + 1, j + 1
                    continue
                k += 1 if re.search(r"Cargo|Primeros|Siguientes|Excedente", c) else 0
            i += 1
    return {"vigencia": find(r"(Vigente a partir del [^|\n]+?20\d\d al [^|\n]+?20\d\d)", text), "tablas": tabs,
            "comparable": comparable(tabs[:1], (r"Cargo fijo",), (r"Primeros 100",), "T 1-R sin subsidio, primeros 100 kWh/mes")}


@parser("ape")
def p_ape(text, sheets=None, **_):
    t = sheet_table(sheets or [], "T1R Categoría Residenciales - Nivel 1", r"T1R\s+CATEGOR", r"NIVEL 2", dec=".")
    return {"vigencia": find(r"Vigencia:\s*([^|\n]+?20\d\d)", text), "tablas": [t],
            "comparable": comparable([t], (r"^Cargo Fijo$", 0, r"^T1R1-2 Consumos menores"), None,
                                     "T1R1-2 Nivel 1 (≤ 120 kWh/mes), precio de venta máximo; el cargo variable tiene varios componentes (ver tabla)")}


@parser("edesal")
def p_edesal(text, sheets=None, **_):
    t = sheet_table(sheets or [], "Tarifa 1-R Residencial", r"Tarifa 1-R:", r"Tarifa 1-G", dec=".", header_re=r"Cargo Fijo")
    return {"vigencia": None, "tablas": [t],
            "comparable": comparable([t], (r"^T1R-1", 0), (r"^T1R-1", 2), "T1R-1, 'Cuadro Resolución' (primera tabla)")}
