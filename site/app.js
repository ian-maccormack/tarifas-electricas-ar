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

function card(e) {
  const d = e.documento;
  const stale = e.ultimo_intento_fallido ? `<span class="badge b-stale">Último intento fallido</span>` : "";
  const via = d && d.via === "archivo nacional" ? `<span class="badge b-old">Archivo nacional (puede no ser el vigente)</span>`
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
  if (e.archivo_nacional) body += `<dt>Archivo nacional</dt><dd><a href="${esc(e.archivo_nacional.url)}" target="_blank" rel="noopener">${esc(e.archivo_nacional.titulo)}</a></dd>`;
  if (e.nota) body += `<dt>Nota</dt><dd>${esc(e.nota)}</dd>`;
  if (!e.ocr && e.escaneado) body += `<dt>Aviso</dt><dd>El PDF es una imagen escaneada y el OCR no obtuvo valores coincidentes.</dd>`;
  body += "</dl>";
  if (e.tablas.length) body += e.tablas.map(tableHTML).join("");
  else body += `<p class="note">No hay valores extraídos automáticamente para esta distribuidora. ${d ? "Consultá el documento oficial." : ""}</p>`;
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
  document.querySelectorAll("#stats .stat").forEach((b) => b.addEventListener("click", () => { $("#f-estado").value = $("#f-estado").value === b.dataset.est ? "" : b.dataset.est; renderList(); }));
  $("#summary").textContent = `Mostrando ${items.length} de ${DATA.distribuidoras.length} distribuidoras`;
  $("#list").innerHTML = items.map(card).join("") || '<p class="note">Sin resultados.</p>';
  if (q) document.querySelectorAll("#list details.card").forEach((d) => (d.open = true));
}

const COMP = { sort: null, dir: 1 };
const hasComp = (e) => e.comparable && [e.comparable.cargo_fijo, e.comparable.cargo_variable].some((c) => c && c.valor != null);
const COMP_KEYS = {
  empresa: (e) => e.empresa.toLowerCase(), provincia: (e) => e.provincia.toLowerCase(),
  fijo: (e) => e.comparable?.cargo_fijo?.valor ?? null, variable: (e) => e.comparable?.cargo_variable?.valor ?? null,
  mes: (e) => e.mes_referencia || null,
};
function sortBy(rows, key, dir) {
  const k = COMP_KEYS[key] || key;
  return [...rows].sort((a, b) => {
    const x = k(a), y = k(b);
    if (x === y) return 0; if (x === null) return 1; if (y === null) return -1;
    return (x < y ? -1 : 1) * dir;
  });
}
function renderComp() {
  const prov = $("#c-prov").value, onlyData = $("#c-data").checked, noOcr = $("#c-ocr").checked, noOld = $("#c-old").checked;
  let rows = DATA.distribuidoras.filter((e) => (!prov || e.provincia === prov) && (!onlyData || hasComp(e)) && (!noOcr || !e.ocr) && (!noOld || !e.desactualizado));
  if (COMP.sort) rows = sortBy(rows, COMP.sort, COMP.dir);
  const cell = (c) => c && c.valor != null ? `<td class="num">${fmt(c.valor)}</td><td>${esc(c.unidad || "")}</td>` : '<td class="num"><span class="empty">sin dato</span></td><td></td>';
  const th = (k, l, title = "") => `<th class="sortable${COMP.sort === k ? " s" + COMP.dir : ""}" data-k="${k}"${title ? ` title="${esc(title)}"` : ""}>${l}</th>`;
  const mixed = "Ordena los valores tal como figuran en cada cuadro, sin convertir: mirá la columna Unidad ($/mes o $/bimestre)";
  let h = `<thead><tr>${th("empresa", "Empresa")}${th("provincia", "Provincia")}${th("fijo", "Cargo fijo", mixed)}<th>Unidad</th>${th("variable", "Cargo variable")}<th>Unidad</th><th>Escalón / criterio</th>${th("mes", "Mes de referencia")}</tr></thead><tbody>`;
  for (const e of rows) {
    const c = e.comparable || {};
    h += `<tr><td><a href="#d-${e.id}" onclick="openCard('${e.id}')">${esc(e.empresa)}</a></td><td>${esc(e.provincia)}</td>${cell(c.cargo_fijo)}${cell(c.cargo_variable)}<td>${esc(c.nota || "")}${e.ocr && e.comparable ? ' <span class="badge b-ocr">OCR</span>' : ""}</td><td>${esc(mesfmt(e.mes_referencia))}${e.desactualizado ? ' <span class="badge b-viejo">+2 meses</span>' : ""}</td></tr>`;
  }
  if (!rows.length) h += '<tr><td colspan="8" class="note">Ninguna distribuidora cumple los filtros.</td></tr>';
  $("#comp").innerHTML = h + "</tbody>";
  $("#c-summary").textContent = `Mostrando ${rows.length} de ${DATA.distribuidoras.length} distribuidoras`;
  document.querySelectorAll("#comp th.sortable").forEach((t) => t.addEventListener("click", () => {
    COMP.dir = COMP.sort === t.dataset.k ? -COMP.dir : 1; COMP.sort = t.dataset.k; renderComp();
  }));
}

// ---- Simulador: same algorithm as scraper/simulador.py::cost ----
function simulate(s, kwhMes) {
  const f = s.periodo === "bimestre" ? 2 : 1, k = kwhMes * f;
  const cat = s.categorias.find((c) => c.hasta === null || k <= c.hasta);
  const r = { k, f, cat, tramos: [], total: null };
  if (!cat || cat.fijo == null) return r;
  let tot = cat.fijo, prev = 0;
  for (const [hasta, p] of cat.escalones) {
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
function simResults() {
  if ($("#s-tipo").value === "dem") {
    const q = demInputs();
    return DATA.distribuidoras.map((e) => {
      let r = null, motivo = "";
      if (e.demanda) {
        r = simulateDem(e.demanda, q);
        if (!r.t) motivo = "El cuadro no tiene una tarifa T2/T3 para esa potencia y tensión";
        else if (r.total === null) motivo = "Al cuadro le faltan cargos para esta tarifa";
      } else motivo = e.estado !== "ok" ? "Sin valores extraídos" : e.ocr ? "Valores leídos por OCR: no se usan en el simulador" : "Las tarifas T2/T3 de este cuadro todavía no están cargadas en el simulador";
      return { e, r, total: r ? r.total : null, motivo, dem: true };
    });
  }
  const kwh = Math.max(0, +$("#s-kwh").value || 0);
  return DATA.distribuidoras.map((e) => {
    let r = null, motivo = "";
    if (e.simulador) { r = simulate(e.simulador, kwh); if (r.total === null) motivo = "Al cuadro le faltan cargos o escalones para este consumo"; }
    else if (e.estado !== "ok") motivo = e.estado === "documento" ? "Sin valores extraídos (solo documento)" : "Sin fuente disponible";
    else if (e.ocr) motivo = "Valores leídos por OCR: no se usan en el simulador";
    else motivo = "La estructura de este cuadro todavía no está cargada en el simulador";
    return { e, r, total: r ? r.total : null, motivo };
  });
}
function detalleDem(x) {
  const d = x.e.demanda, r = x.r;
  let h = `<div class="sim-det"><p><b>Criterio:</b> ${esc(d.criterio)} · <b>Tarifa:</b> ${esc(r.t ? r.t.nombre : "no encontrada")}</p>`;
  if (!r.t || r.total === null) return h + `<p class="note">${esc(x.motivo)}.</p></div>`;
  h += "<table><tbody>";
  for (const p of r.parts) h += `<tr><td>${esc(p.txt)}</td><td class="num">${money(p.v)}</td></tr>`;
  return h + `<tr><td><b>Total mensual</b></td><td class="num"><b>${money(r.total)}</b> /mes</td></tr></tbody></table></div>`;
}
function detalle(x) {
  if (x.dem) return detalleDem(x);
  const s = x.e.simulador, r = x.r, per = s.periodo === "bimestre" ? "bim" : "mes";
  let h = `<div class="sim-det"><p><b>Criterio:</b> ${esc(s.criterio)} · <b>Categoría:</b> ${esc(r.cat ? r.cat.nombre || "única" : "no encontrada")}</p>`;
  if (r.f === 2) h += `<p>El cuadro factura por <b>bimestre</b>: se calcula con ${num(r.k, 1)} kWh/bimestre (${num(r.k / 2, 1)} kWh/mes × 2) y el resultado se divide por 2.</p>`;
  if (r.total === null) return h + `<p class="note">${esc(x.motivo)}.</p></div>`;
  h += `<table><tbody><tr><td>Cargo fijo</td><td class="num">${money(r.cat.fijo)} /${per}</td></tr>`;
  for (const t of r.tramos) h += `<tr><td>${num(t.kwh, 1)} kWh × ${num(t.p)} $/kWh</td><td class="num">${money(t.kwh * t.p)}</td></tr>`;
  h += `<tr><td><b>Total del período</b></td><td class="num"><b>${money(r.periodoTotal)}</b> /${per}</td></tr>`;
  if (r.f === 2) h += `<tr><td><b>Equivalente mensual</b> (÷ 2)</td><td class="num"><b>${money(r.total)}</b> /mes</td></tr>`;
  return h + "</tbody></table></div>";
}
function renderSim() {
  const q = demInputs();
  $("#d-resto").textContent = `Resto ${num(Math.max(0, 100 * (1 - q.pico - q.valle)), 0)} %`;
  const all = simResults(), showAll = $("#s-all").checked;
  let rows = all.filter((x) => (!SIM.prov || x.e.provincia === SIM.prov) && (showAll || x.total !== null));
  rows = sortBy(rows, (x) => x.total, 1);
  const max = Math.max(...all.map((x) => x.total || 0));
  let h = "";
  for (const x of rows) {
    const bar = x.total !== null ? `<div class="bar"><span style="width:${(100 * x.total / max).toFixed(1)}%"></span><b>${money(x.total)}</b></div>` : `<span class="empty">sin resultado</span> <span class="note">${esc(x.motivo)}</span>`;
    const badges = (!x.dem && x.e.simulador?.periodo === "bimestre" ? '<span class="badge b-old" title="El cuadro es bimestral: se convirtió dentro del cálculo">bimestral → mes</span>' : "") + (x.e.desactualizado ? ' <span class="badge b-viejo">+2 meses</span>' : "");
    h += `<details class="simrow"${x.total === null ? ' data-empty=""' : ""}><summary><span class="sn"><a href="#d-${x.e.id}" onclick="openCard('${x.e.id}')">${esc(x.e.empresa)}</a><small>${esc(x.e.provincia)}</small></span>${bar}<span class="sb">${badges}</span></summary>${x.r ? detalle(x) : ""}</details>`;
  }
  const n = all.filter((x) => x.total !== null).length;
  $("#s-list").innerHTML = h || '<p class="note">Ninguna distribuidora con resultado para este filtro.</p>';
  $("#s-summary").innerHTML = `${n} de ${all.length} distribuidoras con resultado para ${esc(simLabel())}` + (SIM.prov ? ` · provincia: <b>${esc(SIM.prov)}</b> <button class="link" id="s-clear">quitar filtro</button>` : "");
  $("#s-clear")?.addEventListener("click", () => { SIM.prov = ""; renderSim(); });
  renderMap(all);
}

// ---- Mapa ----
let MAP = null;
const MAPNAME = { "Ciudad Autónoma de Buenos Aires": "Ciudad de Buenos Aires y GBA", "Tierra del Fuego, Antártida e Islas del Atlántico Sur": "Tierra del Fuego" };
const RAMP = ["#fff1c1", "#fdd17a", "#f9a24b", "#e8642f", "#b9301c"];
const AVAIL = { ok: ["#5cb87a", "Con valores extraídos"], documento: ["#f4b860", "Solo documento oficial"], sin_datos: ["#e98b80", "Sin fuente disponible"] };
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

window.openCard = (id) => { show("dist"); const d = $("#d-" + id); if (d) { d.open = true; d.scrollIntoView(); } };
function show(v) {
  document.querySelectorAll("nav button").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
  document.querySelectorAll("main>section").forEach((s) => (s.hidden = s.id !== "view-" + v));
}

async function init() {
  DATA = await (await fetch("data/tarifas.json", { cache: "no-store" })).json();
  try { HIST = await (await fetch("data/historial.json", { cache: "no-store" })).json(); } catch { HIST = []; }
  $("#generado").textContent = "Última actualización: " + dfmt(DATA.generado);
  [...new Set(DATA.distribuidoras.map((e) => e.provincia))].sort().forEach((p) => $("#f-prov").insertAdjacentHTML("beforeend", `<option>${esc(p)}</option>`));
  [...new Set(DATA.distribuidoras.map((e) => e.provincia))].sort().forEach((p) => $("#c-prov").insertAdjacentHTML("beforeend", `<option>${esc(p)}</option>`));
  ["#f-prov", "#f-estado", "#f-q"].forEach((s) => $(s).addEventListener("input", renderList));
  ["#c-prov", "#c-data", "#c-ocr", "#c-old"].forEach((s) => $(s).addEventListener("input", renderComp));
  $("#s-kwh").addEventListener("input", () => { $("#s-range").value = $("#s-kwh").value; renderSim(); });
  $("#s-range").addEventListener("input", () => { $("#s-kwh").value = $("#s-range").value; renderSim(); });
  ["#s-all", "#m-modo", "#d-kw", "#d-ten", "#d-kwh", "#d-pico", "#d-valle"].forEach((s) => $(s).addEventListener("input", renderSim));
  $("#s-tipo").addEventListener("input", () => {
    const dem = $("#s-tipo").value === "dem";
    $("#s-dem").hidden = $("#s-dem-note").hidden = !dem; $("#s-res").hidden = $("#s-res-note").hidden = dem; renderSim();
  });
  document.querySelectorAll("nav button").forEach((b) => b.addEventListener("click", () => show(b.dataset.view)));
  renderList(); renderComp(); renderHist(); renderSim();
  try { MAP = await (await fetch("data/provincias.json")).json(); renderSim(); } catch { $("#map-wrap").hidden = true; }
}
init();
