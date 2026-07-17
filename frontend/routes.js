const publicRoutes = [
  ["situacao", "Situação agora"], ["alertas", "Alertas e orientações"],
  ["territorio", "Território"], ["protecao", "Proteção e políticas"],
  ["dados", "Dados e metodologia"],
];
const operationalRoutes = [
  ["visao-geral", "Visão geral", "Gabinete, situação municipal, indicadores e prioridades.", ["Operações", "Painel executivo", "Indicadores"]],
  ["monitoramento", "Monitoramento", "Dados, integrações e evidências que sustentam a operação.", ["Meteorologia e clima", "Meio ambiente", "Estações e sensores", "Catálogo de fontes", "Ingestão", "Qualidade dos dados", "Séries temporais"]],
  ["resposta", "Resposta", "Da detecção à ação coordenada, com aprovação e rastreabilidade.", ["Alertas oficiais", "Ocorrências e incidentes", "Protocolos", "Recomendações", "Comunicação e campanhas", "Defesa Civil"]],
  ["planejamento", "Planejamento", "Riscos transformados em ações, investimentos e avaliação pública.", ["Saúde ambiental", "Assistência social", "Planejamento e mitigação", "Relatórios", "Gabinete"]],
  ["governanca", "Governança", "Administração institucional, segurança, auditoria e transparência.", ["Identidade e acesso", "Organizações", "Administração", "Auditoria", "Documentos", "APIs"]],
];
let activeOperationalRoute = "visao-geral";
function portalSlug(value) { return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""); }
function moduleDescription(name) {
  return ({
    "Saúde ambiental":"Indicadores agregados, vigilância de impactos e proteção de grupos vulneráveis.",
    "Assistência social":"Vulnerabilidade territorial e coordenação de busca ativa autorizada.",
    "Meio ambiente":"Qualidade do ar, fumaça, queimadas, fiscalização e evidências ambientais.",
    "Comunicação e campanhas":"Mensagens aprovadas, públicos, canais e acompanhamento de alcance.",
    "APIs":"Integrações públicas e institucionais documentadas e controladas por perfil.",
  })[name] || "Rota institucional disponível conforme as atribuições e permissões do perfil autenticado.";
}
function renderPublicTabs(active) {
  const tabs = byId("public-tabs");
  tabs.innerHTML = publicRoutes.map(([id, label]) => `<a href="#public/${id}" aria-current="${id === active ? "page" : "false"}">${label}</a>`).join("");
  document.querySelectorAll("[data-public-route]").forEach((panel) => { panel.hidden = panel.dataset.publicRoute !== active; });
  if (active === "situacao" && typeof resizeAviationMap === "function") resizeAviationMap();
}
function renderOperationalRoute(active) {
  const route = operationalRoutes.find(([id]) => id === active) || operationalRoutes[0];
  activeOperationalRoute = route[0];
  byId("operational-tabs").innerHTML = operationalRoutes.map(([id, label]) => `<a href="#operacao/${id}" aria-current="${id === route[0] ? "page" : "false"}">${label}</a>`).join("");
  byId("operational-route-summary").innerHTML = `<p class="eyebrow">${escapeHtml(route[1])}</p><h3>${escapeHtml(route[2])}</h3><div class="module-pills">${route[3].map((name) => `<a href="#operacao/${route[0]}/${portalSlug(name)}">${escapeHtml(name)}</a>`).join("")}</div>`;
  document.querySelectorAll("[data-operational-group]").forEach((panel) => { panel.hidden = !operationalToken || panel.dataset.operationalGroup !== route[0]; });
  byId("module-workspace").innerHTML = route[3].map((name) => `<article id="${portalSlug(name)}"><h3>${escapeHtml(name)}</h3><p>${moduleDescription(name)}</p><a class="module-route" href="#operacao/${route[0]}/${portalSlug(name)}">Acessar área</a></article>`).join("");
}
function syncPortalRoute() {
  const parts = location.hash.replace(/^#/, "").split("/");
  const institutional = parts[0] === "operacao";
  byId("public").hidden = institutional;
  byId("operacao").hidden = !institutional;
  document.querySelector("footer").hidden = !institutional;
  if (parts[0] === "operacao") {
    renderOperationalRoute(parts[1] || "visao-geral");
    if (parts[2]) requestAnimationFrame(() => document.getElementById(parts[2])?.scrollIntoView({block:"center"}));
  } else {
    const route = publicRoutes.some(([id]) => id === parts[1]) ? parts[1] : "situacao";
    renderPublicTabs(route);
  }
}
window.addEventListener("hashchange", syncPortalRoute);
window.addEventListener("load", () => { syncPortalRoute(); loadPublic(); });

const loadOperationWithRoutes = loadOperation;
loadOperation = async function loadOperationAndApplyRoute(token) {
  await loadOperationWithRoutes(token);
  renderOperationalRoute(activeOperationalRoute);
};
