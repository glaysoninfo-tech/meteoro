const api = "/api/v1";
const byId = (id) => document.getElementById(id);
const setState = (id, text) => (byId(id).textContent = text);
let operationalToken = null;
let aviationMap = null;
let aviationLayer = null;
let satelliteLayer = null;
let radarLayer = null;
let lightningLayer = null;
let latestMapLayers = null;
let municipalMap = null;
let municipalLayers = {};
let latestOperationalMap = null;

async function request(path, options = {}) {
  const response = await fetch(`${api}${path}`, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Não foi possível concluir a solicitação.");
  return data;
}

async function loadPublic() {
  setState("public-state", "Buscando informações oficiais…");
  try {
    const alerts = await request("/public/alerts");
    byId("public-alerts").innerHTML = alerts.length
      ? alerts.map((a) => `<article><span class="severity">${a.severity}</span><h3>${a.title}</h3><p>${a.message}</p><small>Válido até ${new Date(a.valid_to_utc).toLocaleString("pt-BR")}</small></article>`).join("")
      : "<p class='muted'>Não há alertas oficiais ativos.</p>";
    setState("public-state", "Atualizado agora.");
  } catch (error) { setState("public-state", error.message); }
}

async function loadOperation(token) {
  const auth = { Authorization: `Bearer ${token}` };
  const [runs, connectors, worker, situation, mapData, qualityIssues, incidents, activations] = await Promise.all([
    request("/ingestion/runs/latest", { headers: auth }),
    request("/ingestion/connectors/health", { headers: auth }),
    request("/ingestion/worker/status", { headers: auth }),
    request("/operations/situation", { headers: auth }),
    request("/operations/map", { headers: auth }),
    request("/data-quality/issues", { headers: auth }),
    request("/incidents/reports?triage_status=pending", { headers: auth }),
    request("/alerts/protocol-activations?status=pending_approval", { headers: auth })
  ]);
  byId("runs").textContent = situation.pending_quality_issues;
  byId("sources").textContent = situation.stations_total;
  byId("worker").textContent = situation.pending_protocol_approvals;
  byId("runs").parentElement.querySelector("span").textContent = "dados aguardando revisão";
  byId("sources").parentElement.querySelector("span").textContent = "estações cadastradas";
  byId("worker").parentElement.querySelector("span").textContent = "protocolos pendentes";
  byId("run-list").innerHTML = runs.slice(0, 8).map((r) => `<article><span>${r.status} · ${r.trigger_type}</span><small>${r.records_accepted} aceitos · ${r.records_deduplicated} deduplicados</small></article>`).join("");
  byId("operation-data").hidden = false; byId("run-list").hidden = false;
  // Painéis precisam estar visíveis ANTES de renderizar os mapas: o Leaflet
  // mede o contêiner na inicialização e um contêiner oculto tem tamanho zero.
  byId("municipal-map-panel").hidden = false;
  byId("operational-queues").hidden = false;
  byId("reports-panel").hidden = false;
  byId("aviation-panel").hidden = false;
  latestOperationalMap = mapData;
  renderMunicipalMap();
  renderQueues(qualityIssues, incidents, activations);
  operationalToken = token;
  await loadAviation(token);
  await loadMapLayers(token);
  const attention = situation.platform_state === "attention" ? " Atenção operacional necessária." : "";
  setState("operation-state", (worker.queue_available ? "Painel atualizado." : "API disponível; fila Redis indisponível.") + attention);
}

function initMunicipalMap() {
  if (!municipalMap && window.L) {
    municipalMap = L.map("municipal-map", {scrollWheelZoom:false}).setView([-19.9676, -44.1983], 11);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom:18,attribution:"© OpenStreetMap contributors"}).addTo(municipalMap);
  }
  return municipalMap;
}
function renderMunicipalMap() {
  const map = initMunicipalMap();
  if (!map || !latestOperationalMap) return;
  Object.values(municipalLayers).forEach((layer) => map.removeLayer(layer));
  municipalLayers = {};
  const add = (name, enabled, data, options, popup) => {
    if (!enabled || !data?.features?.length) return;
    municipalLayers[name] = L.geoJSON(data, {style:options?.style, pointToLayer:options?.pointToLayer, onEachFeature:(feature, layer) => layer.bindPopup(popup(feature.properties || {}))}).addTo(map);
  };
  add("territories", byId("layer-territories").checked, latestOperationalMap.territories, {style:{color:"#0f766e",weight:1,fillOpacity:.06}}, (p) => `<strong>${escapeHtml(p.name)}</strong><br>${escapeHtml(p.type)}`);
  add("alerts", byId("layer-alerts").checked, latestOperationalMap.alerts, {style:(f) => ({color:{low:"#eab308",medium:"#f97316",high:"#dc2626",critical:"#7f1d1d"}[f.properties.severity] || "#dc2626",weight:3,fillOpacity:.12})}, (p) => `<strong>Alerta ${escapeHtml(p.code)}</strong><br>${escapeHtml(p.title)}<br>Vigente até ${new Date(p.valid_to_utc).toLocaleString("pt-BR")}`);
  add("stations", byId("layer-stations").checked, latestOperationalMap.stations, {pointToLayer:(f, latlng) => L.circleMarker(latlng,{radius:8,color:"#fff",weight:2,fillColor:f.properties.status === "active" ? "#16803c" : "#b7791f",fillOpacity:1})}, (p) => `<strong>${escapeHtml(p.code)} · ${escapeHtml(p.name)}</strong><br>${escapeHtml(p.type)} · ${escapeHtml(p.status)}`);
  add("incidents", byId("layer-incidents").checked, latestOperationalMap.incidents, {pointToLayer:(f, latlng) => L.circleMarker(latlng,{radius:7,color:"#7c2d12",weight:2,fillColor:"#fb923c",fillOpacity:1})}, (p) => `<strong>${escapeHtml(p.category)}</strong><br>${escapeHtml(p.severity)} · ${escapeHtml(p.triage_status)}<br>${escapeHtml(p.location_code || "local informado")}`);
  // Recalcula o tamanho após o layout assentar; sem isso o mapa fica
  // espremido no canto quando o contêiner acabou de sair de "hidden".
  requestAnimationFrame(() => map.invalidateSize({pan:false, animate:false}));
  setTimeout(() => map.invalidateSize({pan:false, animate:false}), 200);
  const groups = Object.values(municipalLayers);
  if (groups.length) { const combined = L.featureGroup(groups); const bounds = combined.getBounds(); if (bounds.isValid()) setTimeout(() => map.fitBounds(bounds,{padding:[25,25],maxZoom:13}), 220); }
  setState("municipal-map-state", `Atualizado em ${new Date(latestOperationalMap.generated_at_utc).toLocaleString("pt-BR")}. ${latestOperationalMap.notices[0]}`);
}
function renderQueues(issues, incidents, activations) {
  byId("quality-list").innerHTML = issues.length ? issues.slice(0,6).map((i) => `<p><strong>${escapeHtml(i.flag_code)}</strong><br><small>${escapeHtml(i.variable_code)} · ${escapeHtml(i.severity)}</small></p>`).join("") : "<p class='muted'>Nenhum item pendente.</p>";
  byId("incident-list").innerHTML = incidents.length ? incidents.slice(0,6).map((i) => `<p><strong>${escapeHtml(i.category_code)}</strong><br><small>${escapeHtml(i.location_code || "sem bairro")} · ${escapeHtml(i.severity)}</small></p>`).join("") : "<p class='muted'>Nenhuma ocorrência pendente.</p>";
  byId("protocol-list").innerHTML = activations.length ? activations.slice(0,6).map((i) => `<p><strong>${escapeHtml(i.severity)}</strong><br><small>Ativado em ${new Date(i.started_at_utc).toLocaleString("pt-BR")}</small></p>`).join("") : "<p class='muted'>Nenhuma aprovação pendente.</p>";
}

function reportPeriodQuery() {
  const hours = Math.min(720, Math.max(1, Number(byId("report-hours").value) || 24));
  const end = new Date();
  const start = new Date(end.getTime() - hours * 60 * 60 * 1000);
  return `period_start_utc=${encodeURIComponent(start.toISOString())}&period_end_utc=${encodeURIComponent(end.toISOString())}`;
}
async function generateReport() {
  if (!operationalToken) return;
  const auth = {Authorization:`Bearer ${operationalToken}`};
  const kind = byId("report-kind").value;
  setState("report-state", "Gerando consulta…");
  try {
    let result;
    if (kind === "forecast") {
      const horizon = Math.min(168, Math.max(1, Number(byId("report-hours").value) || 24));
      const step = Math.min(24, Math.max(1, Number(byId("report-step").value) || 6));
      result = await request(`/meteorology/forecast?horizon_hours=${horizon}&step_hours=${Math.min(step,horizon)}`, {headers:auth});
      byId("report-result").innerHTML = `<article><h4>Previsão para ${result.horizon_hours}h</h4><p>${escapeHtml(result.summary)}</p><code>${escapeHtml(JSON.stringify(result.series, null, 2))}</code></article>`;
    } else if (kind === "committee") {
      result = await request(`/planning/committee/climate-report?${reportPeriodQuery()}`, {headers:auth});
      byId("report-result").innerHTML = `<article><h4>Relatório climático do Gabinete</h4><p>${escapeHtml(result.executive_summary)}</p><p>Observações consideradas: <strong>${result.observations_considered}</strong> · alertas por limiar: <strong>${result.alerts.length}</strong></p></article>`;
    } else {
      result = await request(`/planning/stations/availability?${reportPeriodQuery()}`, {headers:auth});
      byId("report-result").innerHTML = `<article><h4>Disponibilidade de estações</h4><p>${escapeHtml(result.summary)}</p>${result.stations.map((item) => `<p><strong>${escapeHtml(item.station_code)}</strong> · ${escapeHtml(item.health_status)} · completude ${item.completeness_percent ?? "n/d"}%</p>`).join("") || "<p>Nenhuma estação cadastrada.</p>"}</article>`;
    }
    setState("report-state", "Consulta atualizada e auditada.");
  } catch (error) { setState("report-state", error.message); }
}
async function downloadReport(format) {
  if (!operationalToken) return;
  const kind = byId("report-kind").value;
  const base = kind === "forecast" ? null : kind === "committee" ? "/planning/committee/climate-report" : "/planning/stations/availability";
  if (!base) { setState("report-state", "A previsão é retornada como JSON; use “Gerar consulta”."); return; }
  setState("report-state", `Preparando ${format.toUpperCase()}…`);
  try {
    const response = await fetch(`${api}${base}.${format}?${reportPeriodQuery()}`, {headers:{Authorization:`Bearer ${operationalToken}`}});
    if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(error.detail || "Não foi possível gerar o arquivo."); }
    const objectUrl = URL.createObjectURL(await response.blob());
    const link = document.createElement("a"); link.href = objectUrl; link.download = `meteoro-${kind}.${format}`; link.click(); URL.revokeObjectURL(objectUrl);
    setState("report-state", `${format.toUpperCase()} gerado.`);
  } catch (error) { setState("report-state", error.message); }
}

function categoryMeta(category) {
  return {g:{label:"VFR / verde",color:"#16803c"},y:{label:"Atenção / amarelo",color:"#b7791f"},r:{label:"IFR / vermelho",color:"#be2d2d"}}[category] || {label:"Sem dado recente",color:"#64748b"};
}
function escapeHtml(value) { return String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char])); }

const moduleCatalog = [
  ["01","Identidade e acesso","Login, papéis, sessões e auditoria","Homologar identidade municipal e MFA."],
  ["02","Catálogo de fontes","Instituições, produtos, endpoint, licença e saúde","Homologar endpoints, licença e responsável."],
  ["03","Ingestão","Coleta, upload, fila, idempotência e reprocessamento","Validar conectores com as fontes oficiais."],
  ["04","Armazenamento bruto","Payload, hash, origem, parser e retenção","Aprovar política de retenção e backup."],
  ["05","Estações e sensores","Cadastro, mapa, variáveis e manutenção","Confirmar campo, calibração e transmissão."],
  ["06","Séries temporais","Filtros, lacunas, qualidade e exportação","Homologar séries reais e regra de publicação."],
  ["07","Qualidade dos dados","Regras, fila, decisão e justificativa","Calibrar regras com evidências de operação."],
  ["08","Alertas oficiais","Vigência, severidade, cobertura e histórico","Homologar emissor e fluxo de publicação."],
  ["09","Ocorrências e incidentes","Registro, evidência, triagem e incidente","Validar formulário com os órgãos de campo."],
  ["10","Protocolos","Versões, gatilhos, aprovação e ativação","Aprovar protocolos e competências."],
  ["11","Recomendações","Conteúdo, revisão, aprovação e publicação","Homologar conteúdo e aprovadores."],
  ["12","Portal operacional","Situação, mapas, filas e Gabinete","Homologar login municipal e base operacional."],
  ["13","Site público","Situação, metodologia e dados abertos","Homologar organização pública e licença."],
  ["14","Relatórios","Boletim, CSV, PDF e OpenAPI","Validar modelo institucional de boletim."],
  ["15","Administração","Usuários, fontes, regras e auditoria","Homologar responsáveis administrativos."],
];
let activeModuleId = null;
function renderModuleCatalog() {
  const catalog = byId("module-catalog");
  if (!catalog) return;
  catalog.innerHTML = moduleCatalog.map(([id, name]) => `<button class="module-entry" type="button" data-module-id="${id}" aria-pressed="${id === activeModuleId}"><span>MÓDULO ${id}</span><strong>${escapeHtml(name)}</strong><em>interface completa</em></button>`).join("");
  catalog.querySelectorAll("[data-module-id]").forEach((button) => button.addEventListener("click", () => openModuleWorkspace(button.dataset.moduleId)));
}
function openModuleWorkspace(id) {
  const item = moduleCatalog.find((module) => module[0] === id);
  if (!item) return;
  activeModuleId = id;
  const [moduleId, name, scope, pending] = item;
  const workspace = byId("module-workspace");
  workspace.hidden = false;
  workspace.innerHTML = `<p class="eyebrow">MÓDULO ${moduleId}</p><h3>${escapeHtml(name)}</h3><p>${escapeHtml(scope)}</p><div class="module-actions"><button type="button" data-module-action="open">Abrir fluxo</button><button type="button" data-module-action="filter">Aplicar filtro</button><button type="button" data-module-action="audit">Consultar auditoria</button></div><p class="module-message" id="module-message">Escolha uma ação para navegar pela interface de ${escapeHtml(name)}.</p><ul><li>Campos, filtros e estados apresentados na interface.</li><li>Operações registradas com usuário, data e trilha de auditoria.</li><li>Dados restritos continuam protegidos por perfil.</li></ul><p class="module-note"><strong>Homologação ou evidência de campo pendente:</strong> ${escapeHtml(pending)}</p>`;
  workspace.querySelectorAll("[data-module-action]").forEach((button) => button.addEventListener("click", () => {
    const action = {open:"Fluxo aberto",filter:"Filtro aplicado",audit:"Auditoria consultada"}[button.dataset.moduleAction];
    byId("module-message").textContent = `${action} nesta prévia. Em produção, o resultado usa os dados autenticados do módulo.`;
  }));
  renderModuleCatalog();
}
function initAviationMap() {
  if (!aviationMap && window.L) {
    aviationMap = L.map("aviation-map", {scrollWheelZoom:false}).setView([-20.0, -44.35], 8);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom:18,attribution:"© OpenStreetMap contributors"}).addTo(aviationMap);
  }
  if (aviationMap) {
    requestAnimationFrame(() => aviationMap.invalidateSize({pan:false, animate:false}));
    setTimeout(() => aviationMap.invalidateSize({pan:false, animate:false}), 200);
  }
  return aviationMap;
}
function refreshImageLayers() {
  if (!aviationMap || !latestMapLayers) return;
  for (const layer of [satelliteLayer, radarLayer, lightningLayer]) if (layer) aviationMap.removeLayer(layer);
  satelliteLayer = radarLayer = lightningLayer = null;
  const addImage = (item, enabled, opacity) => {
    if (!item?.image_url || !item?.bounds || !enabled) return null;
    return L.imageOverlay(item.image_url, item.bounds, {opacity, crossOrigin:true}).addTo(aviationMap);
  };
  satelliteLayer = addImage(latestMapLayers.satellite, byId("layer-satellite").checked, .48);
  radarLayer = addImage(latestMapLayers.radar, byId("layer-radar").checked, .62);
  if (Array.isArray(latestMapLayers.lightning_events) && latestMapLayers.lightning_events.length && window.L?.heatLayer) {
    lightningLayer = L.heatLayer(latestMapLayers.lightning_events.map((item) => [item.latitude, item.longitude, Math.min(1, item.intensity)]), {radius:28, blur:20, maxZoom:10, gradient:{.2:"#fef08a",.55:"#f97316",.85:"#dc2626"}}).addTo(aviationMap);
  }
}
async function loadMapLayers(token = operationalToken) {
  if (!token) return;
  try {
    latestMapLayers = await request("/meteorology/map/layers", {headers:{Authorization:`Bearer ${token}`}});
    refreshImageLayers();
    byId("lightning-counter").textContent = latestMapLayers.lightning_available ? `Raios na última hora: ${latestMapLayers.lightning_count_last_60m}` : "Raios: feed oficial não configurado";
  } catch (error) { byId("lightning-counter").textContent = "Raios: indisponível"; }
}
async function loadAviation(token = operationalToken) {
  if (!token) return;
  setState("aviation-state", "Consultando o último dado preservado da REDEMET…");
  try {
    const result = await request("/meteorology/aviation/conditions", {headers:{Authorization:`Bearer ${token}`}});
    const map = initAviationMap();
    if (map && aviationLayer) aviationLayer.remove();
    if (map) aviationLayer = L.layerGroup().addTo(map);
    const bounds = [];
    byId("aviation-cards").innerHTML = result.conditions.length ? result.conditions.map((item) => {
      const meta = categoryMeta(item.flight_category);
      if (map) { L.circleMarker([item.latitude,item.longitude], {radius:13,color:"#fff",weight:2,fillColor:meta.color,fillOpacity:.95}).bindPopup(`<strong>${escapeHtml(item.icao)} — ${escapeHtml(item.airport_name)}</strong><br>${escapeHtml(meta.label)}<br><small>${escapeHtml(item.source_note)}</small>`).addTo(aviationLayer); bounds.push([item.latitude,item.longitude]); }
      const metar = item.metar ? `<code>${escapeHtml(item.metar)}</code>` : "<p class='muted'>METAR/SPECI ainda não disponível.</p>";
      return `<article class="aviation-card"><span class="flight-category" style="--category:${meta.color}">${escapeHtml(meta.label)}</span><h4>${escapeHtml(item.icao)} · ${escapeHtml(item.airport_name)}</h4><p>${escapeHtml(item.source_note)}</p>${metar}<small>METAR válido: ${item.metar_valid_at_utc ? new Date(item.metar_valid_at_utc).toLocaleString("pt-BR") : "indisponível"}</small></article>`;
    }).join("") : "<p class='muted'>Os conectores REDEMET ainda não foram cadastrados ou não possuem coleta concluída.</p>";
    if (map && bounds.length) map.fitBounds(bounds, {padding:[30,30],maxZoom:9});
    setState("aviation-state", result.disclaimer);
  } catch (error) { setState("aviation-state", error.message); }
}

byId("load-public").addEventListener("click", loadPublic);
byId("refresh-aviation").addEventListener("click", async () => { await loadAviation(); await loadMapLayers(); });
byId("refresh-operation").addEventListener("click", () => loadOperation(operationalToken));
byId("reports-form").addEventListener("submit", (event) => { event.preventDefault(); generateReport(); });
byId("download-pdf").addEventListener("click", () => downloadReport("pdf"));
byId("download-csv").addEventListener("click", () => downloadReport("csv"));
byId("layer-satellite").addEventListener("change", refreshImageLayers);
byId("layer-radar").addEventListener("change", refreshImageLayers);
["layer-territories","layer-stations","layer-alerts","layer-incidents"].forEach((id) => byId(id).addEventListener("change", renderMunicipalMap));
// Sessão do operador: access token curto em memória + refresh rotativo em
// cookie httpOnly (o token nunca fica acessível a scripts/sessionStorage).
let refreshTimer = null;
function scheduleTokenRefresh(expiresAtUtc) {
  if (refreshTimer) clearTimeout(refreshTimer);
  const millisecondsToRenewal = new Date(expiresAtUtc).getTime() - Date.now() - 60000;
  refreshTimer = setTimeout(refreshSession, Math.max(15000, millisecondsToRenewal));
}
async function refreshSession() {
  try {
    const token = await request("/auth/refresh", {method:"POST"});
    operationalToken = token.access_token;
    scheduleTokenRefresh(token.expires_at_utc);
    return token.access_token;
  } catch (error) { return null; }
}
async function logoutSession() {
  if (refreshTimer) clearTimeout(refreshTimer);
  try { await request("/auth/logout", {method:"POST"}); } catch (error) { /* idempotente */ }
  operationalToken = null;
  location.reload();
}
byId("login-form").addEventListener("submit", async (event) => {
  event.preventDefault(); setState("operation-state", "Autenticando…");
  try {
    const token = await request("/auth/token", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:byId("email").value,password:byId("password").value})});
    scheduleTokenRefresh(token.expires_at_utc);
    byId("login-form").hidden = true; byId("logout-button").hidden = false;
    await loadOperation(token.access_token);
  } catch (error) { setState("operation-state", error.message); }
});
byId("logout-button").addEventListener("click", logoutSession);
// Reload não derruba mais o operador: tenta renovar a sessão pelo cookie.
refreshSession().then((token) => {
  if (token) {
    byId("login-form").hidden = true; byId("logout-button").hidden = false;
    loadOperation(token).catch(() => {});
  }
});
renderModuleCatalog();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/portal/service-worker.js");
