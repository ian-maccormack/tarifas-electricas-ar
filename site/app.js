const $ = (s) => document.querySelector(s);
const ESTADO = { ok: "Valores extraídos", documento: "Solo documento oficial", sin_datos: "Sin fuente disponible" };
const fmt = (v) => v === null || v === undefined ? '<span class="empty">sin dato</span>'
  : v.toLocaleString("es-AR", { maximumFractionDigits: 4 });
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const dfmt = (iso) => iso ? new Date(iso).toLocaleString("es-AR", { dateStyle: "medium", timeStyle: "short" }) : "";
let DATA = null, HIST = [];

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
  const via = d && d.via === "archivo nacional" ? `<span class="badge b-old">Archivo nacional (puede no ser el vigente)</span>` : "";
  let body = `<dl class="kv">
    <dt>Razón social</dt><dd>${esc(e.nombre)}</dd>
    <dt>Vigencia (según documento)</dt><dd>${e.vigencia ? esc(e.vigencia) : '<span class="empty">sin dato</span>'}</dd>`;
  if (d) body += `<dt>Documento oficial</dt><dd><a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.titulo || d.url)}</a> (${esc(d.tipo)})</dd>
    <dt>Fuente</dt><dd>${esc(d.origen)} — ${esc(d.via)}${d.pagina ? ` · <a href="${esc(d.pagina)}" target="_blank" rel="noopener">página de publicación</a>` : ""}</dd>
    <dt>SHA-256</dt><dd><code>${esc(d.sha256.slice(0, 16))}…</code></dd>`;
  body += `<dt>Verificado</dt><dd>${dfmt(e.verificado)}${e.ultimo_intento ? ` · último intento: ${dfmt(e.ultimo_intento)}` : ""}</dd>`;
  if (e.texto) body += `<dt>Texto extraído</dt><dd><a href="data/textos/${e.id}.txt" target="_blank">ver texto completo del documento</a></dd>`;
  if (e.archivo_nacional) body += `<dt>Archivo nacional</dt><dd><a href="${esc(e.archivo_nacional.url)}" target="_blank" rel="noopener">${esc(e.archivo_nacional.titulo)}</a></dd>`;
  if (e.nota) body += `<dt>Nota</dt><dd>${esc(e.nota)}</dd>`;
  if (e.ocr) body += `<dt>Aviso OCR</dt><dd>Valores leídos por OCR del PDF escaneado. Solo se muestra un número si dos motores de OCR independientes (Tesseract y RapidOCR) leen exactamente lo mismo; si no coinciden, la celda queda vacía. Los textos de filas, encabezados y unidades son la lectura de Tesseract y pueden tener errores; las columnas no se identifican. Verificá contra el documento antes de usar un valor.</dd>`;
  else if (e.escaneado) body += `<dt>Aviso</dt><dd>El PDF es una imagen escaneada y el OCR no obtuvo valores coincidentes.</dd>`;
  body += "</dl>";
  if (e.tablas.length) body += e.tablas.map(tableHTML).join("");
  else body += `<p class="note">No hay valores extraídos automáticamente para esta distribuidora. ${d ? "Consultá el documento oficial." : ""}</p>`;
  if (e.intentos?.length) body += `<details><summary class="note">Registro técnico</summary><pre class="note">${esc(e.intentos.join("\n"))}</pre></details>`;
  return `<details class="card" id="d-${e.id}"><summary><h3>${esc(e.empresa)}</h3><span class="prov">${esc(e.provincia)}</span>
    <span class="badge b-${e.estado}">${ESTADO[e.estado]}</span>${e.ocr ? '<span class="badge b-old">OCR</span>' : ""}${via}${stale}
    <span class="prov">${e.vigencia ? "Vigencia: " + esc(e.vigencia) : ""}</span></summary><div class="body">${body}</div></details>`;
}

function matches(e, q) {
  if (!q) return true;
  const hay = [e.empresa, e.nombre, e.provincia, ...e.tablas.flatMap((t) => [t.titulo, ...t.filas.map((f) => f.concepto + " " + (f.grupo || ""))])].join(" ").toLowerCase();
  return q.toLowerCase().split(/\s+/).every((w) => hay.includes(w));
}

function renderList() {
  const prov = $("#f-prov").value, est = $("#f-estado").value, q = $("#f-q").value.trim();
  const items = DATA.distribuidoras.filter((e) => (!prov || e.provincia === prov) && (!est || e.estado === est) && matches(e, q));
  const cnt = (s) => DATA.distribuidoras.filter((e) => e.estado === s).length;
  $("#summary").textContent = `${items.length} de ${DATA.distribuidoras.length} distribuidoras · ${cnt("ok")} con valores extraídos · ${cnt("documento")} solo con documento oficial · ${cnt("sin_datos")} sin fuente`;
  $("#list").innerHTML = items.map(card).join("") || '<p class="note">Sin resultados.</p>';
  if (q) document.querySelectorAll("#list details.card").forEach((d) => (d.open = true));
}

function renderComp() {
  const cell = (c) => c ? `<td class="num">${fmt(c.valor)}</td><td>${esc(c.unidad || "")}</td>` : '<td class="num"><span class="empty">sin dato</span></td><td></td>';
  let h = "<thead><tr><th>Empresa</th><th>Provincia</th><th>Cargo fijo</th><th>Unidad</th><th>Cargo variable</th><th>Unidad</th><th>Escalón / criterio</th><th>Vigencia</th></tr></thead><tbody>";
  for (const e of DATA.distribuidoras) {
    const c = e.comparable || {};
    h += `<tr><td><a href="#d-${e.id}" onclick="openCard('${e.id}')">${esc(e.empresa)}</a></td><td>${esc(e.provincia)}</td>${cell(c.cargo_fijo)}${cell(c.cargo_variable)}<td>${esc(c.nota || "")}</td><td>${esc(e.vigencia || "")}</td></tr>`;
  }
  $("#comp").innerHTML = h + "</tbody>";
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
  ["#f-prov", "#f-estado", "#f-q"].forEach((s) => $(s).addEventListener("input", renderList));
  document.querySelectorAll("nav button").forEach((b) => b.addEventListener("click", () => show(b.dataset.view)));
  renderList(); renderComp(); renderHist();
}
init();
