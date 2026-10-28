const $ = (s) => document.querySelector(s);
const ESTADO = { ok: "Valores extraídos", documento: "Solo documento oficial", sin_datos: "Sin fuente disponible" };
const fmt = (v) => v === null || v === undefined ? '<span class="empty">sin dato</span>'
  : v.toLocaleString("es-AR", { maximumFractionDigits: 4 });
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const dfmt = (iso) => iso ? new Date(iso).toLocaleString("es-AR", { dateStyle: "medium", timeStyle: "short" }) : "";
let DATA = null, HIST = [];
const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
const mesfmt = (ym) => ym ? `${MESES[+ym.slice(5, 7) - 1]} ${ym.slice(0, 4)}` : "";
const VIEJO = '<span class="badge b-viejo" title="El documento corresponde a hace más de 2 meses: puede seguir vigente, pero conviene confirmarlo">Documento de hace más de 2 meses</span>';

function tableHTML(t) {
  const maxv = Math.max(...t.filas.map((f) => f.valores.length));
  const cols = t.filas.find((f) => f.columnas && f.columnas.length === maxv)?.columnas;
  let h = `<div class="tbl"><h4>${esc(t.titulo)}</h4><div class="tablewrap"><table><thead><tr><th>Concepto</th><th>Unidad</th>`;
  for (let i = 0; i < maxv; i++) h += `<th>${esc(cols ? cols[i] : (maxv > 1 ? `Valor ${i + 1}` : "Valor"))}</th>`;
  h += "</tr></thead><tbody>";
  let g = null;
  for (const f of t.filas) {
    if (f.grupo && f.grupo !== g) { g = f.grupo; h += `<tr class="grp"><td colspan="${maxv + 2}">${esc(g)}</td></tr>`; }
    const own = f.columnas && cols && f.columnas.join() !== cols.join() ? ` title="Columnas: ${esc(f.columnas.join(" | "))}"` : "";
    h += `<tr${own}><td>${esc(f.concepto)}</td><td>${esc(f.unidad || "")}</td>`;
    for (let i = 0; i < maxv; i++) h += `<td class="num">${i < f.valores.length ? fmt(f.valores[i]) : ""}</td>`;
    h += "</tr>";
  }
  return h + "</tbody></table></div></div>";
}

function normHTML(e) {
  const n = e.normalizado, d = e.documento;
  let h = `<div class="tbl norm"><h4>Cuadro normalizado</h4><p class="note">Misma estructura para todas las distribuidoras: los valores salen de las filas del documento oficial${d ? ` (<a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.titulo || "documento")}</a>)` : ""} que usa el simulador. Lo que el cuadro no trae queda vacío.</p>`;
  h += `<div class="tablewrap"><table><thead><tr><th>Concepto</th><th>Tramo / franja</th><th>Unidad</th><th>Valor</th></tr></thead><tbody>`;
  let sec = null, cat = null;
  for (const f of n.filas) {
    if (f.seccion !== sec) { sec = f.seccion; cat = null; h += `<tr class="sec"><td colspan="4">${esc(sec)}</td></tr>`; }
    const k = [f.categoria, f.condicion, f.tension].join("|");
    if (k !== cat) {
      cat = k;
      h += `<tr class="grp"><td colspan="4">${[f.categoria, f.tension, f.condicion].filter(Boolean).map(esc).join(" · ")}</td></tr>`;
    }
    h += `<tr><td>${esc(f.concepto)}</td><td>${esc(f.tramo)}</td><td>${esc(f.unidad)}</td><td class="num">${fmt(f.valor)}</td></tr>`;
  }
  h += "</tbody></table></div>";
  if (n.notas.length) h += `<ul class="note">${n.notas.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
  return h + "</div>";
}

const link = (u, t) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(t)}</a>`;
const ymfmt = (ym) => `${ym.slice(5, 7)}-${ym.slice(0, 4)}`;
function seHTML(e) {
  const d = e.documento, a = e.archivo_nacional, r = e.fuente_reemplazada;
  if (d && d.via === "archivo nacional") return `<dt>Fuente nacional</dt><dd>Este documento sale del archivo de la Secretaría de Energía (Argentina.gob.ar) porque ${esc(d.motivo || "la fuente propia no respondió")}.${r ? ` Documento de la fuente propia: ${link(r.url, r.titulo || r.url)}.` : ""}</dd>`;
  if (!a) return "";
  let h = "<dt>Fuente nacional</dt><dd>" + (a.url ? `${link(a.url, a.titulo)} en el ${link(a.pagina, "archivo de la Secretaría de Energía")}`
    : `El ${link(a.pagina, "archivo de la Secretaría de Energía")} no tiene ningún archivo que se pueda descargar.`);
  if (a.no_disponibles?.length) h += `<br><span class="note">Listados pero no descargables: ${esc(a.no_disponibles.map((x) => `${ymfmt(x.periodo)} (${x.error})`).join(", "))}.</span>`;
  const c = a.comparacion || {};
  const txt = {
    mas_viejo: `Es más viejo que el documento usado (${mesfmt(c.periodo_propio)}): se usa la fuente propia.`,
    mismo: "Es del mismo período que el documento usado: se usa la fuente propia, más cercana a la resolución." + (c.total ? ` Coinciden ${c.coinciden} de ${c.total} valores extraídos.` : ""),
    sin_fecha: "No se pudo leer la fecha del documento usado, así que no se puede saber cuál es más nuevo.",
  }[c.resultado];
  if (txt) h += `<br><span class="note">${esc(txt)}</span>`;
  if (c.resultado === "mismo" && c.total && c.coinciden < c.total) h += ' <span class="badge b-viejo" title="Algunos valores de la fuente propia no aparecen en el archivo nacional del mismo período">Discrepancia con el archivo nacional</span>';
  return h + "</dd>";
}

function card(e) {
  const d = e.documento;
  const stale = e.ultimo_intento_fallido ? `<span class="badge b-stale">Último intento fallido</span>` : "";
  const via = d && d.via === "archivo nacional" ? (e.fuente_reemplazada ? `<span class="badge b-old" title="${esc(d.motivo || "")}">${e.fuente_reemplazada.mismo_texto ? "Archivo nacional (mismo cuadro, con su fecha)" : "Archivo nacional (más nuevo que la fuente propia)"}</span>` : `<span class="badge b-old">Archivo nacional (puede no ser el vigente)</span>`)
    : d && d.archivado ? `<span class="badge b-old" title="El sitio oficial no responde: el documento es la copia guardada por el Internet Archive">Copia archivada</span>` : "";
  let body = "";
  if (e.desactualizado) body += `<div class="alert viejo"><b>Documento de hace más de 2 meses.</b> El mes de referencia (${esc(mesfmt(e.mes_referencia))}, según ${esc(e.mes_referencia_origen)}) es de hace más de 2 meses. No se encontró un cuadro más nuevo en las fuentes consultadas; puede seguir vigente, pero conviene confirmarlo con la distribuidora o el ente regulador.</div>`;
  if (e.ocr) body += `<div class="alert ocr"><b>Valores leídos por OCR</b> del PDF escaneado. Solo se muestra un número si dos motores de OCR independientes (Tesseract y RapidOCR) leen exactamente lo mismo; si no coinciden, la celda queda vacía. Los textos de filas, encabezados y unidades son la lectura de Tesseract y pueden tener errores; los nombres de columna se muestran solo cuando el encabezado se leyó claramente. Verificá contra el documento antes de usar un valor.</div>`;
  body += `<dl class="kv">
    <dt>Razón social</dt><dd>${esc(e.nombre)}</dd>
    <dt>Vigencia (según documento)</dt><dd>${e.vigencia ? esc(e.vigencia) : '<span class="empty">sin dato</span>'}</dd>
    <dt>Mes de referencia</dt><dd>${e.mes_referencia ? `${esc(mesfmt(e.mes_referencia))} <span class="note">(según ${esc(e.mes_referencia_origen)})</span>` : '<span class="empty">sin dato</span>'}</dd>`;
  if (d) body += `<dt>Documento oficial</dt><dd><a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.titulo || d.url)}</a> (${esc(d.tipo)})</dd>
    <dt>Fuente</dt><dd>${esc(d.origen)} — ${esc(d.via)}${d.pagina ? ` · <a href="${esc(d.pagina)}" target="_blank" rel="noopener">página de publicación</a>` : ""}</dd>
    <dt>SHA-256</dt><dd><code>${esc(d.sha256.slice(0, 16))}…</code></dd>`;
  body += `<dt>Verificado</dt><dd>${dfmt(e.verificado)}${e.ultimo_intento ? ` · último intento: ${dfmt(e.ultimo_intento)}` : ""}</dd>`;
  if (e.texto) body += `<dt>Texto extraído</dt><dd><a href="data/textos/${e.id}.txt" target="_blank">ver texto completo del documento</a></dd>`;
  if (d && d.archivado) body += `<dt>Copia archivada</dt><dd>El sitio oficial no responde desde el servidor del scraper. El documento se descargó de la copia guardada por el ${esc(d.archivado.servicio)} el ${esc(d.archivado.captura)}. <a href="${esc(d.archivado.url_original)}" target="_blank" rel="noopener">URL original</a>${d.archivado.pagina_captura ? ` · <a href="${esc(d.archivado.pagina_captura)}" target="_blank" rel="noopener">página archivada</a>` : ""}. Puede existir un cuadro más nuevo que no fue archivado.</dd>`;
  if (d && d.resolucion) body += `<dt>Resolución</dt><dd><a href="${esc(d.resolucion)}" target="_blank" rel="noopener">${esc(d.resolucion.split("/").pop())}</a></dd>`;
  body += seHTML(e);
  if (e.nota) body += `<dt>Nota</dt><dd>${esc(e.nota)}</dd>`;
  if (!e.ocr && e.escaneado) body += `<dt>Aviso</dt><dd>El PDF es una imagen escaneada y el OCR no obtuvo valores coincidentes.</dd>`;
  body += "</dl>";
  if (e.normalizado) body += normHTML(e);
  else if (e.tablas.length) body += `<p class="note"><b>Sin cuadro normalizado:</b> la estructura de este cuadro no se pudo armar con seguridad. Abajo están los valores tal como figuran en el documento.</p>`;
  if (e.tablas.length) {
    const raw = e.tablas.map(tableHTML).join("");
    body += e.normalizado ? `<details class="raw"><summary>Cuadro original completo (tal como figura en el documento, ${e.tablas.length} tabla${e.tablas.length > 1 ? "s" : ""})</summary>${raw}</details>` : raw;
  } else body += `<p class="note">No hay valores extraídos automáticamente para esta distribuidora. ${d ? "Consultá el documento oficial." : ""}</p>`;
  if (e.intentos?.length) body += `<details><summary class="note">Registro técnico</summary><pre class="note">${esc(e.intentos.join("\n"))}</pre></details>`;
  return `<details class="card e-${e.estado}" id="d-${e.id}"><summary><div><h3>${esc(e.empresa)}</h3><span class="prov">${esc(e.provincia)}</span></div>
    <div class="badges"><span class="badge b-${e.estado}">${ESTADO[e.estado]}</span>${e.ocr ? '<span class="badge b-ocr">OCR</span>' : ""}${e.desactualizado ? VIEJO : ""}${via}${stale}</div>
    <span class="vig">${e.mes_referencia ? esc(mesfmt(e.mes_referencia)) : ""}<span class="chev">›</span></span></summary><div class="body">${body}</div></details>`;
}

function matches(e, q) {
  if (!q) return true;
  const hay = [e.empresa, e.nombre, e.provincia, ...e.tablas.flatMap((t) => [t.titulo, ...t.filas.map((f) => f.concepto + " " + (f.grupo || ""))])].join(" ").toLowerCase();
  return q.toLowerCase().split(/\s+/).every((w) => hay.includes(w));
}

function renderList() {
  const prov = $("#f-prov").value, est = $("#f-estado").value, q = $("#f-q").value.trim();
  const okEst = (e) => !est || (est === "viejo" ? e.desactualizado : e.estado === est);
  const items = DATA.distribuidoras.filter((e) => (!prov || e.provincia === prov) && okEst(e) && matches(e, q));
  const cnt = (s) => DATA.distribuidoras.filter((e) => (s === "viejo" ? e.desactualizado : e.estado === s)).length;
  $("#stats").innerHTML = [["ok", "con valores extraídos"], ["documento", "solo documento oficial"], ["sin_datos", "sin fuente disponible"], ["viejo", "documento de hace más de 2 meses"]]
    .map(([k, l]) => `<button class="stat s-${k}${est === k ? " sel" : ""}" data-est="${k}"><b>${cnt(k)}</b><span>${l}</span></button>`).join("");
  $("#stats-about").innerHTML = $("#stats").innerHTML.replaceAll("<button", "<div").replaceAll("</button>", "</div>");
  document.querySelectorAll("#stats .stat").forEach((b) => b.addEventListener("click", () => { $("#f-estado").value = $("#f-estado").value === b.dataset.est ? "" : b.dataset.est; renderList(); }));
  $("#summary").textContent = `Mostrando ${items.length} de ${DATA.distribuidoras.length} distribuidoras`;
  $("#list").innerHTML = items.map(card).join("") || '<p class="note">Sin resultados.</p>';
  if (q) document.querySelectorAll("#list details.card").forEach((d) => (d.open = true));
}

const COMP = { sort: null, dir: 1 };
const PER = (s) => (s.periodo === "bimestre" ? "bim" : "mes");
const rango = (a, b, u) => (b === null ? `más de ${num(a, 0)} ${u}` : `${num(a, 0)}–${num(b, 0)} ${u}`);
function compSim(e, modo, ocr) {
  const plain = e.simulador || (ocr ? e.simulador_ocr : null);
  if (modo === "sub" && e.simulador_subsidio) return { s: e.simulador_subsidio, sub: true };
  return plain ? { s: plain, sub: false, ocr: !e.simulador } : null;
}
function compRes(e, x, crit, kwhMes, mes, aMes) {
  const s = x.s, f = s.periodo === "bimestre" ? 2 : 1, u = `kWh/${PER(s)}`;
  let i = 0, k = null;
  if (crit === "kwh") {
    k = Math.max(kwhMes, s.minimo_kwh || 0) * f;
    i = s.categorias.findIndex((c) => c.hasta === null || k <= c.hasta);
    if (i < 0) return null;
  }
  const cat = s.categorias[i], desde = i ? s.categorias[i - 1].hasta : 0, n = s.categorias.length;
  let prev = 0, tramo = "", precio = null;
  for (const [hasta, p] of cat.escalones) {
    const h = hasta === "base" ? (s.base_mes ? s.base_mes[mes - 1] : undefined) : hasta;
    if (h === undefined) { tramo = "consumo base subsidiado"; precio = p; break; }
    if (k === null || h === null || k <= h) {
      tramo = h === null ? (prev ? `más de ${num(prev, 0)} ${u}` : "todo el consumo") : `${num(prev, 0)}–${num(h, 0)} ${u}`;
      if (hasta === "base") tramo += " (consumo base subsidiado)";
      precio = p; break;
    }
    prev = h;
  }
  const conv = aMes && f === 2 && cat.fijo != null;
  return {
    cat: n === 1 ? "Residencial (categoría única)" : `Residencial ${i + 1} de ${n}`, nombre: cat.nombre || "",
    rango: n === 1 && cat.hasta === null ? "cualquier consumo" : rango(desde, cat.hasta, u) + (f === 2 ? ` (≈ ${cat.hasta === null ? "más de " + num(desde / 2, 0) : num(desde / 2, 0) + "–" + num(cat.hasta / 2, 0)} kWh/mes)` : ""),
    fact: f === 2 ? "Bimestral" : "Mensual", fijo: conv ? cat.fijo / 2 : cat.fijo,
    ufijo: f === 2 ? (conv ? "$/mes (bimestral ÷ 2)" : "$/bim") : "$/mes", precio, tramo,
  };
}
function compDem(d, q) {
  const t = d.tarifas.find((t) => (t.tension === null || t.tension === q.ten) && q.kw >= t.desde_kw && (t.hasta_kw === null || q.kw < t.hasta_kw));
  if (!t) return null;
  const pot = t.potencia.some(([, p]) => p == null) ? null : t.potencia.reduce((a, [, p]) => a + p, 0);
  const en = t.energia;
  return {
    cat: `${/T\s*-?\s*3|grande/i.test(t.nombre) ? "T3" : /T\s*-?\s*2|mediana/i.test(t.nombre) ? "T2" : t.hasta_kw !== null && t.hasta_kw <= 50 ? "T2" : "T3"}${t.tension ? " · " + t.tension : ""}`, nombre: t.nombre,
    rango: t.hasta_kw === null ? `${num(t.desde_kw, 0)} kW o más` : `${num(t.desde_kw, 0)}–${num(t.hasta_kw, 0)} kW`,
    fijo: t.fijo === 0 ? null : t.fijo, sinFijo: t.fijo === 0, pot, potDet: t.potencia.map(([c, p]) => `${c}: ${p == null ? "sin dato" : num(p, 2)}`).join(" · "),
    franjas: !("unica" in en), pico: en.pico ?? null, resto: en.unica ?? en.resto ?? en.fuera_pico ?? null, valle: en.valle ?? null,
    restoTxt: "unica" in en ? "única" : "fuera_pico" in en ? "fuera de pico" : "resto",
  };
}
const NA = '<td class="num"><span class="note" title="El cuadro tiene un único precio de energía para todas las horas">no aplica</span></td>';
function renderComp() {
  const modo = $("#c-tarifa").value, dem = modo === "dem", crit = $("#c-crit").value;
  $("#c-res-crit").hidden = dem; $("#c-dem-crit").hidden = !dem; $("#c-mes-l").hidden = dem; $("#c-kwh-l").hidden = crit !== "kwh";
  const prov = $("#c-prov").value, onlyData = $("#c-data").checked, ocr = $("#c-ocr").checked, noOld = $("#c-old").checked;
  const kwh = Math.max(0, +$("#c-kwh").value || 0), mes = new Date().getMonth() + 1, aMes = $("#c-mes").checked;
  const q = { kw: Math.max(0, +$("#c-kw").value || 0), ten: $("#c-ten").value };
  let rows = DATA.distribuidoras.filter((e) => (!prov || e.provincia === prov) && (!noOld || !e.desactualizado)).map((e) => {
    if (dem) return { e, r: e.demanda ? compDem(e.demanda, q) : null };
    const x = compSim(e, modo, ocr);
    return { e, x, r: x ? compRes(e, x, crit, kwh, mes, aMes) : null };
  });
  if (onlyData) rows = rows.filter((w) => w.r);
  const K = { empresa: (w) => w.e.empresa.toLowerCase(), provincia: (w) => w.e.provincia.toLowerCase(), mes: (w) => w.e.mes_referencia || null,
    fijo: (w) => w.r?.fijo ?? null, precio: (w) => w.r?.precio ?? null, pot: (w) => w.r?.pot ?? null, pico: (w) => w.r?.pico ?? null,
    resto: (w) => w.r?.resto ?? null, valle: (w) => w.r?.valle ?? null };
  if (COMP.sort && K[COMP.sort]) rows = sortBy(rows, K[COMP.sort], COMP.dir);
  const th = (k, l, title = "") => `<th class="sortable${COMP.sort === k ? " s" + COMP.dir : ""}" data-k="${k}"${title ? ` title="${esc(title)}"` : ""}>${l}</th>`;
  const v = (x, d) => `<td class="num">${fmt(x)}</td>`;
  const head = dem
    ? `${th("empresa", "Empresa")}${th("provincia", "Provincia")}<th>Tarifa</th><th>Rango de potencia</th>${th("fijo", "Cargo fijo<br><small>$/mes</small>")}${th("pot", "Potencia<br><small>$/kW-mes</small>", "Suma de los cargos por potencia del cuadro (pasá el mouse sobre el valor para ver el detalle)")}${th("pico", "Energía pico<br><small>$/kWh</small>")}${th("resto", "Energía resto / única<br><small>$/kWh</small>")}${th("valle", "Energía valle<br><small>$/kWh</small>")}${th("mes", "Mes de referencia")}`
    : `${th("empresa", "Empresa")}${th("provincia", "Provincia")}<th>Categoría</th><th>Rango de consumo</th><th>Facturación</th>${th("fijo", "Cargo fijo", aMes ? "" : "Valores tal como figuran en cada cuadro: mirá la unidad ($/mes o $/bim)")}<th>Unidad</th>${th("precio", "Energía<br><small>$/kWh</small>")}<th>Tramo</th>${th("mes", "Mes de referencia")}`;
  const ncol = dem ? 10 : 10;
  let h = `<thead><tr>${head}</tr></thead><tbody>`;
  for (const { e, x, r } of rows) {
    const name = `<td><a href="#d-${e.id}" onclick="openCard('${e.id}')">${esc(e.empresa)}</a>${x?.ocr ? ' <span class="badge b-ocr">OCR</span>' : ""}${modo === "sub" && x && !x.sub ? ' <span class="badge b-old">sin subsidio publicado</span>' : ""}</td><td>${esc(e.provincia)}</td>`;
    const ref = `<td>${esc(mesfmt(e.mes_referencia))}${e.desactualizado ? ' <span class="badge b-viejo">+2 meses</span>' : ""}</td>`;
    if (!r) {
      const why = dem ? (e.demanda ? "El cuadro no tiene una tarifa para esa potencia y tensión" : "Sin estructura homogénea de T2/T3") : "Sin estructura homogénea";
      h += `<tr class="muted">${name}<td colspan="${ncol - 3}" class="note">${why}: ver el cuadro original en la ficha.</td>${ref}</tr>`;
      continue;
    }
    if (dem) {
      h += `<tr>${name}<td title="${esc(r.nombre)}">${esc(r.cat)}</td><td>${esc(r.rango)}</td><td class="num">${r.sinFijo ? '<span class="note" title="El cuadro no tiene cargo fijo mensual">no tiene</span>' : fmt(r.fijo)}</td><td class="num" title="${esc(r.potDet)}">${fmt(r.pot)}</td>${r.franjas ? v(r.pico) : NA}<td class="num">${fmt(r.resto)}${r.resto != null ? ` <small class="note">${r.restoTxt}</small>` : ""}</td>${r.franjas && "valle" in (e.demanda.tarifas.find((t) => t.nombre === r.nombre)?.energia || {}) ? v(r.valle) : NA}${ref}</tr>`;
    } else {
      const pago = r.fact === "Bimestral" && e.pago_mensual ? `<br><small class="note"><a href="${esc(e.pago_mensual.url)}" target="_blank" rel="noopener" title="${esc(e.pago_mensual.texto)}">se paga en 2 cuotas mensuales</a></small>` : "";
      h += `<tr>${name}<td title="${esc(r.nombre)}">${esc(r.cat)}</td><td>${esc(r.rango)}</td><td>${r.fact}${pago}</td>${v(r.fijo)}<td>${esc(r.ufijo)}</td>${v(r.precio)}<td>${esc(r.tramo)}</td>${ref}</tr>`;
    }
  }
  if (!rows.length) h += `<tr><td colspan="${ncol}" class="note">Ninguna distribuidora cumple los filtros.</td></tr>`;
  $("#comp").innerHTML = h + "</tbody>";
  const n = rows.filter((w) => w.r).length;
  $("#c-summary").innerHTML = `${n} distribuidoras con estructura homogénea de ${DATA.distribuidoras.length}` + (dem ? ` · ${num(q.kw, 0)} kW en ${q.ten}` : crit === "kwh" ? ` · consumo de ${num(kwh, 0)} kWh/mes` : " · primer escalón") + (modo === "sub" ? ` · con subsidio donde el cuadro lo publica (consumo base de ${MESES[mes - 1]})` : "");
  document.querySelectorAll("#comp th.sortable").forEach((t) => t.addEventListener("click", () => {
    COMP.dir = COMP.sort === t.dataset.k ? -COMP.dir : 1; COMP.sort = t.dataset.k; renderComp();
  }));
}
function sortBy(rows, k, dir) {
  return [...rows].sort((a, b) => {
    const x = k(a), y = k(b);
    if (x === y) return 0; if (x === null) return 1; if (y === null) return -1;
    return (x < y ? -1 : 1) * dir;
  });
}

// ---- Simulador: same algorithm as scraper/simulador.py::cost ----
function simulate(s, kwhMes, mes) {
  const f = s.periodo === "bimestre" ? 2 : 1, k = Math.max(kwhMes, s.minimo_kwh || 0) * f;
  const cat = s.categorias.find((c) => c.hasta === null || k <= c.hasta);
  const r = { k, f, cat, tramos: [], total: null };
  if (!cat || cat.fijo == null) return r;
  let tot = cat.fijo, prev = 0;
  for (let [hasta, p] of cat.escalones) {
    if (hasta === "base") { if (!s.base_mes || !mes) return r; hasta = s.base_mes[mes - 1]; }
    const top = hasta === null ? k : Math.min(k, hasta), kwh = Math.max(0, top - prev);
    if (kwh && p == null) return r;
    if (kwh) r.tramos.push({ kwh, p });
    tot += kwh * (p || 0);
    prev = hasta === null ? k : hasta;
    if (prev >= k) break;
  }
  r.periodoTotal = tot; r.total = tot / f;
  return r;
}
const money = (v) => "$ " + v.toLocaleString("es-AR", { maximumFractionDigits: 0 });
const num = (v, d = 4) => v.toLocaleString("es-AR", { maximumFractionDigits: d });
const SIM = { prov: "", modo: "costo" };
// ---- T2/T3: same algorithm as scraper/simulador.py::cost_demanda ----
function demInputs() {
  const pico = Math.min(100, Math.max(0, +$("#d-pico").value || 0)) / 100;
  const valle = Math.min(1 - pico, Math.max(0, +$("#d-valle").value || 0) / 100);
  return { kw: Math.max(0, +$("#d-kw").value || 0), ten: $("#d-ten").value, kwh: Math.max(0, +$("#d-kwh").value || 0), pico, valle };
}
function simulateDem(d, q) {
  const t = d.tarifas.find((t) => (t.tension === null || t.tension === q.ten) && q.kw >= t.desde_kw && (t.hasta_kw === null || q.kw < t.hasta_kw));
  const r = { t, parts: [], total: null };
  if (!t) return r;
  const e = t.energia;
  const rep = "unica" in e ? { unica: 1 } : "fuera_pico" in e ? { pico: q.pico, fuera_pico: 1 - q.pico } : { pico: q.pico, resto: 1 - q.pico - q.valle, valle: q.valle };
  const NAME = { unica: "Energía", pico: "Energía en pico", fuera_pico: "Energía fuera de pico", resto: "Energía en resto", valle: "Energía en valle" };
  r.parts.push({ txt: "Cargo fijo", v: t.fijo });
  for (const [c, p] of t.potencia) r.parts.push({ txt: `${c}: ${num(q.kw, 1)} kW × ${p == null ? "—" : num(p, 2)} $/kW-mes`, v: p == null ? null : p * q.kw });
  for (const [k, sh] of Object.entries(rep)) {
    const kwh = q.kwh * sh, p = e[k];
    r.parts.push({ txt: `${NAME[k]}: ${num(kwh, 0)} kWh × ${p == null ? "—" : num(p)} $/kWh`, v: p == null ? null : p * kwh });
  }
  if (r.parts.every((x) => x.v != null)) r.total = r.parts.reduce((a, x) => a + x.v, 0);
  return r;
}
function simLabel() {
  if ($("#s-tipo").value === "res") return `${num(+$("#s-kwh").value || 0, 0)} kWh/mes`;
  const q = demInputs();
  return `${num(q.kw, 1)} kW en ${q.ten}, ${num(q.kwh, 0)} kWh/mes`;
}
function ivaRate() {
  const o = $("#s-iva"), res = $("#s-tipo").value !== "dem";
  o.options[2].disabled = res;
  if (res && o.value === "0.27") o.value = "0.21";
  return +o.value || 0;
}
const withIva = (x, iva) => Object.assign(x, { iva, base: x.total, total: x.total === null ? null : x.total * (1 + iva) });
function ivaRows(x) {
  if (!x.iva || x.base === null) return "";
  return `<tr><td>IVA ${num(100 * x.iva, 0)} % (Ley 23.349, art. 28)</td><td class="num">${money(x.base * x.iva)}</td></tr>` +
    `<tr><td><b>Total mensual con IVA</b> (sin impuestos provinciales ni tasas municipales)</td><td class="num"><b>${money(x.total)}</b> /mes</td></tr>`;
}
function simResults() {
  const iva = ivaRate();
  if ($("#s-tipo").value === "dem") {
    const q = demInputs();
    return DATA.distribuidoras.map((e) => {
      let r = null, motivo = "";
      if (e.demanda) {
        r = simulateDem(e.demanda, q);
        if (!r.t) motivo = "El cuadro no tiene una tarifa T2/T3 para esa potencia y tensión";
        else if (r.total === null) motivo = "Al cuadro le faltan cargos para esta tarifa";
      } else motivo = e.estado !== "ok" ? "Sin valores extraídos" : e.ocr ? "Valores leídos por OCR: no se usan en el simulador" : "Las tarifas T2/T3 de este cuadro todavía no están cargadas en el simulador";
      return withIva({ e, r, total: r ? r.total : null, motivo, dem: true }, iva);
    });
  }
  const kwh = Math.max(0, +$("#s-kwh").value || 0), sub = $("#s-sub").checked, mes = +$("#s-mes").value;
  return DATA.distribuidoras.map((e) => {
    let r = null, motivo = "";
    const sim = (sub && e.simulador_subsidio) || e.simulador || ($("#s-ocr").checked ? e.simulador_ocr : null);
    if (sim) { r = simulate(sim, kwh, mes); if (r.total === null) motivo = "Al cuadro le faltan cargos o escalones para este consumo"; }
    else if (e.estado !== "ok") motivo = e.estado === "documento" ? "Sin valores extraídos (solo documento)" : "Sin fuente disponible";
    else if (e.ocr) motivo = e.simulador_ocr ? "Valores leídos por OCR: activá «Incluir valores leídos por OCR»" : "Valores leídos por OCR: la estructura del cuadro no se pudo armar con seguridad";
    else motivo = "La estructura de este cuadro todavía no está cargada en el simulador";
    return withIva({ e, r, total: r ? r.total : null, motivo, sim, mes, sub }, iva);
  });
}
function detalleDem(x) {
  const d = x.e.demanda, r = x.r;
  let h = `<div class="sim-det"><p><b>Criterio:</b> ${esc(d.criterio)} · <b>Tarifa:</b> ${esc(r.t ? r.t.nombre : "no encontrada")}</p>`;
  if (!r.t || r.total === null) return h + `<p class="note">${esc(x.motivo)}.</p></div>`;
  h += "<table><tbody>";
  for (const p of r.parts) h += `<tr><td>${esc(p.txt)}</td><td class="num">${money(p.v)}</td></tr>`;
  return h + `<tr><td><b>Total mensual</b></td><td class="num"><b>${money(r.total)}</b> /mes</td></tr>${ivaRows(x)}</tbody></table></div>`;
}
function detalle(x) {
  if (x.dem) return detalleDem(x);
  const s = x.sim, r = x.r, per = s.periodo === "bimestre" ? "bim" : "mes";
  let h = `<div class="sim-det"><p><b>Criterio:</b> ${esc(s.criterio)} · <b>Categoría:</b> ${esc(r.cat ? r.cat.nombre || "única" : "no encontrada")}</p>`;
  if (s.base_mes) h += `<p>Consumo base subsidiado en ${MESES[x.mes - 1]}: <b>${num(s.base_mes[x.mes - 1], 0)} kWh/${per}</b>; el resto se cobra al precio de excedente.</p>`;
  if (r.f === 2) h += `<p>El cuadro factura por <b>bimestre</b>: se calcula con ${num(r.k, 1)} kWh/bimestre (${num(r.k / 2, 1)} kWh/mes × 2) y el resultado se divide por 2.</p>`;
  if (r.total === null) return h + `<p class="note">${esc(x.motivo)}.</p></div>`;
  h += `<table><tbody><tr><td>Cargo fijo</td><td class="num">${money(r.cat.fijo)} /${per}</td></tr>`;
  for (const t of r.tramos) h += `<tr><td>${num(t.kwh, 1)} kWh × ${num(t.p)} $/kWh</td><td class="num">${money(t.kwh * t.p)}</td></tr>`;
  h += `<tr><td><b>Total del período</b></td><td class="num"><b>${money(r.periodoTotal)}</b> /${per}</td></tr>`;
  if (r.f === 2) h += `<tr><td><b>Equivalente mensual</b> (÷ 2)</td><td class="num"><b>${money(r.total)}</b> /mes</td></tr>`;
  return h + ivaRows(x) + "</tbody></table></div>";
}
function renderSim() {
  const q = demInputs();
  $("#d-resto").textContent = `Resto ${num(Math.max(0, 100 * (1 - q.pico - q.valle)), 0)} %`;
  $("#s-mes-l").hidden = !$("#s-sub").checked || $("#s-tipo").value === "dem";
  const all = simResults(), showAll = $("#s-all").checked;
  let rows = all.filter((x) => (!SIM.prov || x.e.provincia === SIM.prov) && (showAll || x.total !== null));
  rows = sortBy(rows, (x) => x.total, 1);
  const max = Math.max(...all.map((x) => x.total || 0));
  let h = "";
  for (const x of rows) {
    const bar = x.total !== null ? `<div class="bar"><span style="width:${(100 * x.total / max).toFixed(1)}%"></span><b>${money(x.total)}</b></div>` : `<span class="empty">sin resultado</span> <span class="note">${esc(x.motivo)}</span>`;
    const badges = (!x.dem && x.sim && x.sim === x.e.simulador_subsidio ? '<span class="badge b-sub" title="Cargos con subsidio publicados en el cuadro">con subsidio</span> ' : "") + (!x.dem && x.sub && x.sim && x.sim !== x.e.simulador_subsidio ? '<span class="badge b-old" title="El cuadro no publica cargos con subsidio que se puedan aplicar con seguridad: se muestra el valor sin subsidio">sin subsidio publicado</span> ' : "") + (!x.dem && x.sim && x.sim === x.e.simulador_ocr ? '<span class="badge b-ocr" title="Valores leídos por OCR: pueden tener errores">OCR</span> ' : "") + (!x.dem && x.sim?.periodo === "bimestre" ? '<span class="badge b-old" title="El cuadro es bimestral: se convirtió dentro del cálculo">bimestral → mes</span>' : "") + (x.e.desactualizado ? ' <span class="badge b-viejo">+2 meses</span>' : "");
    h += `<details class="simrow"${x.total === null ? ' data-empty=""' : ""}><summary><span class="sn"><a href="#d-${x.e.id}" onclick="openCard('${x.e.id}')">${esc(x.e.empresa)}</a><small>${esc(x.e.provincia)}</small></span>${bar}<span class="sb">${badges}</span></summary>${x.r ? detalle(x) : ""}</details>`;
  }
  const n = all.filter((x) => x.total !== null).length;
  $("#s-list").innerHTML = h || '<p class="note">Ninguna distribuidora con resultado para este filtro.</p>';
  $("#s-summary").innerHTML = `${n} de ${all.length} distribuidoras con resultado para ${esc(simLabel())}` + (!all[0]?.dem && $("#s-sub").checked ? ` · <b>con subsidio</b> donde el cuadro lo publica (mes del subsidio: ${MESES[+$("#s-mes").value - 1]}); las demás, sin subsidio` : "") + (all[0]?.iva ? ` · <b>con IVA ${num(100 * all[0].iva, 0)} %</b>, sin impuestos provinciales ni tasas municipales` : " · sin impuestos") + (SIM.prov ? ` · provincia: <b>${esc(SIM.prov)}</b> <button class="link" id="s-clear">quitar filtro</button>` : "");
  $("#s-clear")?.addEventListener("click", () => { SIM.prov = ""; renderSim(); });
  renderMap(all);
}

// ---- Mapa ----
let MAP = null;
const MAPNAME = { "Ciudad Autónoma de Buenos Aires": "Ciudad de Buenos Aires y GBA", "Tierra del Fuego, Antártida e Islas del Atlántico Sur": "Tierra del Fuego" };
const RAMP = ["#dbe7f5", "#a9c4e6", "#6f9bd1", "#3b6fb0", "#173f73"];
const AVAIL = { ok: ["#2f62a3", "Con valores extraídos"], documento: ["#9db7d8", "Solo documento oficial"], sin_datos: ["#c3cad4", "Sin fuente disponible"] };
function renderMap(all) {
  if (!MAP) return;
  const modo = $("#m-modo").value;
  const byProv = {};
  for (const x of all) (byProv[x.e.provincia] ||= []).push(x);
  const vals = all.map((x) => x.total).filter((v) => v !== null);
  const lo = Math.min(...vals), hi = Math.max(...vals), bin = (v) => Math.min(4, Math.floor(((v - lo) / ((hi - lo) || 1)) * 5));
  let svg = "", caba = null;
  for (const [name, d] of Object.entries(MAP.provincias)) {
    const p = MAPNAME[name] || name, xs = byProv[p] || [];
    let fill = "#eef1f5", tip = `${p}: no hay distribuidora en el listado`;
    if (modo === "costo") {
      const ok = xs.filter((x) => x.total !== null).sort((a, b) => a.total - b.total);
      if (ok.length) {
        fill = RAMP[bin(ok[0].total)];
        tip = `${p}: ` + ok.map((x) => `${x.e.empresa} ${money(x.total)}/mes`).join(" · ") + (xs.length > ok.length ? ` (y ${xs.length - ok.length} sin resultado)` : "");
      } else if (xs.length) { fill = "#cfd6df"; tip = `${p}: ${xs.map((x) => x.e.empresa).join(", ")} — sin resultado del simulador`; }
    } else if (xs.length) {
      const best = ["ok", "documento", "sin_datos"].find((s) => xs.some((x) => x.e.estado === s));
      fill = AVAIL[best][0]; tip = `${p}: ` + xs.map((x) => `${x.e.empresa} (${ESTADO[x.e.estado].toLowerCase()})`).join(" · ");
    }
    const path = `<path d="${d}" fill="${fill}" data-p="${esc(p)}" class="${SIM.prov === p ? "sel" : ""}"><title>${esc(tip)}</title></path>`;
    if (name.startsWith("Ciudad")) caba = { path, fill, tip, p }; else svg += path;
  }
  const [vx, vy, vw, vh] = MAP.viewBox.split(" ").map(Number);
  $("#map").setAttribute("viewBox", `${vx} ${vy} ${vw + 90} ${vh}`);
  $("#map").innerHTML = svg + (caba ? caba.path : "");
  if (caba) {
    const b = $("#map path[data-p^='Ciudad']").getBBox(), cx = b.x + b.width / 2, cy = b.y + b.height / 2;
    $("#map").insertAdjacentHTML("beforeend", `<g class="caba"><line x1="${cx}" y1="${cy}" x2="${cx + 40}" y2="${cy - 18}"/><circle cx="${cx + 40}" cy="${cy - 18}" r="9" fill="${caba.fill}" data-p="${esc(caba.p)}" class="${SIM.prov === caba.p ? "sel" : ""}"><title>${esc(caba.tip)}</title></circle><text x="${cx + 52}" y="${cy - 14}">CABA</text></g>`);
  }
  document.querySelectorAll("#map [data-p]").forEach((el) => el.addEventListener("click", () => { SIM.prov = SIM.prov === el.dataset.p ? "" : el.dataset.p; renderSim(); }));
  const sw = (c, l, extra = "") => `<span><i style="background:${c}"${extra}></i>${l}</span>`;
  $("#m-legend").innerHTML = modo === "costo"
    ? RAMP.map((c, i) => sw(c, vals.length ? `${money(lo + (hi - lo) * i / 5)} – ${money(lo + (hi - lo) * (i + 1) / 5)}` : "")).join("") + sw("#cfd6df", "sin resultado del simulador") + sw("#eef1f5", "sin distribuidora en el listado")
      + '<p class="note">Color según la distribuidora más barata de la provincia para el consumo elegido; el detalle de cada una está al pasar el mouse y en la lista.</p>'
    : Object.values(AVAIL).map(([c, l]) => sw(c, l)).join("") + sw("#eef1f5", "sin distribuidora en el listado") + '<p class="note">Color según el mejor estado entre las distribuidoras de la provincia.</p>';
}

function renderHist() {
  const name = Object.fromEntries(DATA.distribuidoras.map((e) => [e.id, e.empresa]));
  let h = "<thead><tr><th>Detectado</th><th>Empresa</th><th>Documento</th><th>Vigencia</th><th>SHA-256</th></tr></thead><tbody>";
  for (const x of [...HIST].reverse()) h += `<tr><td>${dfmt(x.detectado)}</td><td>${esc(name[x.id] || x.id)}</td><td><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.titulo || x.url)}</a></td><td>${esc(x.vigencia || "")}</td><td><code>${esc(x.sha256.slice(0, 12))}</code></td></tr>`;
  $("#hist").innerHTML = h + "</tbody>";
}

window.openCard = (id) => { show("dist", false); const d = $("#d-" + id); if (d) { d.open = true; d.scrollIntoView(); } };
const SLUG = { home: "inicio", dist: "distribuidoras", ctx: "contexto", comp: "comparacion", sim: "simulador", hist: "historial", about: "metodologia", contact: "contacto" };
function show(v, top = true) {
  document.querySelectorAll("[data-view]").forEach((b) => b.classList.toggle("active", b.dataset.view === v && !b.classList.contains("tile")));
  document.querySelectorAll("main>section").forEach((s) => (s.hidden = s.id !== "view-" + v));
  document.body.classList.remove("menu-open");
  if (location.hash.slice(1) !== SLUG[v] && !(v === "dist" && location.hash.startsWith("#d-"))) history.pushState(null, "", "#" + SLUG[v]);
  if (top) window.scrollTo(0, 0);
}
function route() {
  const h = location.hash.slice(1);
  if (h.startsWith("d-")) return openCard(h.slice(2));
  show(Object.keys(SLUG).find((k) => SLUG[k] === h) || "home");
}

async function init() {
  DATA = await (await fetch("data/tarifas.json", { cache: "no-store" })).json();
  try { HIST = await (await fetch("data/historial.json", { cache: "no-store" })).json(); } catch { HIST = []; }
  $("#generado").textContent = $("#generado-f").textContent = "Última actualización: " + dfmt(DATA.generado);
  [...new Set(DATA.distribuidoras.map((e) => e.provincia))].sort().forEach((p) => $("#f-prov").insertAdjacentHTML("beforeend", `<option>${esc(p)}</option>`));
  [...new Set(DATA.distribuidoras.map((e) => e.provincia))].sort().forEach((p) => $("#c-prov").insertAdjacentHTML("beforeend", `<option>${esc(p)}</option>`));
  ["#f-prov", "#f-estado", "#f-q"].forEach((s) => $(s).addEventListener("input", renderList));
  ["#c-prov", "#c-data", "#c-ocr", "#c-old", "#c-tarifa", "#c-crit", "#c-kwh", "#c-kw", "#c-ten", "#c-mes"].forEach((s) => $(s).addEventListener("input", renderComp));
  $("#s-kwh").addEventListener("input", () => { $("#s-range").value = $("#s-kwh").value; renderSim(); });
  $("#s-range").addEventListener("input", () => { $("#s-kwh").value = $("#s-range").value; renderSim(); });
  $("#s-mes").innerHTML = MESES.map((m, i) => `<option value="${i + 1}">${m}</option>`).join("");
  $("#s-mes").value = new Date().getMonth() + 1;
  ["#s-all", "#s-ocr", "#s-sub", "#s-mes", "#s-iva", "#m-modo", "#d-kw", "#d-ten", "#d-kwh", "#d-pico", "#d-valle"].forEach((s) => $(s).addEventListener("input", renderSim));
  $("#s-tipo").addEventListener("input", () => {
    const dem = $("#s-tipo").value === "dem";
    $("#s-dem").hidden = $("#s-dem-note").hidden = !dem; $("#s-res").hidden = $("#s-res-note").hidden = dem; renderSim();
  });
  document.querySelectorAll("a[data-view]").forEach((b) => b.addEventListener("click", (ev) => { ev.preventDefault(); show(b.dataset.view); }));
  $(".menu-btn").addEventListener("click", () => document.body.classList.toggle("menu-open"));
  window.addEventListener("popstate", route);
  renderList(); renderComp(); renderHist(); renderSim(); route();
  try { MAP = await (await fetch("data/provincias.json")).json(); renderSim(); } catch { $("#map-wrap").hidden = true; }
}
init();
