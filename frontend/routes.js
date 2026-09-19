const publicRoutes = [
  ["situacao", "Situação agora"], ["alertas", "Alertas e orientações"],
  ["denuncia", "Denúncia e relato"], ["protecao", "Proteção e políticas"],
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
    "Operações":"Situação da coleta, filas pendentes e prontidão da plataforma para o turno.",
    "Painel executivo":"Leitura consolidada para o Gabinete: relatório climático do período, alertas por limiar e disponibilidade das estações.",
    "Indicadores":"Números do dia: fontes operacionais, alertas vigentes, itens em revisão e decisões com prazo.",
    "Gabinete":"Decisões com responsável, prazo e trilha de auditoria — registro e acompanhamento.",
    "Relatórios":"Previsão por horizonte, relatório do Comitê e disponibilidade de estações, com exportação em PDF e CSV.",
    "Meteorologia e clima":"Condições aeronáuticas regionais (METAR/SPECI), satélite e radar de contexto.",
    "Meio ambiente":"Mapa municipal com ocorrências, focos e camadas ambientais de referência.",
    "Estações e sensores":"Pontos de monitoramento no mapa com últimas medições, acumulados de chuva e tendência de nível.",
    "Ingestão":"Execuções recentes de coleta: aceitos, deduplicados e falhas por fonte.",
    "Qualidade dos dados":"Fila de dados suspeitos aguardando decisão do operador.",
    "Séries temporais":"Consulta por variável e período com exportação auditada.",
    "Alertas oficiais":"Alertas vigentes e sua cobertura territorial no mapa.",
    "Ocorrências e incidentes":"Triagem de ocorrências e denúncias recebidas do cidadão.",
    "Protocolos":"Ativações aguardando aprovação da autoridade competente.",
    "Recomendações":"Conteúdos publicados para orientação da população.",
    "Defesa Civil":"Filas de resposta: ocorrências, protocolos e recomendações em curso.",
    "Saúde ambiental":"Índice de calor, níveis de baixa umidade, risco de queimada e ações por grupo vulnerável.",
    "Planejamento e mitigação":"Ações estruturantes por risco, com responsável, prazo, custo e indicador de sucesso.",
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
  "saude-ambiental": ["planejamento", "health-panel"],
  "planejamento-e-mitigacao": ["planejamento", "mitigation-panel"],
  "relatorios": ["planejamento", "reports-panel"],
  "gabinete": ["planejamento", "reports-panel"],
  "operacoes": ["visao-geral", "overview-sources"],
  "painel-executivo": ["planejamento", "reports-panel"],
  "indicadores": ["visao-geral", "operation-data"],
  "gabinete": ["visao-geral", "overview-cabinet"],
};
// Estado honesto dos módulos ainda sem painel dedicado.
const MODULE_ROADMAP = {
  "assistencia-social": "Planejado — depende de convênio de dados com a Assistência Social; nenhuma implementação iniciada.",
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
    // Módulo sem painel não vira link: evita clique que não leva a nada.
    if (!target) return `<span class="module-pill-disabled" title="Interface dedicada ainda não disponível">${escapeHtml(name)}</span>`;
    return `<a href="#operacao/${target[0]}/${target[1]}">${escapeHtml(name)}</a>`;
  }).join("")}</div>`;
  document.querySelectorAll("[data-operational-group]").forEach((panel) => { panel.hidden = !operationalToken || panel.dataset.operationalGroup !== route[0]; });
  byId("module-workspace").innerHTML = route[3].map((name) => `<article id="${portalSlug(name)}"><h3>${escapeHtml(name)}</h3><p>${moduleDescription(name)}</p>${moduleActionMarkup(name)}</article>`).join("");
}
// ---------- Foco em painel: abre um bloco isolado, com Voltar/Início/ESC ----------
const PANEL_TITLES = {
  "overview-sources": "Operações — saúde das fontes",
  "overview-cabinet": "Gabinete — decisões",
  "overview-priorities": "Prioridades agora",
  "operation-data": "Indicadores do dia",
  "municipal-map-panel": "Mapa operacional",
  "aviation-panel": "Contexto aeronáutico regional",
  "quality-panel": "Qualidade dos dados",
  "operational-queues": "Filas de resposta",
  "reports-panel": "Relatórios e previsões",
  "health-panel": "Saúde ambiental",
  "mitigation-panel": "Planejamento e mitigação",
  "runs-details": "Execuções de ingestão",
  "run-list": "Execuções de ingestão",
};
let focusedPanelId = null;
function ensureFocusBar() {
  let barra = document.getElementById("panel-focus-bar");
  if (barra) return barra;
  barra = document.createElement("div");
  barra.id = "panel-focus-bar";
  barra.className = "panel-focus-bar";
  barra.hidden = true;
  barra.innerHTML = `
    <button type="button" data-focus-action="back">← Voltar</button>
    <button type="button" data-focus-action="home">⌂ Início</button>
    <strong id="panel-focus-title"></strong>
    <span class="focus-hint">ESC fecha</span>`;
  const operacao = document.getElementById("operacao");
  operacao?.insertBefore(barra, operacao.querySelector("#operational-tabs"));
  barra.querySelector('[data-focus-action="back"]').addEventListener("click", () => history.back());
  barra.querySelector('[data-focus-action="home"]').addEventListener("click", () => {
    location.hash = "#operacao/visao-geral";
  });
  return barra;
}
function applyPanelFocus(panelId) {
  const barra = ensureFocusBar();
  const alvo = panelId ? document.getElementById(panelId) : null;
  // Limpeza robusta: remove o estado de qualquer elemento, não só dos previstos.
  document.querySelectorAll(".panel-hidden-by-focus").forEach((bloco) => {
    bloco.classList.remove("panel-hidden-by-focus");
  });
  focusedPanelId = alvo ? panelId : null;
  if (!alvo) {
    barra.hidden = true;
    document.getElementById("operacao")?.classList.remove("focus-mode");
    // Rota apontava para um painel inexistente (módulo ainda sem tela):
    // normaliza a URL para a rota, evitando que o usuário fique preso.
    const partes = location.hash.replace(/^#/, "").split("/");
    if (panelId && partes.length > 2) {
      history.replaceState(null, "", `#${partes[0]}/${partes[1]}`);
    }
    return;
  }
  document.getElementById("operacao")?.classList.add("focus-mode");
  barra.hidden = false;
  document.getElementById("panel-focus-title").textContent = PANEL_TITLES[panelId] || "Painel";
  // Esconde os irmãos do painel em foco, mantendo o alvo visível.
  const grupo = alvo.closest("[data-operational-group]") || document.getElementById("operacao");
  Array.from(grupo.children).forEach((irmao) => {
    if (irmao !== alvo && irmao.id !== "panel-focus-bar") irmao.classList.add("panel-hidden-by-focus");
  });
  alvo.hidden = false;
  alvo.scrollIntoView({block: "start", behavior: "smooth"});
}
document.addEventListener("keydown", (evento) => {
  if (evento.key === "Escape" && focusedPanelId) {
    const parte = location.hash.split("/").slice(0, 2).join("/");
    location.hash = parte || "#operacao/visao-geral";
  }
});

function syncPortalRoute() {
  const parts = location.hash.replace(/^#/, "").split("/");
  const institutional = parts[0] === "operacao";
  byId("public").hidden = institutional;
  byId("operacao").hidden = !institutional;
  document.querySelector("footer").hidden = !institutional;
  if (parts[0] === "operacao") {
    renderOperationalRoute(parts[1] || "visao-geral");
    requestAnimationFrame(() => applyPanelFocus(parts[2] || null));
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
