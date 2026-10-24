"""Check which candidate sources respond from the current machine (used to compare VM vs GitHub Actions)."""
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "scraper")
from common import fetch  # noqa: E402

URLS = [
    "https://www.oceba.gba.gov.ar/",
    "https://oceba.gba.gov.ar/nueva_web/s.php?i=17",
    "https://www.edenargentina.com.ar/",
    "https://www.edessa.com.ar/",
    "https://www.edes.com.ar/",
    "https://boletinoficial.gba.gob.ar/",
    "https://www.gba.gob.ar/infraestructura/cuadros_tarifarios",
    "https://www.spse.gob.ar/",
    "https://www.spse.com.ar/",
    "https://seym.lapampa.gob.ar/informacion-publica/tarifas-electricas/2026",
    "https://edesalenergia.com.ar/eener/cuadro_tarifario.html",
    "https://www.epe.santafe.gov.ar/",
    "https://www.epe.santafe.gov.ar/institucional/cuadro-tarifario/",
    "https://www.santafe.gov.ar/boletinoficial/",
    "https://www.chubut.gov.ar/",
    "https://boletin.chubut.gov.ar/",
    "https://www.formosa.gob.ar/",
    "https://www.enre.gov.ar/web/TARIFASD.nsf/todoscuadros?OpenView&collapseview",
]


def probe(u):
    try:
        r = fetch(u, timeout=25)
        return f"OK   {r.status_code} {len(r.content):>8} {u} -> {r.url}"
    except Exception as e:
        return f"FAIL {type(e).__name__}: {str(e)[:70]} {u}"


with ThreadPoolExecutor(8) as ex:
    for line in ex.map(probe, URLS):
        print(line)
