const currentConditionVariables = {
  temperature_c: {id:"current-temperature", unit:"°C", digits:1},
  rainfall_mm_1h: {id:"current-rainfall", unit:"mm", digits:1},
  humidity_pct: {id:"current-humidity", unit:"%", digits:0},
  wind_speed_mps: {id:"current-wind", unit:"m/s", digits:1},
};
function conditionTime(value) { const text = String(value); return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(text) ? text : `${text}Z`); }
function conditionKindLabel(kind) {
  return ({observation:"Observação",forecast:"Previsão",model_estimate_or_forecast:"Estimativa de modelo"})[kind] || "Dado publicado";
}
function renderCurrentCondition(variable, item) {
  const config = currentConditionVariables[variable];
  const card = document.getElementById(config.id);
  if (!card) return;
  if (!item) {
    card.querySelector("strong").textContent = "—";
    card.querySelector("small").textContent = "Dado público indisponível";
    return;
  }
  const value = Number(item.value).toLocaleString("pt-BR", {minimumFractionDigits:config.digits, maximumFractionDigits:config.digits});
  card.querySelector("strong").textContent = `${value} ${item.unit || config.unit}`;
  const time = conditionTime(item.observed_at_utc).toLocaleString("pt-BR", {dateStyle:"short", timeStyle:"short"});
  card.querySelector("small").textContent = `${conditionKindLabel(item.data_kind)} · ${time}`;
  card.dataset.kind = item.data_kind || "published";
}
async function loadCurrentConditions() {
  const state = document.getElementById("current-conditions-state");
  try {
    const response = await request("/public/open-data/observations?page_size=1000");
    const now = Date.now();
    const nearest = {};
    for (const item of response.items || []) {
      if (!currentConditionVariables[item.variable_code]) continue;
      const distance = Math.abs(conditionTime(item.observed_at_utc).getTime() - now);
      if (!nearest[item.variable_code] || distance < nearest[item.variable_code].distance) nearest[item.variable_code] = {item, distance};
    }
    Object.keys(currentConditionVariables).forEach(variable => renderCurrentCondition(variable, nearest[variable]?.item));
    const available = Object.keys(nearest).length;
    state.textContent = available ? `Atualizado com ${available} de 4 variáveis públicas disponíveis.` : "Ainda não há dados públicos validados para estas variáveis.";
  } catch (error) {
    Object.keys(currentConditionVariables).forEach(variable => renderCurrentCondition(variable, null));
    state.textContent = error.message;
  }
}
window.addEventListener("load", loadCurrentConditions);

const forecastVariables = {
  temperature_c:{label:"Temperatura",unit:"°C",digits:1},
  rainfall_mm_1h:{label:"Precipitação",unit:"mm",digits:1},
  humidity_pct:{label:"Umidade",unit:"%",digits:0},
  wind_speed_mps:{label:"Vento",unit:"m/s",digits:1},
};
async function loadPublicForecast() {
  const state = document.getElementById("public-forecast-state");
  const grid = document.getElementById("public-forecast-grid");
  if (!state || !grid) return;
  try {
    const forecast = await request("/public/meteorology/forecast");
    const times = forecast.series?.[0]?.points || [];
    grid.innerHTML = times.map((base, index) => {
      const values = forecast.series.map(series => {
        const config = forecastVariables[series.variable_code];
        const point = series.points[index];
        if (!config || !point) return "";
        const value = Number(point.predicted_value).toLocaleString("pt-BR", {maximumFractionDigits:config.digits,minimumFractionDigits:config.digits});
        return `<span><small>${config.label}</small><strong>${value} ${series.unit || config.unit}</strong></span>`;
      }).join("");
      const time = new Date(base.valid_at_utc).toLocaleString("pt-BR", {weekday:"short",hour:"2-digit",minute:"2-digit"});
      return `<article><h4>${time}</h4><div>${values}</div></article>`;
    }).join("");
    state.textContent = `Fonte: ${forecast.source.provider} · estimativa de modelo emitida em ${new Date(forecast.issued_at_utc).toLocaleString("pt-BR")}.`;
    document.getElementById("public-forecast-note").textContent = `${forecast.summary} Ponto de referência: ${forecast.source.latitude}, ${forecast.source.longitude} (${forecast.source.timezone}). ${forecast.disclaimer}`;
  } catch (error) {
    state.textContent = error.message;
    grid.innerHTML = "<p class='muted'>Previsão temporariamente indisponível.</p>";
  }
}
window.addEventListener("load", loadPublicForecast);
async function loadDailyBrief() {
  const message = document.getElementById("daily-brief-message");
  try {
    const brief = await request("/public/daily-brief");
    document.getElementById("daily-brief-title").textContent = brief.title;
    message.textContent = brief.message;
    document.getElementById("daily-brief-mode").textContent = brief.generation_mode === "ai_assisted" ? "Texto gerado com assistência de IA" : "Texto factual automático · IA aguardando configuração";
    document.getElementById("daily-brief-time").textContent = `Atualizado em ${new Date(brief.generated_at_utc).toLocaleString("pt-BR")}`;
    const current=brief.facts.current, next=brief.facts.next_24h;
    document.getElementById("daily-brief-details").innerHTML = `<ul><li>Temperatura atual considerada: ${current.temperature_c ?? "indisponível"} °C.</li><li>Faixa estimada em 24h: ${next.temperature_min_c} °C a ${next.temperature_max_c} °C.</li><li>Chuva horária máxima estimada: ${next.rainfall_max_mm_h} mm.</li><li>Vento máximo estimado: ${next.wind_max_m_s} m/s.</li><li>Áreas de trovoada STSC na região: ${brief.facts.regional_thunderstorm_areas}.</li></ul><small>Fontes: ${brief.sources.join(" · ")}</small>`;
    document.getElementById("daily-brief-disclaimer").textContent = brief.disclaimer;
  } catch (error) {
    message.textContent = "A previsão resumida está temporariamente indisponível. Consulte as condições e os alertas oficiais abaixo.";
    document.getElementById("daily-brief-mode").textContent = "Atualização indisponível";
  }
}
window.addEventListener("load", loadDailyBrief);