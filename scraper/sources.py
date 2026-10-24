"""Registry of distributors and how to discover their current tariff document."""
import html
import json
import re
import threading
import time
from urllib.parse import unquote, urljoin

from common import MESES, fetch, links, norm

SE_BASE = "https://www.argentina.gob.ar/economia/energia/energia-electrica/estadisticas/cuadros-tarifarios-"
ORIGEN_DIST = "Distribuidora"
ORIGEN_ENTE = "Ente regulador / organismo provincial"
ORIGEN_SE = "Secretaría de Energía de la Nación (archivo)"


def _date_key(t):
    best = (0, 0, 0)
    ok = lambda y: 2015 <= y <= 2035
    for m in re.finditer(r"(?<!\d)(\d{1,2})[-_/.](\d{1,2})[-_/.](20\d\d)(?!\d)", t):
        d, mo, y = map(int, m.groups())
        if 1 <= mo <= 12 and ok(y):
            best = max(best, (y, mo, d))
    for name, mo in MESES.items():
        for m in re.finditer(name + r"[^0-9]{0,12}(20\d\d)", t):
            best = max(best, (int(m.group(1)), mo, 0))
        for m in re.finditer(r"(20\d\d)[^0-9a-z]{1,4}" + name, t):
            best = max(best, (int(m.group(1)), mo, 0))
    for m in re.finditer(r"(?<!\d)(20\d\d)[-_](\d{2})(?:[-_](\d{2}))?(?!\d)", t):
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and ok(y):
            best = max(best, (y, mo, int(m.group(3) or 0)))
    for m in re.finditer(r"(?<!\d)(\d{2})[-_/](20\d\d)(?!\d)", t):
        mo, y = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and ok(y):
            best = max(best, (y, mo, 0))
    return best


def date_key(href, text=""):
    """Best-effort (year, month, day) for ordering candidate links; dates in the
    link text / file name win over the CMS upload folder (/uploads/YYYY/MM/)."""
    href = unquote(href)
    k = _date_key(norm(text + " " + href.rsplit("/", 1)[-1]))
    if k != (0, 0, 0):
        return k
    m = re.search(r"/uploads/(20\d\d)/(\d{2})/", href)
    return (int(m.group(1)), int(m.group(2)), 0) if m else (0, 0, 0)


def latest_link(page, url_re, text_re=None, exclude_re=None):
    r = fetch(page)
    cands = []
    for i, (txt, href) in enumerate(links(r.text, r.url)):
        if not re.search(url_re, href, re.I) and not (text_re and re.search(text_re, txt, re.I)):
            continue
        if exclude_re and (re.search(exclude_re, href, re.I) or re.search(exclude_re, txt, re.I)):
            continue
        cands.append((date_key(href, txt), -i, txt, href))
    if not cands:
        raise LookupError(f"sin enlaces candidatos en {page}")
    cands.sort(reverse=True)
    _, _, txt, href = cands[0]
    return {"url": href, "titulo": txt or href.rsplit("/", 1)[-1]}


def fixed(url, titulo=""):
    return lambda: {"url": url, "titulo": titulo or url.rsplit("/", 1)[-1]}


def se_archive(slug):
    def disc():
        page = SE_BASE + slug
        r = fetch(page)
        best = None
        for txt, href in links(r.text, r.url):
            m = re.search(r"Cuadro Tarifario del (\d{2})-(\d{4})", txt)
            if m and "energia.gob.ar" in href:
                key = (int(m.group(2)), int(m.group(1)))
                if best is None or key > best[0]:
                    best = (key, txt, href)
        if not best:
            raise LookupError("sin cuadros en el archivo de la Secretaría de Energía")
        return {"url": best[2], "titulo": best[1], "pagina": page}
    return disc


def enre():
    page = "https://www.enre.gov.ar/web/TARIFASD.nsf/todoscuadros?OpenView&collapseview"
    r = fetch(page)
    for txt, href in links(r.text, r.url):
        if "opendocument" in href.lower() and "Cuadro Tarifario del" in txt:
            return {"url": href.replace("\\", "/"), "titulo": txt, "pagina": page}
    raise LookupError("ENRE: no se encontró el último cuadro")


def epre_entre_rios():
    page = "https://epre.gov.ar/web/category/noticias/tarifa-electrica/"
    r = fetch(page)
    posts = [(date_key(h, t), -i, h) for i, (t, h) in enumerate(links(r.text, r.url))
             if re.search(r"/web/(actualizacion-)?cuadro-tarifario-[a-z]+-20\d\d", h)]
    if not posts:
        raise LookupError("EPRE ER: sin publicaciones")
    posts.sort(reverse=True)
    post = posts[0][2]
    r2 = fetch(post)
    for t, h in links(r2.text, r2.url):
        if re.search(r"anexo-?1\.xlsx$", h, re.I):
            return {"url": h, "titulo": post.rstrip("/").rsplit("/", 1)[-1], "pagina": post}
    for t, h in links(r2.text, r2.url):
        if re.search(r"anexo-?1\.pdf$", h, re.I):
            return {"url": h, "titulo": post.rstrip("/").rsplit("/", 1)[-1], "pagina": post}
    raise LookupError("EPRE ER: publicación sin anexo")


def getfile_page(page, text_re, exclude_re=r"dispers|permer"):
    """EJESA/EDET portals: links say 'DESCARGAR'; the title is the text right before."""
    def disc():
        import html as htmlmod
        r = fetch(page)
        for m in re.finditer(r'href="([^"]*GetFile\?fileId=[^"]+)"', r.text):
            ctx = htmlmod.unescape(re.sub(r"<[^>]+>", " ", r.text[max(0, m.start() - 600):m.start()]))
            title = re.sub(r"\s+", " ", ctx).strip()[-80:]
            title = re.sub(r"^.*?>\s*|\s*<a$", "", title).strip()
            if re.search(text_re, title, re.I) and not re.search(exclude_re, title, re.I):
                return {"url": urljoin(r.url, htmlmod.unescape(m.group(1))), "titulo": title, "pagina": page}
        raise LookupError("sin archivos de cuadro tarifario")
    return disc


def refsa():
    page = "https://recursosyenergia.com.ar/tarifas?id=32"
    r = fetch(page)
    cands = [(date_key("", t), -i, t, h) for i, (t, h) in enumerate(links(r.text, r.url))
             if re.search(r"tarifas\?id=\d+$", h) and re.match(r"20\d\d\s*-", t)]
    if not cands:
        raise LookupError("REFSA: sin períodos")
    cands.sort(reverse=True)
    _, _, t, h = cands[0]
    r2 = fetch(h)
    m = re.search(r"https?://[^\"' ]+_cuadro_[^\"' ]+\.pdf", r2.text)
    if not m:
        raise LookupError("REFSA: período sin PDF de cuadro")
    return {"url": m.group(0), "titulo": t, "pagina": h}


def page_latest(page, url_re, text_re=None, exclude_re=None):
    def disc():
        d = latest_link(page, url_re, text_re, exclude_re)
        d["pagina"] = page
        return d
    return disc


def wp_media(site, search, url_re):
    """WordPress sites often unlink older pages; the media API lists every uploaded PDF by date."""
    def disc():
        api = f"{site}/wp-json/wp/v2/media?search={search}&per_page=30&orderby=date&mime_type=application/pdf"
        items = [m for m in fetch(api).json() if re.search(url_re, m.get("source_url", ""), re.I)]
        if not items:
            raise LookupError(f"sin PDFs '{search}' en {site}")
        m = max(items, key=lambda m: m["date"])
        return {"url": m["source_url"], "titulo": m["source_url"].rsplit("/", 1)[-1], "pagina": api,
                "publicado": m["date"][:10]}
    return disc


S = []


WAYBACK = "https://web.archive.org/web/"
OCEBA_PAGE = "https://www.oceba.gba.gov.ar/nueva_web/s.php?i=17"


_WB_LOCK = threading.Lock()
_WB_CACHE = {}


def _wayback(url, timeout=60):
    """GET through the Internet Archive one request at a time (it rate-limits with 429), retrying
    while it is offline or busy. Responses are reused within a run (EDEN and EDES share the page)."""
    with _WB_LOCK:
        if url in _WB_CACHE:
            return _WB_CACHE[url]
        last = None
        for i in range(4):
            try:
                r = fetch(url, timeout=timeout)
                if "Internet Archive: " not in r.text[:400] or "Offline" not in r.text[:400]:
                    _WB_CACHE[url] = r
                    time.sleep(2)
                    return r
                last = RuntimeError("Internet Archive fuera de servicio")
            except Exception as e:
                last = e
            time.sleep(20 * (i + 1))
        raise last


def _captures(url_pattern, limit=None):
    """[(timestamp, original_url)] with HTTP 200 in the Internet Archive, oldest first."""
    q = f"https://web.archive.org/cdx/search/cdx?url={url_pattern}&output=json&filter=statuscode:200&fl=timestamp,original"
    if limit:
        q += f"&limit={limit}"
    rows = json.loads(_wayback(q).text or "[]")
    return [tuple(r) for r in rows[1:]]


def _oceba_blocks(page_html, empresa):
    """[(vigencia, resolución_url, pdf_url)] for the general tariff ('DEMANDA RESIDENCIAL', ...) of
    every approval block on the OCEBA page; the newest validity first."""
    t = html.unescape(page_html)
    out = []
    for blk in re.split(r"Tarifas aprobadas por", t)[1:]:
        mv = re.search(r"vigentes\s+a\s*partir de consumos del\s+([^.<]+?20\d\d)", blk)
        mr = re.search(r'href="([^"]+\.pdf)"', blk)
        heads = re.split(r"TARIFA APLICABLE A", blk)
        if not mv or len(heads) < 2 or not re.match(r'\s*"DEMANDA RESIDENCIAL"', heads[1]):
            continue
        ml = re.search(r'href="([^"]+\.pdf)"[^>]*>\s*' + re.escape(empresa) + r"\s+S\.A\.", heads[1])
        if ml:
            out.append((re.sub(r"\s+", " ", mv.group(1)).strip(), urljoin(OCEBA_PAGE, mr.group(1)) if mr else None,
                        urljoin(OCEBA_PAGE, ml.group(1))))
    return sorted(out, key=lambda b: _date_key(norm(b[0])), reverse=True)


def oceba(empresa):
    """OCEBA publishes one annex per distributor. Its site blocks the scraper, so when the live page
    does not answer, use the newest copy of the page and annex kept by the Internet Archive."""
    def disc():
        def result(vig, reso, pdf, url, archivado=None):
            titulo = f"Cuadro tarifario {empresa} S.A. (OCEBA), consumos desde el {vig}"
            return {"url": url, "titulo": titulo + (" — copia archivada" if archivado else ""), "pagina": OCEBA_PAGE,
                    "vigencia": f"Consumos desde el {vig}", "resolucion": reso, "archivado": archivado}
        try:
            blocks = _oceba_blocks(fetch(OCEBA_PAGE, timeout=30).text, empresa)
            if blocks:
                return result(*blocks[0], blocks[0][2])
        except Exception:
            pass
        snaps = sorted(_captures("oceba.gba.gov.ar/nueva_web/s.php?i=17"), reverse=True)
        for ts, orig in snaps[:4]:
            page = _wayback(f"{WAYBACK}{ts}id_/{orig}").text
            for vig, reso, pdf in _oceba_blocks(page, empresa):
                caps = _captures(pdf.split("://", 1)[1].replace("www.", "", 1))
                if caps:
                    cts, corig = caps[-1]
                    return result(vig, reso, pdf, f"{WAYBACK}{cts}id_/{corig}",
                                  {"servicio": "Internet Archive (Wayback Machine)", "url_original": pdf,
                                   "captura": f"{cts[:4]}-{cts[4:6]}-{cts[6:8]}", "pagina_captura": f"{WAYBACK}{ts}/{orig}"})
        raise LookupError("ni OCEBA ni el Internet Archive tienen el anexo de " + empresa)
    return disc


EPE_PAGE = "https://epe.santafe.gov.ar/institucional/usuarios"
EPE_API = "https://epe.santafe.gov.ar/institucional-api/download/"


def _epe_headers(page, component):
    """Headers the site's own download component sends (its public client key lives in the bundle)."""
    js = fetch(urljoin(page, component)).text
    m = re.search(r'from\s*"(\./httpClient[^"]+\.js)"', js)
    key = re.search(r'"x-api-key":\s*[`"\']([^`"\']+)', fetch(urljoin(urljoin(page, component), m.group(1))).text) if m else None
    if not key:
        raise LookupError("no se encontró cómo descarga archivos la página de EPE")
    return {"x-api-key": key.group(1)}


def epe():
    """The EPE page renders its files with a client component; the file hash is in its props."""
    r = fetch(EPE_PAGE)
    best, component = None, None
    for comp, raw in re.findall(r'<astro-island[^>]*component-url="([^"]*DownloadFile[^"]*)"[^>]*props="([^"]+)"', r.text):
        component = comp
        props = {k: v[1] for k, v in json.loads(html.unescape(raw)).items() if isinstance(v, list)}
        title, name = props.get("title") or "", props.get("fileName") or ""
        if re.search(r"cuadro tarifario", title, re.I) and re.search(r"residencial", name, re.I) and props.get("fileHash"):
            key = date_key(name, title)
            if best is None or key > best[0]:
                best = (key, {"url": EPE_API + props["fileHash"], "titulo": f"{title} ({name})", "pagina": EPE_PAGE})
    if not best:
        raise LookupError("sin cuadro tarifario residencial en la página de EPE")
    return {**best[1], "headers": _epe_headers(EPE_PAGE, component)}


def src(id, empresa, nombre, provincia, primary=None, origen=ORIGEN_DIST, se=None, parser=None, nota="", known=None, ocr=False):
    S.append(dict(id=id, empresa=empresa, nombre=nombre, provincia=provincia,
                  primary=primary, origen=origen, se=se, parser=parser or id, nota=nota, known=known,
        ocr=ocr))


src("edenor", "EDENOR", "Empresa Distribuidora y Comercializadora Norte S.A.", "Ciudad de Buenos Aires y GBA",
    enre, "ENRE / ENReGE", "edenor", parser="enre")
src("edesur", "EDESUR", "Empresa Distribuidora Sur S.A.", "Ciudad de Buenos Aires y GBA",
    enre, "ENRE / ENReGE", "edesur", parser="enre")
src("edes", "EDES", "Empresa Distribuidora de Energía Sur S.A.", "Buenos Aires",
    oceba("EDES"), ORIGEN_ENTE, "edessa", parser="oceba",
    nota="OCEBA no responde desde el servidor del scraper: se usa la copia más reciente guardada por el Internet Archive.")
src("edea", "EDEA", "Empresa Distribuidora de Energía Atlántica S.A.", "Buenos Aires",
    page_latest("https://www.edeaweb.com.ar/cuadro-tarifario/", r"/uploads/.*\.pdf$"), se="edea")
src("edelap", "EDELAP", "Empresa Distribuidora La Plata S.A.", "Buenos Aires",
    wp_media("https://www.edelap.com.ar", "tarifario", r"/uploads/.*cuadro-tarifario.*\.pdf$"), se="edelap",
    known="https://www.edelap.com.ar/wp-content/uploads/2026/03/EDELAP-CT-102-2026.pdf")
src("eden", "EDEN", "Empresa Distribuidora de Energía Norte S.A.", "Buenos Aires",
    oceba("EDEN"), ORIGEN_ENTE, "eden", parser="oceba",
    nota="OCEBA no responde desde el servidor del scraper: se usa la copia más reciente guardada por el Internet Archive.")
src("ecsapem", "EC SAPEM", "Energía Catamarca S.A.P.E.M.", "Catamarca",
    page_latest("https://www.ecsapem.com.ar/", r"/uploads/.*cuadro.*\.pdf$"), se="ecsapem",
    known="https://www.ecsapem.com.ar/uploads/Cuadro_Tarifario_Octubre_2026_SUBSIDIADO_Res_DP_301_26_34088daf9f.pdf")
src("secheep", "SECHEEP", "Servicios Energéticos del Chaco Empresa del Estado Provincial", "Chaco",
    page_latest("https://www.secheep.gob.ar/?page_id=5601", r"/uploads/.*(cuadro|tarifa).*\.pdf$", exclude_re=r"social|AP24|alumbrado"),
    se="secheep")
src("dgsp", "DGSP", "Dirección General de Servicios Públicos", "Chubut", None, se="dgsp",
    nota="No se encontró publicación propia vigente; gran parte de Chubut es atendida por cooperativas.")
src("epec", "EPEC", "Empresa Provincial de Energía de Córdoba", "Córdoba",
    page_latest("https://www.epec.com.ar/cuadro-tarifario", r"/docs/cuadro-tarifario/.*\.pdf$"), se="epec-0",
    known="https://www.epec.com.ar/docs/cuadro-tarifario/cuadro-tarifario-publicado-02102026-aplicacion-011026.pdf")
src("dpec", "DPEC", "Dirección Provincial de Energía de Corrientes", "Corrientes",
    page_latest("https://www.dpec.com.ar/1500/Cuadro-Tarifario", r"/descarga/.*CUADRO", r"cuadro"), se="dpec",
    known="https://www.dpec.com.ar/es/articulo/1500/descarga/165/CUADRO-TARIFARIO-108-Dpdf")
src("enersa", "ENERSA", "Energía de Entre Ríos S.A.", "Entre Ríos", epre_entre_rios, ORIGEN_ENTE, "enersa")
src("die", "DIE", "Dirección de Infraestructura Eléctrica", "Formosa", None, se=None,
    nota="No se encontró una fuente pública de cuadro tarifario.")
src("refsa", "REFSA", "Recursos y Energía Formosa S.A.", "Formosa",
    refsa, se="refsa")
src("ejesa", "EJE S.A.", "Empresa Jujeña de Energía S.A.", "Jujuy",
    getfile_page("https://www.ejesa.com.ar/info/pwa/institucional/costos-del-servicio", r"cuadro tarif"), se="eje-sa")
src("ejsed", "EJSED S.A.", "Empresa Jujeña de Sistemas Energéticos Dispersos S.A.", "Jujuy",
    None, se="ejsed-sa",
    known="https://ejsedsa.com.ar/wp-content/uploads/2026/06/CT-EJSEDSA-WEB-_-Res-198-2026-_-Mayo-a-Octubre-2026.pdf")
src("ape", "APE", "Administración Provincial de Energía", "La Pampa",
    page_latest("https://seym.lapampa.gob.ar/informacion-publica/tarifas-electricas/2026", r"Cuadro-Tarifario.*\.pdf"),
    ORIGEN_ENTE, "ape")
src("edelar", "EDELAR", "Empresa Distribuidora de Electricidad de La Rioja S.A.", "La Rioja",
    fixed("https://www.edelar.com.ar/files.php?f=cuadro-tarifario.pdf", "Cuadro tarifario vigente (EDELAR)"), se="edelar")
src("edemsa", "EDEMSA", "Empresa Distribuidora de Electricidad de Mendoza S.A.", "Mendoza",
    page_latest("https://epremendoza.gob.ar/home/", r"cuadrosT-Vigentes/CT.*20\d\d\.pdf$"), ORIGEN_ENTE, "edemsa",
    parser="mendoza", nota="Mendoza publica un único cuadro tarifario (EPRE) para todas sus distribuidoras.")
src("edeste", "EDESTE", "Empresa Distribuidora de Electricidad del Este S.A.", "Mendoza",
    page_latest("https://epremendoza.gob.ar/home/", r"cuadrosT-Vigentes/CT.*20\d\d\.pdf$"), ORIGEN_ENTE, "edeste",
    parser="mendoza", nota="Mendoza publica un único cuadro tarifario (EPRE) para todas sus distribuidoras.")
src("emsa", "EMSA", "Energía de Misiones S.A.", "Misiones",
    page_latest("https://energia.misiones.gob.ar/cuadro-tarifario/", r"boletines/\d+\.pdf$", exclude_re=r"peaje|balance|neto"),
    "Boletín Oficial de Misiones", se="emsa")
src("epen", "EPEN", "Ente Provincial de Energía del Neuquén", "Neuquén",
    page_latest("https://www.epen.gov.ar/index.php/cuadros-tarifarios/", r"/uploads/.*CT.*\.pdf$"), se="epen")
src("edersa", "EDERSA", "Empresa de Energía de Río Negro S.A.", "Río Negro",
    page_latest("https://www.edersa.com.ar/usuarios/cuadro-tarifario/", r"/uploads/.*(CT|cuadro).*\.pdf$", exclude_re=r"anexo"),
    se="edersa")
src("edesa", "EDESA", "Empresa Distribuidora de Electricidad de Salta S.A.", "Salta",
    page_latest("https://www.edesa.com.ar/informacion-regulatoria/", r"/uploads/.*(CT|cuadro).*\.pdf$", exclude_re=r"ESED"), se="edesa",
    nota="El PDF usa fuentes sin mapa de caracteres (el texto no se puede extraer): los valores se leen por OCR, con las tablas apaisadas giradas.")
src("esj", "ESJ", "Energía San Juan S.A. (Naturgy San Juan)", "San Juan",
    page_latest("https://www.naturgysj.com.ar/hogar/cuadro-tarifario/", r"uploads/.*CT.*ESJ.*\.pdf$"), se="esj-0")
src("edesal", "EDESAL", "Empresa Distribuidora San Luis S.A.", "San Luis",
    page_latest("https://edesalenergia.com.ar/eener/cuadro_tarifario.html", r"\.pdf$"), se="edesal-sa")
src("spse", "SPSE", "Servicios Públicos Sociedad del Estado", "Santa Cruz", None, se="spse-0",
    nota="El sitio de SPSE no responde desde el servidor del scraper.")
src("epe", "EPE", "Empresa Provincial de la Energía de Santa Fe", "Santa Fe", epe, se="epe", parser="epe")
src("edese", "EDESE", "Empresa Distribuidora de Electricidad de Santiago del Estero S.A.", "Santiago del Estero",
    fixed("https://www.edese.com.ar/public/assets/archivos/CuadroTarifarioVigente.pdf", "Cuadro tarifario vigente (EDESE)"), se="edese")
src("dpe", "DPE", "Dirección Provincial de Energía de Tierra del Fuego", "Tierra del Fuego",
    page_latest("https://www.dpe.com.ar/usuarios/cuadro_tarifario/", r"assets/usuarios/.*Tarifa.*\.pdf$"), se="dpe")
src("edet", "EDET", "Empresa de Distribución Eléctrica de Tucumán S.A.", "Tucumán",
    getfile_page("https://www.edetsa.com/info/pwa/institucional/costos-del-servicio", r"cuadro tarifario vigente"), se="edet")

SOURCES = S


# PDFs whose text layer is unusable (images, or fonts without a character map): use OCR.
for _s in SOURCES:
    if _s["id"] in ("edelap", "dpe", "edesa"):
        _s["ocr"] = True
    if _s["id"] == "edesa":
        _s["ocr_dpi"] = 400  # small table text; at 300 dpi the engines disagree on the T1R1 row
