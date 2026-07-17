const guidanceTopics = {
  heat: {title:"Calor e umidade", icon:"☀"},
  air: {title:"Qualidade do ar e fumaça", icon:"◌"},
  fire: {title:"Queimadas e ocorrências", icon:"△"},
};
function guidanceTime(value) { const text=String(value); return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(text)?text:`${text}Z`); }
function valuesFor(items, variable, start, end) { return items.filter(item=>item.variable_code===variable&&guidanceTime(item.observed_at_utc)>=start&&guidanceTime(item.observed_at_utc)<=end).map(item=>Number(item.value)).filter(Number.isFinite); }
function rangeText(values, unit, digits=0) { if(!values.length)return null; const min=Math.min(...values).toFixed(digits).replace(".",","); const max=Math.max(...values).toFixed(digits).replace(".",","); return min===max?`${max} ${unit}`:`${min} a ${max} ${unit}`; }
function hasWords(item, words) { const text=`${item.title||""} ${item.message||""}`.toLowerCase(); return words.some(word=>text.includes(word)); }
function heatGuidance(items, now) {
  const past=new Date(now-86400000), future=new Date(now.getTime()+86400000);
  const recentT=valuesFor(items,"temperature_c",past,now), nextT=valuesFor(items,"temperature_c",now,future);
  const recentH=valuesFor(items,"humidity_pct",past,now), nextH=valuesFor(items,"humidity_pct",now,future);
  if(!recentT.length&&!nextT.length) return {state:"Dados insuficientes",summary:"Ainda não há dados recentes de temperatura e umidade para uma análise segura.",facts:[],advice:["Beba água ao longo do dia.","Evite esforço excessivo nos horários mais quentes.","Observe crianças, idosos e pessoas com doenças crônicas."]};
  const peak=nextT.length?Math.max(...nextT):Math.max(...recentT), lowHumidity=nextH.length?Math.min(...nextH):(recentH.length?Math.min(...recentH):null);
  const attention=peak>=32||lowHumidity!==null&&lowHumidity<=30;
  return {state:attention?"Atenção recomendada":"Condição sem destaque crítico",summary:attention?"As próximas horas podem exigir mais hidratação e menor exposição ao calor.":"Os dados disponíveis não indicam calor ou baixa umidade em nível de destaque nas próximas 24 horas.",facts:[`Temperatura nas últimas 24h: ${rangeText(recentT,"°C",1)||"sem dado"}.`,`Prognóstico de temperatura: ${rangeText(nextT,"°C",1)||"sem dado"}.`,`Menor umidade prevista: ${lowHumidity===null?"sem dado":`${Math.round(lowHumidity)}%`}.`],advice:["Hidrate-se antes de sentir sede.","Prefira sombra e ambientes ventilados.","Se sentir tontura, fraqueza ou confusão, procure ajuda."]};
}
function airGuidance(items, alerts, now) {
  const past=new Date(now-86400000), future=new Date(now.getTime()+86400000), pollutants=["pm25_ugm3","pm10_ugm3","o3_ugm3","no2_ugm3","so2_ugm3","co_mgm3"];
  const recent=items.filter(item=>pollutants.includes(item.variable_code)&&guidanceTime(item.observed_at_utc)>=past&&guidanceTime(item.observed_at_utc)<=now);
  const next=items.filter(item=>pollutants.includes(item.variable_code)&&guidanceTime(item.observed_at_utc)>now&&guidanceTime(item.observed_at_utc)<=future);
  const relevant=alerts.filter(item=>hasWords(item,["fumaça","fumaca","qualidade do ar","polui"]));
  if(!recent.length&&!next.length&&!relevant.length) return {state:"Sem informes relevantes",summary:"Boa notícia! Não foram encontrados informes de fumaça ou piora da qualidade do ar na sua região.",facts:["Não há medição pública de poluentes disponível para complementar esta análise."],advice:["Ajude a manter o ar limpo: não queime resíduos.","Denuncie queimadas pelos canais oficiais.","Se perceber fumaça intensa, reduza a exposição e feche portas e janelas."]};
  return {state:relevant.length?"Atenção a informe oficial":"Monitoramento disponível",summary:relevant.length?"Há informe oficial relacionado à fumaça ou à qualidade do ar. Consulte os detalhes e siga as orientações públicas.":"Existem dados ambientais publicados para acompanhamento da qualidade do ar.",facts:[`${recent.length} registro(s) de poluentes nas últimas 24h.`,`${next.length} registro(s) no cenário das próximas 24h.`,`${relevant.length} alerta(s) oficial(is) relacionado(s).`],advice:["Reduza esforço ao ar livre se houver fumaça.","Priorize ambientes protegidos.","Pessoas com sintomas respiratórios devem procurar orientação de saúde."]};
}
function fireGuidance(alerts, items, now) {
  const relevant=alerts.filter(item=>hasWords(item,["queimada","incêndio","incendio","fogo","fumaça","fumaca"]));
  const future=new Date(now.getTime()+86400000), wind=valuesFor(items,"wind_speed_mps",now,future), rain=valuesFor(items,"rainfall_mm_1h",now,future);
  if(!relevant.length) return {state:"Sem informes relevantes",summary:"Boa notícia! Não foram encontrados informes de fumaça ou queimadas na sua região.",facts:[`Vento previsto: ${rangeText(wind,"m/s",1)||"sem dado"}.`,`Precipitação prevista: ${rangeText(rain,"mm",1)||"sem dado"}.`],advice:["Mantenha a qualidade do ar: não queime lixo ou vegetação.","Denuncie queimadas e descarte resíduos corretamente.","Ao notar fogo ou risco imediato, ligue 193."]};
  return {state:"Informe oficial ativo",summary:"Há alerta oficial relacionado a fogo, queimada ou fumaça. Evite a área indicada e acompanhe os canais da Defesa Civil.",facts:relevant.map(item=>item.title),advice:["Não se aproxime de focos de incêndio.","Mantenha rotas de acesso livres para equipes de resposta.","Em risco imediato, ligue 193; para Defesa Civil, ligue 199."]};
}
function renderGuidance(topic, analysis) {
  const dialog=document.getElementById("guidance-dialog"), meta=guidanceTopics[topic];
  document.getElementById("guidance-icon").textContent=meta.icon; document.getElementById("guidance-title").textContent=meta.title;
  document.getElementById("guidance-state").textContent=analysis.state; document.getElementById("guidance-summary").textContent=analysis.summary;
  document.getElementById("guidance-facts").innerHTML=analysis.facts.map(item=>`<li>${escapeHtml(item)}</li>`).join("");
  document.getElementById("guidance-advice").innerHTML=analysis.advice.map(item=>`<li>${escapeHtml(item)}</li>`).join("");
  dialog.showModal();
}
async function openGuidance(topic) {
  const button=document.querySelector(`[data-guidance-topic="${topic}"]`); button?.setAttribute("aria-busy","true");
  try { const [data,alerts]=await Promise.all([request("/public/open-data/observations?page_size=1000"),request("/public/alerts")]); const now=new Date(); const analysis=topic==="heat"?heatGuidance(data.items||[],now):topic==="air"?airGuidance(data.items||[],alerts,now):fireGuidance(alerts,data.items||[],now); renderGuidance(topic,analysis); }
  catch(error){renderGuidance(topic,{state:"Análise indisponível",summary:error.message,facts:[],advice:["Consulte os canais oficiais do município."]});}
  finally{button?.removeAttribute("aria-busy");}
}
document.querySelectorAll("[data-guidance-topic]").forEach(button=>button.addEventListener("click",()=>openGuidance(button.dataset.guidanceTopic)));
document.getElementById("guidance-close")?.addEventListener("click",()=>document.getElementById("guidance-dialog").close());
