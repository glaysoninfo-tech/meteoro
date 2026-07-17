let officialMapLayers = {};
let latestOfficialLayers = null;

function installOfficialLayerControls() {
  const controls = document.querySelector("#municipal-map-panel .map-controls");
  if (!controls || document.getElementById("layer-watercourses")) return;
  controls.insertAdjacentHTML("beforeend", '<label><input id="layer-watercourses" type="checkbox" checked> Cursos d\'água (ANA)</label><label><input id="layer-rain-gauges" type="checkbox" checked> Pluviômetros (CEMADEN)</label><label><input id="layer-river-gauges" type="checkbox" checked> Réguas fluviométricas (ANA)</label><label><input id="layer-fire-hotspots" type="checkbox" checked> Queimadas 24h (INPE)</label>');
  ["layer-watercourses", "layer-rain-gauges", "layer-river-gauges", "layer-fire-hotspots"].forEach((id) => document.getElementById(id).addEventListener("change", renderOfficialLayers));
  const state = document.createElement("p");
  state.id = "official-layer-state";
  state.className = "official-layer-state";
  controls.after(state);
}

function clearOfficialLayers() {
  Object.values(officialMapLayers).forEach((layer) => municipalMap?.removeLayer(layer));
  officialMapLayers = {};
}

function renderOfficialLayers() {
  if (!municipalMap || !latestOfficialLayers) return;
  clearOfficialLayers();
  const add = (key, enabled, data, options, popup) => {
    if (!enabled || !data?.features?.length) return;
    officialMapLayers[key] = L.geoJSON(data, {...options, onEachFeature:(feature, layer) => layer.bindPopup(popup(feature.properties || {}))}).addTo(municipalMap);
  };
  add("watercourses", document.getElementById("layer-watercourses").checked, latestOfficialLayers.hydrography,
    {style:{color:"#168aad", weight:2, opacity:.82}},
    (p) => `<strong>${escapeHtml(p.NORIOCOMP || p.NOGENERICO || "Curso d'água")}</strong><br>Fonte: ANA / SNIRH`);
  add("rain_gauges", document.getElementById("layer-rain-gauges").checked, latestOfficialLayers.rain_gauges,
    {pointToLayer:(f, ll) => L.marker(ll,{icon:mapSymbolIcon("☂", "rain", "Estação pluviométrica")})},
    (p) => `<strong>${escapeHtml(p.nomeestacao || "Estação pluviométrica")}</strong><br>${escapeHtml(p.cidade || "Região de Betim")}<br>Acumulado informado: ${escapeHtml(p.acumulado ?? "não informado")}<br>Fonte: CEMADEN`);
  add("river_gauges", document.getElementById("layer-river-gauges").checked, latestOfficialLayers.river_gauges,
    {pointToLayer:(f, ll) => L.marker(ll,{icon:mapSymbolIcon("≋", "river", "Estação fluviométrica")})},
    (p) => `<strong>${escapeHtml(p.Nome || "Estação fluviométrica")}</strong><br>Rio: ${escapeHtml(p.Rio || "não informado")}<br>${escapeHtml(p.Municipio || "")}<br>Fonte: ANA / SNIRH`);
  add("fire_hotspots", document.getElementById("layer-fire-hotspots").checked, latestOfficialLayers.fire_hotspots,
    {pointToLayer:(f, ll) => L.marker(ll,{icon:mapSymbolIcon("▲", "fire", "Foco de calor")})},
    (p) => `<strong>Foco de calor</strong><br>${escapeHtml(p.data_hora_gmt || p.data || "Últimas 24 horas")}<br>Fonte: INPE`);
  const labels = {hydrography:"ANA cursos d'água", rain_gauges:"CEMADEN", river_gauges:"ANA réguas", fire_hotspots:"INPE"};
  document.getElementById("official-layer-state").innerHTML = Object.entries(latestOfficialLayers.status).map(([key, value]) => `<span class="${value.available ? "source-ok" : "source-off"}" title="${escapeHtml(value.detail || value.source || "")}">${labels[key] || key}: ${value.available ? `${value.count} feição(ões)` : "indisponível"}</span>`).join("");
  updateOperationalMapStatus();
}

async function loadOfficialLayers(token) {
  installOfficialLayerControls();
  try {
    latestOfficialLayers = await request("/geospatial/official-layers", {headers:{Authorization:`Bearer ${token}`}});
    renderOfficialLayers();
  } catch (error) {
    const state = document.getElementById("official-layer-state");
    if (state) state.textContent = `Camadas públicas indisponíveis: ${error.message}`;
  }
}

const loadOperationBeforeOfficialLayers = loadOperation;
loadOperation = async function loadOperationWithOfficialLayers(token) {
  await loadOperationBeforeOfficialLayers(token);
  await loadOfficialLayers(token);
};
installOfficialLayerControls();
