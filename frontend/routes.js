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
// Destino real de cada módulo: [rota, id do painel funcional]. Módulos sem
// painel dedicado ainda recebem aviso honesto em vez de link circular.
const MODULE_TARGETS = {
  "meteorologia-e-clima": ["monitoramento", "aviation-panel"],
  "meio-ambiente": ["monitoramento", "municipal-map-panel"],
  "estacoes-e-sensores": ["monitoramento", "municipal-map-panel"],
  "qualidade-dos-dados": ["monitoramento", "quality-panel"],
  "ingestao": ["visao-geral", "run-list"],
  "series-temporais": ["planejamento", "reports-panel"],
  "alertas-oficiais": ["monitoramento", "municipal-map-panel"],
  "ocorrencias-e-incidentes": ["resposta", "operational-queues"],
  "protocolos": ["resposta", "operational-queues"],
  "recomendacoes": ["resposta", "operational-queues"],
  "defesa-civil": ["resposta", "operational-queues"],
  "relatorios": ["planejamento", "reports-panel"],
  "gabinete": ["planejamento", "reports-panel"],
  "operacoes": ["visao-geral", "overview-priorities"],
  "painel-executivo": ["planejamento", "reports-panel"],
  "indicadores": ["visao-geral", "operation-data"],
  "gabinete": ["visao-geral", "overview-cabinet"],
};
// Estado honesto dos módulos ainda sem painel dedicado.
const MODULE_ROADMAP = {
  "saude-ambiental": "Planejado — o módulo de saúde ambiental (backend) ainda é um esqueleto sem implementação. Entra na fase pós-piloto.",
  "assistencia-social": "Planejado — depende de convênio de dados com a Assistência Social; nenhuma implementação iniciada.",
  "planejamento-e-mitigacao": "Parcial — limiares de risco e relatórios já operam (ver Relatórios); a gestão de ações de mitigação é fase futura.",
  "catalogo-de-fontes": "Operações via API: POST /catalog/sources e perfis prontos (ANA, REDEMET, Open-Meteo) em /catalog/sources/profiles/*.",
  "comunicacao-e-campanhas": "Backend implementado (boletins e destinatários via /communications); tela dedicada em fase futura.",
  "administracao": "Operações via API de identidade (/auth) e auditoria (/audit); tela dedicada em fase futura.",
  "identidade-e-acesso": "Backend completo (papéis, sessões, Keycloak opcional); administração via API /auth.",
  "auditoria": "Trilha completa em /audit/events (toda ação relevante é registrada); consulta via API.",
  "organizacoes": "Multi-organização já suportado no backend; gestão via API.",
  "documentos": "Planejado — repositório documental entra na fase pós-piloto.",
  "apis": "Documentação interativa em /docs (fora de produção) e OpenAPI em /openapi.json.",
};
function moduleActionMarkup(name) {
  const slug = portalSlug(name);
  const target = MODULE_TARGETS[slug];
  if (target) return `<a class="module-route" href="#operacao/${target[0]}/${target[1]}">Abrir painel</a>`;
  const roadmap = MODULE_ROADMAP[slug] || "Interface dedicada em desenvolvimento — operações via API documentada.";
  return `<em class="module-soon">${roadmap}</em>`;
}
function renderOperationalRoute(active) {
  const route = operationalRoutes.find(([id]) => id === active) || operationalRoutes[0];
  activeOperationalRoute = route[0];
  byId("operational-tabs").innerHTML = operationalRoutes.map(([id, label]) => `<a href="#operacao/${id}" aria-current="${id === route[0] ? "page" : "false"}">${label}</a>`).join("");
  byId("operational-route-summary").innerHTML = `<p class="eyebrow">${escapeHtml(route[1])}</p><h3>${escapeHtml(route[2])}</h3><div class="module-pills">${route[3].map((name) => {
    const target = MODULE_TARGETS[portalSlug(name)];
    const href = target ? `#operacao/${target[0]}/${target[1]}` : `#operacao/${route[0]}/${portalSlug(name)}`;
    return `<a href="${href}">${escapeHtml(name)}</a>`;
  }).join("")}</div>`;
  document.querySelectorAll("[data-operational-group]").forEach((panel) => { panel.hidden = !operationalToken || panel.dataset.operationalGroup !== route[0]; });
  byId("module-workspace").innerHTML = route[3].map((name) => `<article id="${portalSlug(name)}"><h3>${escapeHtml(name)}</h3><p>${moduleDescription(name)}</p>${moduleActionMarkup(name)}</article>`).join("");
}
function syncPortalRoute() {
  const parts = location.hash.replace(/^#/, "").split("/");
  const institutional = parts[0] === "operacao";
  byId("public").hidden = institutional;
  byId("operacao").hidden = !institutional;
  document.querySelector("footer").hidden = !institutional;
  if (parts[0] === "operacao") {
    renderOperationalRoute(parts[1] || "visao-geral");
    if (parts[2]) requestAnimationFrame(() => {
      const alvo = document.getElementById(parts[2]);
      if (!alvo) return;
      alvo.scrollIntoView({block:"center"});
      alvo.classList.add("anchor-flash");
      setTimeout(() => alvo.classList.remove("anchor-flash"), 1800);
    });
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
