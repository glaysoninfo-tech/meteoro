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

function setApiBanner(message) {
  const banner = byId("api-banner");
  if (!banner) return;
  banner.hidden = !message;
  banner.textContent = message || "";
}
async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${api}${path}`, options);
  } catch (networkError) {
    setApiBanner("API indisponível no momento — verifique o servidor. Dados exibidos podem estar desatualizados.");
    throw new Error("Sem conexão com a API.");
  }
  const cachedAt = response.headers.get("X-Meteoro-Cached-At");
  if (cachedAt) {
    setApiBanner(`Sem conexão com a API — exibindo dados guardados de ${new Date(cachedAt).toLocaleString("pt-BR")}.`);
  } else {
    setApiBanner(null);
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Não foi possível concluir a solicitação.");
  return data;
}

async function loadPublic() {
  setState("public-state", "Buscando informações oficiais…");
  try {
    const alerts = await request("/public/alerts");
    byId("public-alerts").innerHTML = alerts.length
      ? alerts.map((a) => `<article><span class="severity">${a.severity}</span><h3>${a.title}</h3><p>${a.message}</p><small>Válido até ${dataHoraLocal(a.valid_to_utc)}</small></article>`).join("")
      : "<p class='muted'>Não há alertas oficiais ativos.</p>";
    setState("public-state", "Atualizado agora.");
  } catch (error) { setState("public-state", error.message); }
}

async function loadOperation(token) {
  const auth = { Authorization: `Bearer ${token}` };
  const [runs, connectors, worker, situation, mapData, qualityIssues, incidents, activations, decisions, publicAlerts] = await Promise.all([
    request("/ingestion/runs/latest", { headers: auth }),
    request("/ingestion/connectors/health", { headers: auth }),
    request("/ingestion/worker/status", { headers: auth }),
    request("/operations/situation", { headers: auth }),
    request("/operations/map", { headers: auth }),
    request("/data-quality/issues", { headers: auth }),
    request("/incidents/reports?triage_status=pending", { headers: auth }),
    request("/alerts/protocol-activations?status=pending_approval", { headers: auth }),
    request("/planning/cabinet/decisions?status=open", { headers: auth }).catch(() => []),
    request("/public/alerts").catch(() => [])
  ]);
  renderOverview({situation, connectors, qualityIssues, incidents, activations, decisions, publicAlerts, worker});
  byId("run-list").innerHTML = runs.slice(0, 8).map((r) => `<article><span>${r.status} · ${r.trigger_type}</span><small>${r.records_accepted} aceitos · ${r.records_deduplicated} deduplicados</small></article>`).join("");
  byId("operation-data").hidden = false; byId("run-list").hidden = false;
  // Painéis precisam estar visíveis ANTES de renderizar os mapas: o Leaflet
  // mede o contêiner na inicialização e um contêiner oculto tem tamanho zero.
  byId("municipal-map-panel").hidden = false;
  byId("operational-queues").hidden = false;
  byId("reports-panel").hidden = false;
  byId("aviation-panel").hidden = false;
  byId("module-workspace").hidden = false;
  latestOperationalMap = mapData;
  renderMunicipalMap();
  renderQueues(qualityIssues, incidents, activations);
  operationalToken = token;
  await loadOperationalMonitoring(token);
  await loadAviation(token);
  await loadMapLayers(token);
  const attention = situation.platform_state === "attention" ? " Atenção operacional necessária." : "";
  setState("operation-state", (worker.queue_available ? "Painel atualizado." : "API disponível; fila Redis indisponível.") + attention);
}

// ---------- Visão geral executiva ----------
const PLATFORM_STATE_LABELS = {normal:"Normal", attention:"Atenção", critical:"Crítico"};
function renderOverview({situation, connectors, qualityIssues, incidents, activations, decisions, publicAlerts, worker}) {
  const stateLabel = PLATFORM_STATE_LABELS[situation.platform_state] || situation.platform_state || "–";
  byId("ov-state").textContent = stateLabel;
  byId("ov-state").style.color = situation.platform_state === "normal" ? "#16803c" : "#b45309";
  byId("ov-alerts").textContent = (publicAlerts || []).length;
  const operational = (connectors || []).filter((c) => ["operational", "healthy"].includes(c.state)).length;
  byId("ov-sources").textContent = `${operational}/${(connectors || []).length}`;
  const abertas = (decisions || []).length;
  byId("ov-decisions").textContent = abertas;

  // Prioridades: tudo que exige ação humana, com link direto para a fila.
  const prioridades = [];
  const add = (count, texto, href, criticidade) => { if (count > 0) prioridades.push({count, texto, href, criticidade}); };
  add(situation.pending_quality_issues, "dado(s) suspeito(s) aguardando revisão", "#operacao/monitoramento/quality-panel", "media");
  add((incidents || []).length, "ocorrência(s) aguardando triagem", "#operacao/resposta/operational-queues", "alta");
  add((activations || []).length, "protocolo(s) aguardando aprovação", "#operacao/resposta/operational-queues", "alta");
  const agora = Date.now();
  const vencidas = (decisions || []).filter((d) => d.deadline_utc && new Date(d.deadline_utc).getTime() < agora).length;
  add(vencidas, "decisão(ões) do Gabinete com prazo vencido", "#operacao/visao-geral/overview-cabinet", "alta");
  const paradas = (connectors || []).filter((c) => c.state === "stale").length;
  add(paradas, "fonte(s) com coleta atrasada", "#operacao/monitoramento/municipal-map-panel", "media");
  if (!worker.queue_available) prioridades.push({count:"!", texto:"fila Redis indisponível — coletas agendadas paradas", href:"#operacao/visao-geral/runs-details", criticidade:"alta"});

  byId("priority-list").innerHTML = prioridades.length
    ? prioridades.map((p) => `<li class="priority-${p.criticidade}"><a href="${p.href}"><strong>${p.count}</strong> ${escapeHtml(p.texto)} →</a></li>`).join("")
    : "<li class='priority-ok'>Nenhuma pendência operacional no momento.</li>";
  byId("overview-priorities").hidden = false;

  renderSourcesHealth(connectors || []);
  renderCabinetDecisions(decisions || []);
  loadEnvironmentalHealth();
  loadMitigation();
  byId("overview-cabinet").hidden = false;
}

// Ações do operador sobre as fontes, sem precisar de linha de comando.
async function coletarFonte(sourceId, botao) {
  const state = byId("collect-state");
  const original = botao.textContent;
  botao.disabled = true; botao.textContent = "Coletando…";
  try {
    const resumo = await request(`/ingestion/runs/collect/source/${sourceId}`, {
      method: "POST", headers: {Authorization: `Bearer ${operationalToken}`},
    });
    state.textContent = `Coleta concluída: ${resumo.records_accepted ?? 0} registro(s) aceito(s), ${resumo.records_deduplicated ?? 0} deduplicado(s).`;
    await loadOperation(operationalToken);
  } catch (error) {
    state.textContent = `Falha na coleta: ${error.message}`;
    botao.disabled = false; botao.textContent = original;
  }
}
async function desativarFonte(sourceId, nome) {
  if (!confirm(`Desativar a fonte "${nome}"?\n\nEla deixa de ser coletada e sai dos alarmes, mas o histórico é preservado e ela pode ser reativada depois.`)) return;
  const state = byId("collect-state");
  try {
    await request(`/catalog/sources/${sourceId}`, {
      method: "PATCH",
      headers: {Authorization: `Bearer ${operationalToken}`, "Content-Type": "application/json"},
      body: JSON.stringify({status: "inactive"}),
    });
    state.textContent = `Fonte "${nome}" desativada. Reative pelo Catálogo quando a origem voltar.`;
    await loadOperation(operationalToken);
  } catch (error) { state.textContent = error.message; }
}
async function coletarTodas() {
  const botao = byId("collect-all");
  const state = byId("collect-state");
  botao.disabled = true; botao.textContent = "Coletando todas as fontes…";
  state.textContent = "Isso pode levar alguns minutos; as origens são consultadas uma a uma.";
  try {
    const resumo = await request("/ingestion/runs/collect/all", {
      method: "POST", headers: {Authorization: `Bearer ${operationalToken}`},
    });
    state.textContent = `Ciclo concluído: ${resumo.sources_processed ?? "—"} fonte(s) processada(s), ${resumo.records_accepted ?? 0} registro(s) aceito(s).`;
    await loadOperation(operationalToken);
  } catch (error) {
    state.textContent = `Falha no ciclo de coleta: ${error.message}`;
  } finally {
    botao.disabled = false; botao.textContent = "↻ Coletar agora (todas)";
  }
}
byId("collect-all")?.addEventListener("click", coletarTodas);

// Operações: saúde de cada fonte, agrupada por estado.
const SOURCE_STATE_LABELS = {
  healthy: ["Operacional", "#16803c"],
  operational: ["Operacional", "#16803c"],
  stale: ["Coleta atrasada", "#b45309"],
  critical: ["Sem coleta recente", "#b91c1c"],
  error: ["Falha na coleta", "#b91c1c"],
  waiting_first_collection: ["Aguardando 1ª coleta", "#0e7490"],
  never_run: ["Aguardando 1º envio", "#0e7490"],
  degraded: ["Degradada", "#b45309"],
  unavailable: ["Indisponível", "#b91c1c"],
};
function renderSourcesHealth(connectors) {
  const host = byId("sources-health");
  if (!host) return;
  if (!connectors.length) {
    host.innerHTML = "<p class='muted'>Nenhuma fonte cadastrada.</p>";
    byId("overview-sources").hidden = false;
    return;
  }
  const ordem = {error:0, unavailable:0, critical:1, stale:2, degraded:3, waiting_first_collection:4, healthy:5, operational:5};
  const lista = [...connectors].sort((a, b) => (ordem[a.state] ?? 9) - (ordem[b.state] ?? 9));
  const problemas = lista.filter((c) => (ordem[c.state] ?? 9) <= 4).length;
  const resumo = problemas
    ? `<p class="sources-summary alerta">${problemas} fonte(s) exigindo atenção · ${lista.length - problemas} operando normalmente</p>`
    : `<p class="sources-summary ok">Todas as ${lista.length} fontes operando normalmente</p>`;
  const linha = (c) => {
    const [rotulo, cor] = SOURCE_STATE_LABELS[c.state] || [c.state, "#5a7a80"];
    const podeColetar = c.access_method !== "manual_file";
    const acoes = `<div class="source-actions">
      ${podeColetar ? `<button type="button" data-collect-source="${c.source_id}">Coletar agora</button>` : ""}
      <button type="button" class="ghost" data-toggle-source="${c.source_id}" data-source-name="${escapeHtml(c.source_name)}">Desativar</button>
    </div>`;
    const atraso = c.delay_minutes != null
      ? (c.delay_minutes < 60 ? `${c.delay_minutes} min` : `${(c.delay_minutes / 60).toFixed(1)} h`)
      : "—";
    const ultima = c.last_success_at ? new Date(c.last_success_at).toLocaleString("pt-BR") : "nunca";
    return `<article class="source-row" style="--state:${cor}">
      <div><strong>${escapeHtml(c.source_name)}</strong><br><small>${escapeHtml(c.access_method)} · esperado a cada ${c.expected_frequency_minutes} min</small></div>
      <div><span class="source-state">${escapeHtml(rotulo)}</span><br><small>atraso: ${atraso} · última: ${ultima}</small></div>
      ${c.last_error ? `<p class="source-error">${escapeHtml(c.last_error).slice(0, 160)}</p>` : ""}
      ${acoes}
    </article>`;
  };
  const comProblema = lista.filter((c) => (ordem[c.state] ?? 9) <= 4);
  const saudaveis = lista.filter((c) => (ordem[c.state] ?? 9) > 4);
  host.innerHTML =
    resumo +
    comProblema.map(linha).join("") +
    (saudaveis.length
      ? `<details class="sources-ok"><summary>${saudaveis.length} fonte(s) operando normalmente</summary>${saudaveis.map(linha).join("")}</details>`
      : "");
  host.querySelectorAll("[data-collect-source]").forEach((botao) => {
    botao.addEventListener("click", () => coletarFonte(botao.dataset.collectSource, botao));
  });
  host.querySelectorAll("[data-toggle-source]").forEach((botao) => {
    botao.addEventListener("click", () => desativarFonte(botao.dataset.toggleSource, botao.dataset.sourceName));
  });
  byId("overview-sources").hidden = false;
}

// ---------- Planejamento e mitigação ----------
const RISK_THEMES = {
  calor: ["Calor extremo", "🌡"], baixa_umidade: ["Baixa umidade", "💨"],
  queimada: ["Queimada", "🔥"], fumaca: ["Fumaça", "🌫"],
  cheia: ["Cheia / alagamento", "🌊"], deslizamento: ["Deslizamento", "⛰"],
  qualidade_ar: ["Qualidade do ar", "🏭"], outro: ["Outro", "•"],
};
const MITIGATION_STATUS = {
  planejada: ["Planejada", "#0e7490"], em_execucao: ["Em execução", "#b45309"],
  concluida: ["Concluída", "#16803c"], suspensa: ["Suspensa", "#5a7a80"],
  cancelada: ["Cancelada", "#5a7a80"],
};
const PRIORITY_COLORS = {critica: "#7f1d1d", alta: "#b91c1c", media: "#b45309", baixa: "#5a7a80"};
function renderMitigation(actions) {
  const lista = byId("mitigation-list");
  const resumo = byId("mitigation-summary");
  if (!lista) return;
  const total = actions.length;
  const concluidas = actions.filter((a) => a.status === "concluida").length;
  const execucao = actions.filter((a) => a.status === "em_execucao").length;
  const investimento = actions.reduce((s, a) => s + (a.estimated_cost_brl || 0), 0);
  resumo.innerHTML = total
    ? `<article><strong>${total}</strong><span>ações registradas</span></article>
       <article><strong>${execucao}</strong><span>em execução</span></article>
       <article><strong>${concluidas}</strong><span>concluídas</span></article>
       <article><strong>${investimento.toLocaleString("pt-BR", {style:"currency", currency:"BRL", maximumFractionDigits:0})}</strong><span>investimento previsto</span></article>`
    : "";
  lista.innerHTML = total
    ? actions.map((a) => {
        const [tema, icone] = RISK_THEMES[a.risk_theme] || [a.risk_theme, "•"];
        const [rotulo, cor] = MITIGATION_STATUS[a.status] || [a.status, "#5a7a80"];
        const prazo = a.deadline_utc ? new Date(a.deadline_utc) : null;
        const vencida = prazo && prazo.getTime() < Date.now() && !["concluida","cancelada"].includes(a.status);
        const acoes = ["concluida","cancelada"].includes(a.status) ? "" :
          `<button type="button" data-action-id="${a.action_id}" data-action-status="em_execucao">Iniciar</button>
           <button type="button" data-action-id="${a.action_id}" data-action-status="concluida">Concluir</button>
           <button type="button" class="ghost" data-action-id="${a.action_id}" data-action-status="suspensa">Suspender</button>`;
        return `<article class="cabinet-card${vencida ? " overdue" : ""}" style="border-left-color:${PRIORITY_COLORS[a.priority] || "#0f766e"}">
          <header><strong>${icone} ${escapeHtml(a.title)}</strong><span class="cabinet-status" style="--status:${cor}">${escapeHtml(rotulo)}</span></header>
          <p>${escapeHtml(a.description)}</p>
          <p class="cabinet-action"><strong>${escapeHtml(tema)}</strong> · ${escapeHtml(a.territory)} · ${escapeHtml(a.responsible_role)} · prioridade ${escapeHtml(a.priority)}</p>
          ${a.indicator ? `<p class="muted">Indicador: ${escapeHtml(a.indicator)}</p>` : ""}
          <p class="${vencida ? "deadline-overdue" : "muted"}">${prazo ? `Prazo: ${prazo.toLocaleDateString("pt-BR")}${vencida ? " — VENCIDO" : ""}` : "Sem prazo"}${a.estimated_cost_brl ? ` · ${a.estimated_cost_brl.toLocaleString("pt-BR", {style:"currency", currency:"BRL", maximumFractionDigits:0})}` : ""} · ${a.progress_pct}% concluído</p>
          <div class="cabinet-actions">${acoes}</div>
        </article>`;
      }).join("")
    : "<p class='muted'>Nenhuma ação registrada. Use “+ Nova ação” para transformar um risco identificado em ação com responsável e prazo.</p>";
  lista.querySelectorAll("[data-action-id]").forEach((botao) => {
    botao.addEventListener("click", () => updateMitigation(botao.dataset.actionId, botao.dataset.actionStatus));
  });
}
async function loadMitigation() {
  if (!operationalToken) return;
  try {
    const acoes = await request("/planning/mitigation/actions", {headers:{Authorization:`Bearer ${operationalToken}`}});
    renderMitigation(acoes);
  } catch (error) { byId("mitigation-state").textContent = error.message; }
}
async function updateMitigation(actionId, status) {
  const state = byId("mitigation-state");
  state.textContent = "Atualizando ação…";
  try {
    await request(`/planning/mitigation/actions/${actionId}`, {
      method: "PATCH",
      headers: {Authorization:`Bearer ${operationalToken}`, "Content-Type": "application/json"},
      body: JSON.stringify({status}),
    });
    state.textContent = "Ação atualizada e registrada na auditoria.";
    await loadMitigation();
  } catch (error) { state.textContent = error.message; }
}
function bindMitigationForm() {
  const form = byId("mitigation-form");
  if (!form) return;
  byId("mitigation-new")?.addEventListener("click", () => { form.hidden = !form.hidden; });
  byId("mitigation-cancel")?.addEventListener("click", () => { form.hidden = true; form.reset(); });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const state = byId("mitigation-state");
    state.textContent = "Registrando ação…";
    const prazo = byId("mitigation-deadline").value;
    const custo = byId("mitigation-cost").value;
    const corpo = {
      risk_theme: byId("mitigation-theme").value,
      action_type: byId("mitigation-type").value,
      territory: byId("mitigation-territory").value.trim(),
      responsible_role: byId("mitigation-role").value.trim(),
      priority: byId("mitigation-priority").value,
      title: byId("mitigation-title-input").value.trim(),
      description: byId("mitigation-description").value.trim(),
      indicator: byId("mitigation-indicator").value.trim() || null,
      estimated_cost_brl: custo ? Number(custo) : null,
      deadline_utc: prazo ? new Date(`${prazo}T12:00:00`).toISOString() : null,
    };
    try {
      await request("/planning/mitigation/actions", {
        method: "POST",
        headers: {Authorization:`Bearer ${operationalToken}`, "Content-Type": "application/json"},
        body: JSON.stringify(corpo),
      });
      state.textContent = "Ação registrada com responsável, prazo e indicador.";
      form.reset(); form.hidden = true;
      await loadMitigation();
    } catch (error) { state.textContent = error.message; }
  });
}
bindMitigationForm();

// ---------- Saúde ambiental: calor, umidade, queimadas e fumaça ----------
const HEALTH_STATE_LABELS = {
  critico: ["Situação crítica", "#7f1d1d"],
  alerta: ["Estado de alerta", "#b91c1c"],
  atencao: ["Estado de atenção", "#b45309"],
  observacao: ["Em observação", "#ca8a04"],
  normal: ["Dentro da normalidade", "#16803c"],
  sem_dado: ["Sem dados suficientes", "#5a7a80"],
};
async function loadEnvironmentalHealth() {
  if (!operationalToken) return;
  const state = byId("health-state");
  if (!state) return;
  try {
    const dados = await request("/environmental-health/indicators", {headers:{Authorization:`Bearer ${operationalToken}`}});
    const [rotulo, cor] = HEALTH_STATE_LABELS[dados.state] || [dados.state, "#5a7a80"];
    state.innerHTML = `<strong style="color:${cor}">${escapeHtml(rotulo)}</strong> · ${dados.observations_considered} observações das últimas 72 h`;
    byId("health-indicators").innerHTML = (dados.indicators || []).map((i) => `
      <article class="health-card" style="--nivel:${i.color}">
        <p class="health-card-title">${escapeHtml(i.title)}</p>
        <p class="health-value">${i.value != null ? escapeHtml(String(i.value)) : "—"}<span>${escapeHtml(i.unit || "")}</span></p>
        <p class="health-level">${escapeHtml(i.level_label)}</p>
        ${i.extra ? `<p class="health-extra">${escapeHtml(i.extra)}</p>` : ""}
        <p class="health-reference" title="${escapeHtml(i.reference)}">Metodologia ⓘ</p>
      </article>`).join("");
    byId("health-actions").innerHTML = (dados.recommended_actions || []).map((a) =>
      `<p><strong>${escapeHtml(a.audience)}</strong><br>${escapeHtml(a.action)}</p>`).join("");
    byId("health-groups").innerHTML = (dados.vulnerable_groups || []).map((g) =>
      `<li>${escapeHtml(g)}</li>`).join("");
    byId("health-disclaimer").textContent = dados.disclaimer || "";
  } catch (error) { state.textContent = error.message; }
}
byId("health-refresh")?.addEventListener("click", loadEnvironmentalHealth);

// ---------- Decisões do Gabinete: registro e acompanhamento ----------
const CABINET_STATUS = {
  open: ["Em aberto", "#b45309"],
  in_progress: ["Em andamento", "#0e7490"],
  completed: ["Concluída", "#16803c"],
  cancelled: ["Cancelada", "#5a7a80"],
};
function renderCabinetDecisions(decisions) {
  const lista = byId("cabinet-list");
  if (!lista) return;
  const agora = Date.now();
  if (!decisions.length) {
    lista.innerHTML = "<p class='muted'>Nenhuma decisão registrada neste filtro. Use “+ Registrar decisão” para incluir a primeira.</p>";
    return;
  }
  lista.innerHTML = decisions.map((d) => {
    const prazo = d.deadline_utc ? new Date(d.deadline_utc) : null;
    const vencida = prazo && prazo.getTime() < agora && !["completed", "cancelled"].includes(d.status);
    const [rotulo, cor] = CABINET_STATUS[d.status] || [d.status, "#5a7a80"];
    const acoes = ["completed", "cancelled"].includes(d.status)
      ? `<small>Encerrada por ${escapeHtml(d.updated_by || "—")}</small>`
      : `<button type="button" data-decision-id="${d.decision_id}" data-decision-status="completed">Concluir</button>
         <button type="button" data-decision-id="${d.decision_id}" data-decision-status="in_progress">Em andamento</button>
         <button type="button" class="ghost" data-decision-id="${d.decision_id}" data-decision-status="cancelled">Cancelar</button>`;
    return `<article class="cabinet-card${vencida ? " overdue" : ""}">
      <header><strong>${escapeHtml(d.territory)}</strong><span class="cabinet-status" style="--status:${cor}">${escapeHtml(rotulo)}</span></header>
      <p>${escapeHtml(d.decision)}</p>
      <p class="cabinet-action"><strong>Ação:</strong> ${escapeHtml(d.responsible_action)} — <em>${escapeHtml(d.responsible_role)}</em></p>
      <p class="${vencida ? "deadline-overdue" : "muted"}">${prazo ? `Prazo: ${prazo.toLocaleString("pt-BR")}${vencida ? " — VENCIDO" : ""}` : "Sem prazo definido"}${d.notes ? ` · ${escapeHtml(d.notes)}` : ""}</p>
      <div class="cabinet-actions">${acoes}</div>
    </article>`;
  }).join("");
  lista.querySelectorAll("[data-decision-id]").forEach((botao) => {
    botao.addEventListener("click", () => updateCabinetDecision(botao.dataset.decisionId, botao.dataset.decisionStatus));
  });
}
function cabinetFilter() {
  return document.querySelector('input[name="cabinet-filter"]:checked')?.value || "open";
}
async function loadCabinetDecisions() {
  if (!operationalToken) return;
  const filtro = cabinetFilter();
  const query = filtro === "open" ? "?status=open" : "";
  try {
    const decisions = await request(`/planning/cabinet/decisions${query}`, {headers:{Authorization:`Bearer ${operationalToken}`}});
    renderCabinetDecisions(decisions);
  } catch (error) { byId("cabinet-form-state").textContent = error.message; }
}
async function updateCabinetDecision(decisionId, status) {
  if (!operationalToken) return;
  const state = byId("cabinet-form-state");
  state.textContent = "Atualizando decisão…";
  try {
    await request(`/planning/cabinet/decisions/${decisionId}`, {
      method: "PATCH",
      headers: {Authorization:`Bearer ${operationalToken}`, "Content-Type": "application/json"},
      body: JSON.stringify({status}),
    });
    state.textContent = "Decisão atualizada e registrada na auditoria.";
    await loadCabinetDecisions();
  } catch (error) { state.textContent = error.message; }
}
function bindCabinetForm() {
  const form = byId("cabinet-form");
  if (!form) return;
  byId("cabinet-new")?.addEventListener("click", () => { form.hidden = !form.hidden; });
  byId("cabinet-cancel")?.addEventListener("click", () => { form.hidden = true; form.reset(); });
  document.querySelectorAll('input[name="cabinet-filter"]').forEach((radio) => {
    radio.addEventListener("change", loadCabinetDecisions);
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!operationalToken) return;
    const state = byId("cabinet-form-state");
    state.textContent = "Registrando decisão…";
    const prazo = byId("cabinet-deadline").value;
    const corpo = {
      territory: byId("cabinet-territory").value.trim(),
      responsible_role: byId("cabinet-role").value.trim(),
      decision: byId("cabinet-decision").value.trim(),
      responsible_action: byId("cabinet-action").value.trim(),
      risk_key: byId("cabinet-risk").value.trim() || `gabinete:${new Date().toISOString().slice(0,10)}`,
      notes: byId("cabinet-notes").value.trim() || null,
      deadline_utc: prazo ? new Date(prazo).toISOString() : null,
      status: "open",
    };
    try {
      await request("/planning/cabinet/decisions", {
        method: "POST",
        headers: {Authorization:`Bearer ${operationalToken}`, "Content-Type": "application/json"},
        body: JSON.stringify(corpo),
      });
      state.textContent = "Decisão registrada com responsável, prazo e trilha de auditoria.";
      form.reset(); form.hidden = true;
      await loadCabinetDecisions();
    } catch (error) { state.textContent = error.message; }
  });
}
bindCabinetForm();

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
const FORECAST_LABELS = {
  temperature_c: "Temperatura",
  humidity_pct: "Umidade relativa",
  rainfall_mm_1h: "Chuva (1 h)",
  wind_speed_mps: "Vento",
};
const RISK_LABELS = { normal: "normal", elevated: "elevado", high: "alto", critical: "crítico" };
function formatForecastValue(variableCode, value) {
  if (value === null || value === undefined) return "n/d";
  const units = { temperature_c: "°C", humidity_pct: "%", rainfall_mm_1h: "mm", wind_speed_mps: "m/s" };
  const decimals = variableCode === "humidity_pct" ? 0 : 1;
  return `${Number(value).toFixed(decimals)} ${units[variableCode] || ""}`.trim();
}
function renderForecastTables(series) {
  if (!Array.isArray(series) || !series.length) return "<p class='muted'>Sem séries previstas.</p>";
  return series.map((item) => {
    const label = FORECAST_LABELS[item.variable_code] || item.variable_code;
    const trend = item.trend_per_hour > 0.005 ? "em elevação" : item.trend_per_hour < -0.005 ? "em queda" : "estável";
    const rows = (item.points || []).map((point) => {
      const risk = RISK_LABELS[point.risk_level] || point.risk_level;
      const riskAttention = point.risk_level !== "normal";
      return `<tr${riskAttention ? " class='forecast-risk'" : ""}><td>${dataUtc(point.valid_at_utc).toLocaleString("pt-BR", {weekday:"short", hour:"2-digit", minute:"2-digit"})}</td><td>${formatForecastValue(item.variable_code, point.predicted_value)}</td><td>${escapeHtml(risk)}</td><td>${point.confidence_score}%</td></tr>`;
    }).join("");
    return `<section class="forecast-block"><h5>${escapeHtml(label)} <small>(${escapeHtml(trend)} · ${item.sample_count} amostras · base ${formatForecastValue(item.variable_code, item.base_value)})</small></h5><table class="forecast-table"><thead><tr><th>Válido para</th><th>Previsto</th><th>Risco</th><th>Confiança</th></tr></thead><tbody>${rows}</tbody></table></section>`;
  }).join("");
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
      byId("report-result").innerHTML = `<article><h4>Previsão para ${result.horizon_hours}h</h4><p>${escapeHtml(result.summary)}</p>${renderForecastTables(result.series)}</article>`;
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

// Ícone simbólico para camadas oficiais (usado por official-layers.js).
function mapSymbolIcon(symbol, kind, label) {
  return L.divIcon({
    className: `map-symbol map-symbol-${kind}`,
    html: `<span role="img" aria-label="${escapeHtml(label)}">${symbol}</span>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  });
}
function resizeAviationMap() {
  if (!aviationMap) return;
  requestAnimationFrame(() => aviationMap.invalidateSize({pan:false, animate:false}));
  setTimeout(() => aviationMap?.invalidateSize({pan:false, animate:false}), 180);
}
// Mapas em rotas: ao entrar em Monitoramento, recalcular os dois mapas.
window.addEventListener("hashchange", () => {
  if (location.hash.includes("operacao/monitoramento")) {
    setTimeout(() => { municipalMap?.invalidateSize({pan:false, animate:false}); resizeAviationMap(); }, 160);
  }
  if (location.hash.includes("public/situacao") || location.hash === "" || location.hash === "#public") {
    setTimeout(() => { if (publicMap) publicMap.invalidateSize({pan:false, animate:false}); else loadPublicMap(); }, 160);
  }
});

// Mapa público (Situação agora): territórios publicados + alertas vigentes.
let publicMap = null;
let publicMapLayers = [];
async function loadPublicMap() {
  const host = byId("public-map");
  if (!host || !window.L) return;
  try {
    const [territories, alerts] = await Promise.all([
      request("/public/territories"),
      request("/public/alerts"),
    ]);
    if (!publicMap) {
      publicMap = L.map("public-map", {scrollWheelZoom:false}).setView([-19.9676, -44.1983], 12);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom:18, attribution:"© OpenStreetMap contributors"}).addTo(publicMap);
    }
    publicMapLayers.forEach((layer) => publicMap.removeLayer(layer));
    publicMapLayers = [];
    const alertedCodes = new Set(alerts.flatMap((a) => a.territory_codes || []));
    territories.forEach((territory) => {
      const emAlerta = alertedCodes.has(territory.territory_code);
      const layer = L.geoJSON(territory.geometry_geojson, {
        style: {color: emAlerta ? "#dc2626" : "#0f766e", weight: 3, fillOpacity: emAlerta ? 0.25 : 0.14},
      }).bindPopup(`<strong>${escapeHtml(territory.territory_name)}</strong><br>${escapeHtml(territory.territory_type)}${emAlerta ? "<br><strong>⚠ Alerta oficial vigente</strong>" : ""}`).addTo(publicMap);
      try {
        const center = layer.getBounds().getCenter();
        const label = L.marker(center, {icon: L.divIcon({className:"territory-label", html:`<span>${escapeHtml(territory.territory_name)}${emAlerta ? " ⚠" : ""}</span>`, iconSize:null})}).addTo(publicMap);
        publicMapLayers.push(label);
      } catch (error) { /* geometria sem bounds válidos */ }
      publicMapLayers.push(layer);
    });
    if (publicMapLayers.length) {
      const bounds = L.featureGroup(publicMapLayers).getBounds();
      if (bounds.isValid()) publicMap.fitBounds(bounds, {padding:[24,24], maxZoom:13});
    }
    requestAnimationFrame(() => publicMap.invalidateSize({pan:false, animate:false}));
    setTimeout(() => publicMap?.invalidateSize({pan:false, animate:false}), 200);
    byId("public-map-state").textContent = alertedCodes.size
      ? "Áreas em vermelho possuem alerta oficial vigente — toque para detalhes."
      : "Sem alertas vigentes nas áreas publicadas. Toque em uma área para detalhes.";
  } catch (error) { byId("public-map-state").textContent = error.message; }
}
// ---------- Pontos de monitoramento (mapa público e operacional) ----------
const MONITORING_LABELS = {
  temperature_c: ["Temperatura", "°C"],
  humidity_pct: ["Umidade", "%"],
  dew_point_c: ["Ponto de orvalho", "°C"],
  rainfall_mm_1h: ["Chuva (1 h)", "mm"],
  wind_speed_mps: ["Vento", "m/s"],
  wind_direction_deg: ["Direção do vento", "°"],
  cloud_cover_pct: ["Cobertura de nuvens", "%"],
  visibility_m: ["Visibilidade", "m"],
  pressure_hpa: ["Pressão", "hPa"],
  wind_gust_mps: ["Rajada", "m/s"],
  solar_radiation_kjm2: ["Radiação solar", "kJ/m²"],
  temperature_max_c: ["Temp. máxima", "°C"],
  temperature_min_c: ["Temp. mínima", "°C"],
  river_level_m: ["Nível do rio", "m"],
  river_flow_m3s: ["Vazão", "m³/s"],
};
const FOG_COLORS = {alto: "#b91c1c", moderado: "#b45309", baixo: "#5a7a80"};
const MONITORING_ICONS = {fluviometrica: "≋", meteorologica: "⌂", modelo: "◈"};
function compassDirection(degrees) {
  const rumos = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSO","SO","OSO","O","ONO","NO","NNO"];
  return rumos[Math.round(Number(degrees) / 22.5) % 16] || "";
}
function monitoringPopup(point) {
  const linhas = Object.entries(point.variables || {}).map(([code, item]) => {
    const meta = MONITORING_LABELS[code];
    if (!meta) return "";
    const extra = code === "wind_direction_deg" ? ` (${compassDirection(item.value)})` : "";
    return `<tr><td>${meta[0]}</td><td><strong>${item.value} ${item.unit || meta[1]}</strong>${extra}</td></tr>`;
  }).join("");
  let chuva = "";
  if (point.rainfall_accumulation_mm) {
    const a = point.rainfall_accumulation_mm;
    chuva = `<p class="popup-block"><strong>Chuva acumulada</strong><br>1 h: ${a["1h"]} mm · 6 h: ${a["6h"]} mm<br>24 h: ${a["24h"]} mm · 72 h: ${a["72h"]} mm</p>`;
  }
  let nivel = "";
  if (point.river_level) {
    const r = point.river_level;
    const seta = r.trend === "subindo" ? "▲" : r.trend === "descendo" ? "▼" : "▬";
    const cor = r.trend === "subindo" ? "#b91c1c" : r.trend === "descendo" ? "#16803c" : "#5a7a80";
    nivel = `<p class="popup-block"><strong>Nível do rio: ${r.value_m} m</strong><br><span style="color:${cor};font-weight:700">${seta} ${r.trend} (${r.rate_cm_h > 0 ? "+" : ""}${r.rate_cm_h} cm/h)</span></p>`;
  }
  let nevoeiro = "";
  if (point.fog_risk) {
    const f = point.fog_risk;
    nevoeiro = `<p class="popup-block" style="border-left:4px solid ${FOG_COLORS[f.level] || "#5a7a80"}"><strong>🌫 ${escapeHtml(f.label)}</strong>${f.reasons?.length ? `<br><small>${escapeHtml(f.reasons.join("; "))}</small>` : ""}</p>`;
  }
  const quando = dataHoraLocal(point.observed_at_utc);
  return `<div class="monitoring-popup"><strong>${escapeHtml(point.source_name)}</strong><br><small>${escapeHtml(point.institution)}</small>${nevoeiro}${nivel}${chuva}${linhas ? `<table class="popup-table">${linhas}</table>` : ""}<small>Medição: ${quando}</small></div>`;
}
function monitoringIcon(point) {
  const simbolo = MONITORING_ICONS[point.kind] || "•";
  const alerta = point.river_level && point.river_level.trend === "subindo";
  return L.divIcon({
    className: `monitoring-marker monitoring-${point.kind}${alerta ? " monitoring-rising" : ""}`,
    html: `<span>${simbolo}</span>`,
    iconSize: [30, 30], iconAnchor: [15, 15],
  });
}
function renderMonitoringPoints(map, data, layerStore) {
  layerStore.forEach((layer) => map.removeLayer(layer));
  layerStore.length = 0;
  (data.points || []).forEach((point) => {
    if (point.latitude == null || point.longitude == null) return;
    const marker = L.marker([point.latitude, point.longitude], {icon: monitoringIcon(point)})
      .bindPopup(monitoringPopup(point))
      .addTo(map);
    layerStore.push(marker);
  });
  return layerStore.length;
}

// ---------- Previsão diária para o cidadão (72 h) ----------
// Ícones desenhados em SVG: cores consistentes com a condição prevista.
const SKY_ICONS = {
  "Céu limpo": `<svg viewBox="0 0 48 48" class="sky-icon"><circle cx="24" cy="24" r="10" fill="#f59e0b"/><g stroke="#f59e0b" stroke-width="3" stroke-linecap="round"><path d="M24 4v6M24 38v6M4 24h6M38 24h6M10 10l4 4M34 34l4 4M38 10l-4 4M14 34l-4 4"/></g></svg>`,
  "Predomínio de sol": `<svg viewBox="0 0 48 48" class="sky-icon"><circle cx="18" cy="18" r="8" fill="#f59e0b"/><g stroke="#f59e0b" stroke-width="2.5" stroke-linecap="round"><path d="M18 3v5M3 18h5M7 7l3.5 3.5M29 7l-3.5 3.5"/></g><path d="M16 34a7 7 0 0 1 7-7 8 8 0 0 1 15 2 6 6 0 0 1-1 12H23a7 7 0 0 1-7-7z" fill="#e2e8f0" stroke="#94a3b8" stroke-width="1.5"/></svg>`,
  "Parcialmente nublado": `<svg viewBox="0 0 48 48" class="sky-icon"><circle cx="17" cy="17" r="7" fill="#fbbf24"/><path d="M14 36a8 8 0 0 1 8-8 9 9 0 0 1 17 2 6.5 6.5 0 0 1-1 13H22a8 8 0 0 1-8-7z" fill="#cbd5e1" stroke="#94a3b8" stroke-width="1.5"/></svg>`,
  "Nublado": `<svg viewBox="0 0 48 48" class="sky-icon"><path d="M12 36a9 9 0 0 1 9-9 10 10 0 0 1 19 2 7 7 0 0 1-1 14H21a9 9 0 0 1-9-7z" fill="#94a3b8" stroke="#64748b" stroke-width="1.5"/></svg>`,
  "Nevoeiro": `<svg viewBox="0 0 48 48" class="sky-icon"><g stroke="#94a3b8" stroke-width="3.5" stroke-linecap="round"><path d="M8 18h32M6 26h36M10 34h28M14 42h20"/></g></svg>`,
  "Chuva": `<svg viewBox="0 0 48 48" class="sky-icon"><path d="M12 28a9 9 0 0 1 9-9 10 10 0 0 1 19 2 7 7 0 0 1-1 14H21a9 9 0 0 1-9-7z" fill="#94a3b8"/><g stroke="#2563eb" stroke-width="3" stroke-linecap="round"><path d="M18 38l-2 6M27 38l-2 6M36 38l-2 6"/></g></svg>`,
  "Trovoadas": `<svg viewBox="0 0 48 48" class="sky-icon"><path d="M12 26a9 9 0 0 1 9-9 10 10 0 0 1 19 2 7 7 0 0 1-1 14H21a9 9 0 0 1-9-7z" fill="#64748b"/><path d="M26 32l-8 10h6l-2 6 10-11h-6l2-5z" fill="#f59e0b"/></svg>`,
};
function iconeCondicao(condicao) {
  if (SKY_ICONS[condicao]) return SKY_ICONS[condicao];
  const texto = (condicao || "").toLowerCase();
  if (texto.includes("trovoada")) return SKY_ICONS["Trovoadas"];
  if (texto.includes("chuva") || texto.includes("garoa") || texto.includes("pancada")) return SKY_ICONS["Chuva"];
  if (texto.includes("nevoeiro")) return SKY_ICONS["Nevoeiro"];
  if (texto.includes("nublado")) return SKY_ICONS["Nublado"];
  if (texto.includes("sol")) return SKY_ICONS["Predomínio de sol"];
  return SKY_ICONS["Céu limpo"];
}
// O backend envia UTC; quando o carimbo vem sem sufixo de fuso, o navegador
// interpretaria como hora local e não converteria — por isso normalizamos.
function dataUtc(valor) {
  const texto = String(valor ?? "");
  const temFuso = /[zZ]$|[+-]\d\d:?\d\d$/.test(texto);
  return new Date(temFuso ? texto : `${texto}Z`);
}
function horaLocal(valor) {
  return dataUtc(valor).toLocaleTimeString("pt-BR", {hour: "2-digit", minute: "2-digit"});
}
function dataHoraLocal(valor) {
  return dataUtc(valor).toLocaleString("pt-BR", {dateStyle: "short", timeStyle: "short"});
}
function diaSemana(iso, ehHoje) {
  if (ehHoje) return "Hoje";
  const data = new Date(`${iso}T12:00:00`);
  const dia = data.toLocaleDateString("pt-BR", {weekday: "short"}).replace(".", "");
  return `${dia.charAt(0).toUpperCase()}${dia.slice(1)} ${data.getDate()}`;
}
function chuvaClasse(prob) {
  if (prob == null) return "";
  if (prob >= 70) return "chuva-alta";
  if (prob >= 40) return "chuva-media";
  return "";
}
let diasPrevisao = [];
function abrirDetalheDia(indice) {
  const dia = diasPrevisao[indice];
  const painel = byId("hourly-detail");
  if (!dia || !painel) return;
  const horas = dia.hourly || [];
  painel.innerHTML = horas.length
    ? `<div class="hourly-head"><strong>${escapeHtml(diaSemana(dia.date, dia.is_today))} · ${escapeHtml(dia.condition)}</strong><button type="button" id="hourly-close">Fechar ✕</button></div>
       <div class="hourly-table-wrap"><table class="hourly-table">
         <thead><tr><th>Hora</th><th>Temp.</th><th>Umid.</th><th>Chuva</th><th>Vento</th><th>Nuvens</th></tr></thead>
         <tbody>${horas.map((h) => `<tr>
           <td><strong>${horaLocal(h.time_utc)}</strong></td>
           <td>${h.temperature_c != null ? h.temperature_c.toFixed(1) + " °C" : "—"}</td>
           <td>${h.humidity_pct != null ? Math.round(h.humidity_pct) + "%" : "—"}</td>
           <td>${h.precipitation_mm != null ? h.precipitation_mm.toFixed(1) + " mm" : "—"}</td>
           <td>${h.wind_speed_ms != null ? h.wind_speed_ms.toFixed(1) + " m/s" : "—"}</td>
           <td>${h.cloud_cover_pct != null ? Math.round(h.cloud_cover_pct) + "%" : "—"}</td>
         </tr>`).join("")}</tbody>
       </table></div>
       <p class="muted">Horários no fuso local (Brasília).</p>`
    : "<p class='muted'>Detalhamento horário indisponível para este dia.</p>";
  painel.hidden = false;
  byId("hourly-close")?.addEventListener("click", () => { painel.hidden = true; });
  painel.scrollIntoView({block: "nearest", behavior: "smooth"});
}
async function loadDailyForecast() {
  const host = byId("daily-forecast");
  const state = byId("daily-forecast-state");
  if (!host) return;
  try {
    const previsao = await request("/public/meteorology/forecast/daily?days=3");
    diasPrevisao = previsao.days || [];
    host.innerHTML = diasPrevisao.map((d, indice) => {
      const prob = d.precipitation_probability_pct;
      const chuva = d.precipitation_mm;
      const destaque = indice === 0 ? " destaque" : "";
      const nascer = d.sunrise ? horaLocal(d.sunrise) : null;
      const por = d.sunset ? horaLocal(d.sunset) : null;
      return `<article class="day-card${destaque} ${chuvaClasse(prob)}" data-day-index="${indice}" role="button" tabindex="0" aria-label="Ver detalhamento por horário de ${escapeHtml(diaSemana(d.date, d.is_today))}">
        <header><strong>${escapeHtml(diaSemana(d.date, d.is_today))}</strong>${iconeCondicao(d.condition)}</header>
        <p class="day-condition">${escapeHtml(d.condition)}</p>
        <p class="day-temps"><span class="tmax">${d.temperature_max_c != null ? Math.round(d.temperature_max_c) + "°" : "—"}</span><span class="tmin">${d.temperature_min_c != null ? Math.round(d.temperature_min_c) + "°" : "—"}</span></p>
        <ul class="day-details">
          <li><span>Chuva</span><strong>${prob != null ? Math.round(prob) + "%" : "—"}${chuva ? ` · ${chuva.toFixed(1)} mm` : ""}</strong></li>
          <li><span>Vento máx.</span><strong>${d.wind_max_ms != null ? d.wind_max_ms.toFixed(1) + " m/s" : "—"}</strong></li>
          <li><span>UV máx.</span><strong>${d.uv_index_max != null ? Math.round(d.uv_index_max) : "—"}</strong></li>
          ${nascer && por ? `<li><span>Sol</span><strong>${nascer} · ${por}</strong></li>` : ""}
        </ul>
        ${d.uv_advice ? `<p class="day-advice">${escapeHtml(d.uv_advice)}</p>` : ""}
        <p class="day-more">Ver hora a hora →</p>
      </article>`;
    }).join("");
    host.querySelectorAll("[data-day-index]").forEach((cartao) => {
      const abrir = () => abrirDetalheDia(Number(cartao.dataset.dayIndex));
      cartao.addEventListener("click", abrir);
      cartao.addEventListener("keydown", (evento) => {
        if (evento.key === "Enter" || evento.key === " ") { evento.preventDefault(); abrir(); }
      });
    });
    const emitido = dataHoraLocal(previsao.issued_at_utc);
    state.textContent = `${previsao.location.name} · modelo Open-Meteo emitido em ${emitido} (horário local). ${previsao.disclaimer}`;
  } catch (error) {
    host.innerHTML = "<p class='muted'>Previsão diária indisponível no momento.</p>";
    state.textContent = error.message;
  }
}
window.addEventListener("load", loadDailyForecast);

// Camadas visuais no mapa público (satélite/radar da REDEMET).
let publicImageLayers = {satellite: null, radar: null};
let latestPublicMapLayers = null;
function refreshPublicImageLayers() {
  if (!publicMap) return;
  Object.entries(publicImageLayers).forEach(([nome, layer]) => {
    if (layer) publicMap.removeLayer(layer);
    publicImageLayers[nome] = null;
  });
  if (!latestPublicMapLayers) return;
  const intensidade = Number(byId("public-layer-opacity")?.value || 80) / 100;
  const addImage = (item, enabled, fator) => {
    if (!item?.image_url || !item?.bounds || !enabled) return null;
    return L.imageOverlay(item.image_url, item.bounds, {
      opacity: Math.min(1, intensidade * fator), crossOrigin: true,
    }).addTo(publicMap);
  };
  // O satélite IR realçado tem tons claros: precisa de mais peso que o radar.
  publicImageLayers.satellite = addImage(latestPublicMapLayers.satellite, byId("public-layer-satellite")?.checked, 1);
  publicImageLayers.radar = addImage(latestPublicMapLayers.radar, byId("public-layer-radar")?.checked, 0.9);
}
async function loadPublicMapLayers() {
  const state = byId("public-layers-state");
  try {
    latestPublicMapLayers = await request("/public/map-layers");
    if (state) {
      const satelite = descreverIdadeImagem(latestPublicMapLayers.satellite, "Satélite");
      const radar = descreverIdadeImagem(latestPublicMapLayers.radar, "Radar");
      const temImagem = latestPublicMapLayers.satellite?.image_url || latestPublicMapLayers.radar?.image_url;
      state.className = `${satelite} ${radar}`.includes("⚠") ? "muted stale-warning" : "muted";
      state.textContent = temImagem
        ? `${satelite} · ${radar}`
        : "Imagens de satélite e radar ainda não disponíveis.";
    }
    refreshPublicImageLayers();
  } catch (error) {
    if (state) state.textContent = "Camadas visuais indisponíveis no momento.";
  }
}
["public-layer-satellite", "public-layer-radar", "public-layer-opacity"].forEach((id) => {
  document.getElementById(id)?.addEventListener("input", refreshPublicImageLayers);
});

let publicMonitoringLayers = [];
async function loadPublicMonitoring() {
  if (!publicMap) return;
  try {
    const data = await request("/public/monitoring-points");
    const total = renderMonitoringPoints(publicMap, data, publicMonitoringLayers);
    const state = byId("public-map-state");
    if (state && total) state.textContent = `${total} ponto(s) de monitoramento com dados. Toque em um marcador para ver as medições.`;
  } catch (error) { /* mapa permanece com territórios */ }
}

let operationalMonitoringLayers = [];
async function loadOperationalMonitoring(token) {
  const map = initMunicipalMap();
  if (!map) return;
  try {
    const data = await request("/meteorology/monitoring-points", {headers:{Authorization:`Bearer ${token}`}});
    renderMonitoringPoints(map, data, operationalMonitoringLayers);
  } catch (error) { /* silencioso: camadas de referência seguem disponíveis */ }
}

window.addEventListener("load", () => {
  loadPublicMap().then(() => { loadPublicMonitoring(); loadPublicMapLayers(); });
});

// ---------- Denúncia e relato do cidadão ----------
let citizenReportPosition = null;
function bindCitizenReportForm() {
  const form = byId("citizen-report-form");
  if (!form) return;
  byId("report-use-location")?.addEventListener("click", () => {
    if (!navigator.geolocation) { byId("report-location-state").textContent = "Seu navegador não permite compartilhar localização."; return; }
    byId("report-location-state").textContent = "Obtendo localização…";
    navigator.geolocation.getCurrentPosition(
      (position) => {
        citizenReportPosition = {latitude: Number(position.coords.latitude.toFixed(6)), longitude: Number(position.coords.longitude.toFixed(6))};
        byId("report-location-state").textContent = `Localização anexada (${citizenReportPosition.latitude}, ${citizenReportPosition.longitude}).`;
      },
      () => { byId("report-location-state").textContent = "Não foi possível obter a localização; descreva o endereço no formulário."; }
    );
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const state = byId("citizen-report-state");
    state.textContent = "Enviando relato…";
    const corpo = {
      category: byId("report-category").value,
      description: byId("report-description").value.trim(),
      neighborhood: byId("report-neighborhood").value.trim() || null,
      address: byId("report-address").value.trim() || null,
      reporter_name: byId("report-name").value.trim() || null,
      reporter_contact: byId("report-contact").value.trim() || null,
      ...(citizenReportPosition || {}),
    };
    try {
      const resposta = await request("/public/incident-report", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(corpo)});
      state.innerHTML = `<strong>Protocolo ${escapeHtml(resposta.protocol)}</strong><br>${escapeHtml(resposta.detail)}`;
      form.reset();
      citizenReportPosition = null;
      byId("report-location-state").textContent = "";
    } catch (error) { state.textContent = error.message; }
  });
}
bindCitizenReportForm();

// A aba Território foi retirada da navegação pública: a cobertura territorial
// já é comunicada no Mapa da Cidade, com destaque para áreas sob alerta.
async function loadPublicRecommendations() {
  const state = byId("public-recommendations-state");
  if (!state) return;
  try {
    const items = await request("/public/recommendations");
    byId("public-recommendations").innerHTML = items.length
      ? items.map((r) => `<article><h3>${escapeHtml(r.title)}</h3><p>${escapeHtml(r.audience || "população em geral")}</p></article>`).join("")
      : "<p class='muted'>Nenhuma recomendação pública vigente.</p>";
    state.textContent = `${items.length} recomendação(ões) publicada(s).`;
  } catch (error) { state.textContent = error.message; }
}
window.addEventListener("load", () => { loadPublicRecommendations(); });

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
  const intensidadeAviacao = Number(byId("municipal-layer-opacity")?.value || 80) / 100;
  satelliteLayer = addImage(latestMapLayers.satellite, byId("layer-satellite").checked, intensidadeAviacao);
  radarLayer = addImage(latestMapLayers.radar, byId("layer-radar").checked, Math.min(1, intensidadeAviacao * 0.9));
  if (Array.isArray(latestMapLayers.lightning_events) && latestMapLayers.lightning_events.length && window.L?.heatLayer) {
    lightningLayer = L.heatLayer(latestMapLayers.lightning_events.map((item) => [item.latitude, item.longitude, Math.min(1, item.intensity)]), {radius:28, blur:20, maxZoom:10, gradient:{.2:"#fef08a",.55:"#f97316",.85:"#dc2626"}}).addTo(aviationMap);
  }
}
// As mesmas imagens da REDEMET também no mapa municipal (contexto de nuvens
// e eco de chuva sobre território, estações e ocorrências).
let municipalImageLayers = {satellite: null, radar: null};
function refreshMunicipalImageLayers() {
  if (!municipalMap) return;
  Object.entries(municipalImageLayers).forEach(([nome, layer]) => {
    if (layer) municipalMap.removeLayer(layer);
    municipalImageLayers[nome] = null;
  });
  if (!latestMapLayers) return;
  const intensidade = Number(byId("municipal-layer-opacity")?.value || 80) / 100;
  const addImage = (item, enabled, fator) => {
    if (!item?.image_url || !item?.bounds || !enabled) return null;
    return L.imageOverlay(item.image_url, item.bounds, {
      opacity: Math.min(1, intensidade * fator), crossOrigin: true,
    }).addTo(municipalMap);
  };
  municipalImageLayers.satellite = addImage(latestMapLayers.satellite, byId("municipal-layer-satellite")?.checked, 1);
  municipalImageLayers.radar = addImage(latestMapLayers.radar, byId("municipal-layer-radar")?.checked, 0.9);
}
["municipal-layer-satellite", "municipal-layer-radar", "municipal-layer-opacity"].forEach((id) => {
  document.getElementById(id)?.addEventListener("input", refreshMunicipalImageLayers);
});

// Idade da imagem de sensoriamento remoto: satélite/radar velhos induzem a erro.
function descreverIdadeImagem(item, rotulo) {
  if (!item?.image_url) return `${rotulo}: indisponível`;
  if (!item.captured_at_utc) return `${rotulo}: sem carimbo de hora`;
  const capturada = dataUtc(item.captured_at_utc);
  const minutos = Math.round((Date.now() - capturada.getTime()) / 60000);
  const quando = capturada.toLocaleString("pt-BR", {dateStyle: "short", timeStyle: "short"});
  if (minutos > 180) return `⚠ ${rotulo}: imagem de ${quando} (${(minutos / 60).toFixed(1)} h atrás — desatualizada)`;
  return `${rotulo}: ${quando} (${minutos} min atrás)`;
}
function atualizarEstadoImagens() {
  const alvo = byId("imagery-state");
  if (!alvo || !latestMapLayers) return;
  const satelite = descreverIdadeImagem(latestMapLayers.satellite, "Satélite");
  const radar = descreverIdadeImagem(latestMapLayers.radar, "Radar");
  const desatualizado = `${satelite} ${radar}`.includes("⚠");
  alvo.className = desatualizado ? "imagery-state stale" : "imagery-state";
  alvo.textContent = `${satelite} · ${radar}`;
}
async function loadMapLayers(token = operationalToken) {
  if (!token) return;
  try {
    latestMapLayers = await request("/meteorology/map/layers", {headers:{Authorization:`Bearer ${token}`}});
    refreshImageLayers();
    refreshMunicipalImageLayers();
    atualizarEstadoImagens();
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
      return `<article class="aviation-card"><span class="flight-category" style="--category:${meta.color}">${escapeHtml(meta.label)}</span><h4>${escapeHtml(item.icao)} · ${escapeHtml(item.airport_name)}</h4><p>${escapeHtml(item.source_note)}</p>${metar}<small>METAR válido: ${item.metar_valid_at_utc ? dataHoraLocal(item.metar_valid_at_utc) : "indisponível"}</small></article>`;
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

// Atualização automática: painel operacional a cada 5 min; público a cada 10 min.
setInterval(() => {
  if (operationalToken) loadOperation(operationalToken).catch(() => {});
}, 5 * 60 * 1000);
setInterval(() => {
  loadPublic();
  loadPublicMap().then(() => { loadPublicMonitoring(); loadPublicMapLayers(); });
  loadDailyForecast();
  loadPublicRecommendations();
  if (typeof loadCurrentConditions === "function") loadCurrentConditions();
  if (typeof loadPublicForecast === "function") loadPublicForecast();
  if (typeof loadDailyBrief === "function") loadDailyBrief();
}, 10 * 60 * 1000);
