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
    filas, prev = [], ""
    for line in sub.splitlines():
        m = re.match(r"^\s*(R\d(?:\s*-\s*bis)?|RE)\s+(.*?(?:kWh/mes|Todo el consumo))\s+(.*)$", line)
        if not m:
            # the label of a row can sit on the line above its code and values (e.g. R5)
            m0 = re.match(r"^\s*(R\d)\s+(\d.*)$", line)
            lab = re.match(r"^\s*(Mayor a \d+ y menor o igual a \d+ kWh/mes)(?:\s{3,}\D*)?$", prev)
            if m0 and lab:
                m = re.match(r"^(.*)\|(.*)\|(.*)$", f"{m0.group(1)}|{lab.group(1)}|{m0.group(2)}")
        if line.strip():
            prev = line
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


def _chunks(line):
    return [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"\S+(?: \S+)*", line)]


def _nearest(cols, pos):
    return min(range(len(cols)), key=lambda i: abs((cols[i][0] + cols[i][1]) / 2 - pos))


NUM_ES = re.compile(r"-?\d[\d.]*,\d+")


@parser("edelar")
def p_edelar(text, **_):
    """Values are mapped to columns by horizontal position; a row is kept only when every
    number lands in a distinct column (tiered sub-rows without a label are skipped)."""
    tablas, t, cols, tipos, pending, held = [], None, None, {}, None, None

    def add(label, unit, found):
        idx = [_nearest(cols, (a + b) / 2) for a, b, _ in found]
        if len(set(idx)) != len(idx):
            return
        vals = [None] * len(cols)
        for i, (_, _, s) in zip(idx, found):
            vals[i] = parse_num(s, ",")
        keep = t["_keep"]
        t["filas"].append({"grupo": None, "concepto": label, "unidad": unit,
                           "valores": [vals[i] for i in keep],
                           "columnas": [f"{cols[i][2]} ({tipos[i]})" if i in tipos else cols[i][2] for i in keep]})

    for raw in text.splitlines():
        if held and raw.strip():
            label, unit, _, found = held
            held = None
            m2 = re.match(r"^(\S.*?)\s{2,}(\$/\S+)\s*$", raw)
            if m2 and m2.group(2) == unit:
                # one value printed between two label rows: the PDF does not say which row it belongs to
                add(f"{label} / {squeeze(m2.group(1))} (un solo valor entre ambas filas del PDF)", unit, found)
                continue
            add(label, unit, found)
        codes = [c for c in _chunks(raw) if re.fullmatch(r"T\d+-[A-Z]+\d*(-[A-Z0-9]+)?", c[2])]
        if codes and len(codes) == len(_chunks(raw)) - (1 if "PEQUEÑAS" in raw else 0):
            keep = [i for i, c in enumerate(codes) if c[2].startswith("T1-R")]
            if not keep:
                break
            cols, tipos, pending = codes, {}, None
            pref = re.match(r"T1-R[A-Z]?\d?", codes[keep[0]][2]).group(0)
            t = {"titulo": f"{pref} — Tarifa Residencial", "filas": [], "_keep": keep}
            tablas.append(t)
            continue
        if not cols:
            continue
        if "Tipo usuario" in raw:
            for a, b, s in _chunks(raw):
                if s != "Tipo usuario":
                    tipos[_nearest(cols, (a + b) / 2)] = s
            continue
        found = [(m.start(), m.end(), m.group(0)) for m in NUM_ES.finditer(raw)]
        m = re.match(r"^(\S.*?)\s{2,}(\$/\S+)", raw)
        if m:
            pending = None
            if not found:
                pending = (squeeze(m.group(1)), m.group(2))
                continue
            label, unit = squeeze(m.group(1)), m.group(2)
        elif pending and found and not re.search(r"[A-Za-z]", raw):
            label, unit = pending
            pending = None
            held = (label, unit, raw, found)
            continue
        else:
            if raw.strip():
                pending = None
            continue
        add(label, unit, found)
    for x in tablas:
        x.pop("_keep", None)
    return {"vigencia": find(r"CUADRO TARIFARIO DE APLICACI[ÓO]N A LOS USUARIOS\s+(\S.*?20\d\d)", text),
            "tablas": tablas,
            "comparable": comparable(tablas, None, (r"^Cargo Variable$", 0, None),
                                     "T1-R1 sin subsidio (< 200 kWh/mes)")}


@parser("ejsed")
def p_ejsed(text, **_):
    """Two side-by-side columns of TDI categories (sistemas dispersos)."""
    lines = text.splitlines()
    first = next((ln for ln in lines if ln.count("ENPAD") == 2), None)
    if not first:
        raise ValueError("no se encontró la grilla TDI")
    split = first.index("ENPAD", first.index("ENPAD") + 1) - 10
    rx = re.compile(r"(ENPAD|Cargo Fijo|Cargo Variable|Tarifa Plena|Tarifa Usuario Final|Subsidio)\s+(\S+)\s+\$?\s*(-?[\d.]+,\d+)")
    blocks, cur = [], None
    for ln in lines:
        hits = list(rx.finditer(ln))
        if any(h.group(1) == "ENPAD" for h in hits):
            cur = [{"label": "", "rows": []}, {"label": "", "rows": []}]
            blocks.append(cur)
        if cur is None:
            continue
        for h in hits:
            cur[0 if h.start() < split else 1]["rows"].append((h.group(1), h.group(2), parse_num(h.group(3), ",")))
        for m in re.finditer(r"TDI-\d+|_\d{3}\b", ln):
            cur[0 if m.start() < split else 1]["label"] += m.group(0)
    filas = []
    for b in blocks:
        for side in b:
            for c, u, v in side["rows"]:
                filas.append({"grupo": side["label"] or None, "concepto": c, "unidad": u, "valores": [v], "columnas": None})
    filas.sort(key=lambda f: (f["grupo"] or "") if f["grupo"] else "")
    return {"vigencia": squeeze((find(r"(Para el per[ií]odo comprendido[^\n]*\n[^\n]*)", text) or "").replace("TARIFARIO", "")) or None,
            "tablas": [{"titulo": "Tarifas TDI (sistemas dispersos)", "filas": filas}]}


@parser("emsa")
def p_emsa(text, **_):
    sub = section(text, r"CUADRO TARIFARIO N[ºo°] 654\s+Vigente", r"2\.a1|COMERCIAL")
    row = re.compile(r"(Primeros|Siguientes|Excedente de)\s+(\d+)\s*KWH\s+(\d[\d.]*,\d+)(?:\s+(\d[\d.]*,\d+))?\s*$", re.I)
    blocks = []
    for ln in sub.splitlines():
        m = row.search(ln)
        rest = ln[:m.start()] if m else ln
        if m and m.group(1).lower() == "primeros":
            blocks.append({"label": [], "rows": [], "cuota": None})
        if not blocks:
            continue
        b = blocks[-1]
        rest = re.sub(r"Categor[ií]a\s+\d+", "", rest).strip()
        if rest and not re.search(r"Vigente|CUADRO|Hoja|ANEXO|TARIFA|SUMINISTRO|CATEGORIA", rest):
            b["label"].append(rest)
        if m:
            b["rows"].append((f"{m.group(1)} {m.group(2)} kWh", parse_num(m.group(3), ",")))
            if m.group(4):
                b["cuota"] = parse_num(m.group(4), ",")
    filas = []
    for b in blocks:
        g = squeeze(" ".join(b["label"])) or None
        filas.append({"grupo": g, "concepto": "Cuota de servicio", "unidad": None, "valores": [b["cuota"]], "columnas": None})
        filas += [{"grupo": g, "concepto": c, "unidad": "Neto kWh", "valores": [v], "columnas": None} for c, v in b["rows"]]
    t = {"titulo": "Cuadro Tarifario Nº 654 (Anexo I) — Categoría 1 Residencial", "filas": filas}
    return {"vigencia": find(r"(Vigente a partir del Per[ií]odo \d\d/20\d\d)", text), "tablas": [t],
            "comparable": comparable([t], (r"^Cuota de servicio$", 0, r"500 kwh"), (r"^Primeros 30", 0, r"500 kwh"),
                                     "Residencial hasta 500 kWh/mes; primeros 30 kWh. El cuadro no indica la unidad de la cuota de servicio")}


@parser("oceba")
def p_oceba(text, **_):
    """OCEBA annexes (EDEN, EDES): T1R categories R1..R7, each with its own fixed and variable charge."""
    t = line_table(text, "T1R - Residencial (categoría según consumo mensual)", r"^\s*T1R - RESIDENCIAL\s*$",
                   r"^\s*T1RE - RESIDENCIAL ESTACIONAL", dec=",", unit_after=True)
    t2 = line_table(text, "T2 - Medianas demandas (de 10 kW a menos de 50 kW)", r"^T2 - MEDIANAS DEMANDAS",
                    r"^T3 - GRANDES DEMANDAS", dec=",", unit_after=True, header_re=r"^\s*T2(BT|MT)\s*-")
    t3 = [line_table(text, f"T3{v} - Grandes demandas (50 kW o más), {n}", rf"^\s*T3{v} - SUMINISTROS", end,
                     dec=",", unit_after=True,
                     header_re=r"^\s*(SUMINISTROS >=|USUARIOS FINALES|DIST\. MUNICIPALES|DISTRIBUIDORES MUNICIPALES)")
          for v, n, end in (("BT", "baja tensión", r"^\s*T3MT - "), ("MT", "media tensión", r"^\s*T3AT - "))]
    tablas = [t] + [x for x in [t2] + t3 if x["filas"]]
    return {"vigencia": None, "tablas": tablas,
            "comparable": comparable([t], (r"^CARGO FIJO R1$", 0), (r"^CARGO VARIABLE R1\b", 0),
                                     "T1R R1 (consumo ≤ 100 kWh-mes)")}


EPE_NUM = re.compile(r"(?<![\d.,])\d{1,3}(?:\.\d{3})*,\d{5}(?![\d,])")
EPE_CODE = re.compile(r"\b1[A-Z]A\b")


def _epe_columns(header):
    """Column names from a header block, only if its tiers add up to the stated excedente limit."""
    h = re.sub(r"\s+", " ", " ".join(header))
    tiers = [(w, int(n)) for w, n in re.findall(r"(Primeros|Siguientes) (\d+)", h)]
    exc = re.search(r"Excedente de.*?(\d+)\s*kWh/mes", h)
    if not tiers or not exc or tiers[0][0] != "Primeros" or sum(n for _, n in tiers) != int(exc.group(1)):
        return None
    return (["Cuota de Servicio ($/mes)"] + [f"{w} {n} kWh/mes ($/kWh)" for w, n in tiers]
            + [f"Excedente de {exc.group(1)} kWh/mes ($/kWh)"])


@parser("epe")
def p_epe(text, **_):
    """EPE 'residencial sin subsidio' tables. Values are vertically centred next to several tariff
    codes, so a value row takes the codes of the lines around it; if two value rows compete for
    the same lines, they are dropped."""
    sub = section(text, r"TARIFA RESIDENCIAL - SIN SUBSIDIO", r"^\s*TARIFA SOCIAL")
    lines = sub.splitlines()
    starts = [i for i, l in enumerate(lines) if re.search(r"Cuota de\s", l)]
    tablas = []
    for n, s in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        hdr_end = next((i for i in range(s, end) if "$/sum" in lines[i]), None)
        if hdr_end is None:
            continue
        cols = _epe_columns(lines[s:hdr_end + 1])
        body = list(range(hdr_end + 1, end))
        vals = {i: [parse_num(x, ",") for x in EPE_NUM.findall(lines[i])] for i in body}
        coded = [i for i in body if vals[i] and EPE_CODE.search(lines[i])]
        bare = [i for i in body if vals[i] and not EPE_CODE.search(lines[i])]
        bounds = [hdr_end] + coded + [end]
        filas = []
        for i in sorted(coded + bare):
            if i in coded:
                label = squeeze(EPE_NUM.sub("", lines[i]))
            else:
                lo = max(b for b in bounds if b < i)
                hi = min(b for b in bounds if b > i)
                if len([j for j in bare if lo < j < hi]) != 1:
                    continue
                parts = [squeeze(EPE_CODE.sub(lambda m: "|" + m.group(0), lines[j])) for j in range(lo + 1, hi)
                         if j != i and EPE_CODE.search(lines[j])]
                label = " / ".join(squeeze(p.split("|", 1)[-1]) for p in parts)
                grupo = " ".join(squeeze(EPE_CODE.split(lines[j])[0]) for j in range(lo + 1, hi)
                                 if j != i and squeeze(EPE_CODE.split(lines[j])[0]))
                label = (squeeze(grupo) + ": " if grupo else "") + label
            if not EPE_CODE.search(label):
                continue
            filas.append({"grupo": None, "concepto": label, "unidad": "$/mes; $/kWh", "valores": vals[i],
                          "columnas": assign(vals[i], cols)})
        if filas:
            tablas.append({"titulo": "Residencial sin subsidio (valores mensuales, facturación bimestral)" +
                           (f" — {cols[1].split(' (')[0]}…" if cols else ""), "filas": filas})
    comp = None
    for t in tablas:
        f = next((f for f in t["filas"] if re.search(r"\b1AA\b", f["concepto"]) and f.get("columnas")), None)
        if f:
            comp = {"cargo_fijo": {"valor": f["valores"][0], "unidad": "$/mes", "concepto": f["concepto"], "grupo": None,
                                   "columna": f["columnas"][0]},
                    "cargo_variable": {"valor": f["valores"][1], "unidad": "$/kWh", "concepto": f["concepto"], "grupo": None,
                                       "columna": f["columnas"][1]},
                    "nota": f"Residencial urbano sin subsidio (1AA), {f['columnas'][1].split(' (')[0]}"}
            break
    return {"vigencia": find(r"(Consumos registrados desde el [^\n]+?20\d\d)", text), "tablas": tablas, "comparable": comp}
