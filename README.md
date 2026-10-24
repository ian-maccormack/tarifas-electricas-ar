# Cuadros tarifarios eléctricos de Argentina

Sitio estático (`site/`) con los cuadros tarifarios vigentes de las distribuidoras eléctricas de Argentina,
alimentado por un scraper en Python (`scraper/`) que corre a diario en GitHub Actions.

Regla principal: **si un valor no se puede extraer y verificar desde un documento oficial, queda vacío.**

## Cómo funciona

1. `scraper/sources.py` define cada distribuidora y cómo encontrar su cuadro vigente
   (sitio de la distribuidora / ente regulador → URL conocida → archivo de la Secretaría de Energía).
2. `scraper/run.py` descarga cada documento, guarda hash SHA-256, texto extraído (`site/data/textos/`)
   y, si hay un extractor en `scraper/parsers.py`, las filas de la tarifa residencial tal como figuran.
3. `site/data/tarifas.json` y `site/data/historial.json` alimentan `site/index.html`.

## Uso local

```bash
sudo apt-get install poppler-utils   # pdftotext
pip install -r requirements.txt
python scraper/run.py                # o: python scraper/run.py epec edesa
python -m http.server -d site 8000
```

## Publicación

El workflow `.github/workflows/update.yml` corre todos los días, commitea los datos nuevos y publica `site/`
en GitHub Pages (Settings → Pages → Source: GitHub Actions).
