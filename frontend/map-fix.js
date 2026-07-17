function operationalLayerCounts() {
  const data = latestOperationalMap || {};
  return {
    territories: data.territories?.features?.length || 0,
    stations: data.stations?.features?.length || 0,
    alerts: data.alerts?.features?.length || 0,
    incidents: data.incidents?.features?.length || 0,
  };
}
function updateOperationalMapStatus() {
  const host = document.getElementById("municipal-map");
  if (!host || !latestOperationalMap) return;
  let notice = document.getElementById("municipal-map-empty");
  if (!notice) {
    notice = document.createElement("div");
    notice.id = "municipal-map-empty";
    notice.className = "map-empty-state";
    notice.setAttribute("role", "status");
    host.parentElement.insertBefore(notice, host);
  }
  const counts = operationalLayerCounts();
  const total = Object.values(counts).reduce((sum, value) => sum + value, 0);
  notice.hidden = total > 0;
  notice.innerHTML = total ? "" : "<strong>Nenhuma camada operacional cadastrada.</strong><span>O mapa-base está disponível. Territórios, estações, alertas e ocorrências aparecerão após cadastro com coordenadas válidas.</span>";
  const state = document.getElementById("municipal-map-state");
  if (state) {
    const updated = new Date(latestOperationalMap.generated_at_utc).toLocaleString("pt-BR");
    state.textContent = `Atualizado em ${updated}. Camadas: ${counts.territories} território(s), ${counts.stations} estação(ões), ${counts.alerts} alerta(s) e ${counts.incidents} ocorrência(s).`;
  }
}
function resizeOperationalMap() {
  if (!municipalMap || document.getElementById("municipal-map-panel")?.hidden) return;
  requestAnimationFrame(() => {
    municipalMap.invalidateSize({pan:false, animate:false});
    if (!Object.values(municipalLayers).length) municipalMap.setView([-19.9676, -44.1983], 11, {animate:false});
    updateOperationalMapStatus();
  });
  setTimeout(() => municipalMap?.invalidateSize({pan:false, animate:false}), 180);
}
const renderMunicipalMapBeforeLayoutFix = renderMunicipalMap;
renderMunicipalMap = function renderMunicipalMapWithLayoutFix() {
  renderMunicipalMapBeforeLayoutFix();
  updateOperationalMapStatus();
  resizeOperationalMap();
};
const renderOperationalRouteBeforeMapFix = renderOperationalRoute;
renderOperationalRoute = function renderOperationalRouteWithMapFix(active) {
  renderOperationalRouteBeforeMapFix(active);
  if (active === "monitoramento") resizeOperationalMap();
};
const municipalPanel = document.getElementById("municipal-map-panel");
if (municipalPanel) new MutationObserver(() => { if (!municipalPanel.hidden) resizeOperationalMap(); }).observe(municipalPanel, {attributes:true, attributeFilter:["hidden"]});
window.addEventListener("resize", resizeOperationalMap);
