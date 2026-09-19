# Eco-Gestão Municipal — Estado da Plataforma

Data: 20/07/2026 · Município de referência: Betim/MG
Documento de fechamento do ciclo de desenvolvimento assistido.

---

## 1. O que a plataforma faz hoje

### Para o cidadão (portal público, sem login)

| Recurso | Estado |
|---|---|
| Resumo diário em linguagem simples (com IA opcional) | ✅ operante |
| Condições atuais (temperatura, chuva, umidade, vento) | ✅ operante |
| Previsão de 72 h em cartões diários, com detalhamento hora a hora | ✅ operante |
| Mapa da cidade com limite municipal oficial (IBGE), estações e alertas | ✅ operante |
| Camadas de satélite e radar (REDEMET) | ✅ operante |
| Orientações por tema (calor, qualidade do ar, queimadas) | ✅ operante |
| Canal de denúncia ambiental com protocolo (SEMMAD) | ✅ operante |
| Dados abertos (JSON, CSV, metodologia) | ✅ operante |

### Para o operador e o Gabinete (área restrita)

| Recurso | Estado |
|---|---|
| Visão geral executiva com fila de prioridades | ✅ operante |
| Saúde das 36 fontes com diagnóstico de falha | ✅ operante |
| Mapa operacional (território, estações, ANA, CEMADEN, rede BH, satélite/radar) | ✅ operante |
| Pontos de monitoramento com acumulados de chuva e tendência de nível | ✅ operante |
| Contexto aeronáutico (METAR/SPECI de SBBH e SNDV) | ✅ operante |
| Filas: qualidade de dados, triagem de ocorrências, aprovação de protocolos | ✅ operante |
| Saúde ambiental: índice de calor, baixa umidade, risco de queimada, ações por público | ✅ operante |
| Planejamento e mitigação: ações com responsável, prazo, custo e indicador | ✅ operante |
| Decisões do Gabinete com prazo e trilha de auditoria | ✅ operante |
| Relatórios (previsão, Comitê, disponibilidade) em PDF e CSV | ✅ operante |
| Navegação em foco (um painel por vez, ESC/Voltar/Início) | ✅ operante |

### Fontes de dados integradas (36)

- **Open-Meteo** — ponto de Betim + 12 municípios da região metropolitana
- **REDEMET/DECEA** — METAR, status aeronáutico, satélite IR e radar MaxCAPPI
- **ANA/SNIRH** — 8 estações telemétricas de nível (Rio Betim e Paraopeba)
- **INMET** — 4 estações regionais (via importação do catálogo; API pública instável)
- **Camadas de referência** — cursos d'água (ANA), pluviômetros (CEMADEN), réguas (ANA), rede da Defesa Civil de BH
- **Municipal** — denúncias do cidadão e importação manual

---

## 2. Fundamentos técnicos consolidados

- Cadeia de migrações íntegra (head único) com guard automático no CI
- Testes contra PostgreSQL/PostGIS real, com as migrações de produção
- Boot recusa segredo fraco em produção; `/health/ready` por componente
- Logging estruturado JSON com request-id; erros nunca vazam stacktrace
- Rate limiting na superfície pública; sessão com refresh rotativo e revogação
- Observabilidade: métricas Prometheus com **staleness por fonte** e 7 regras de alerta
- Backup diário com hash e retenção; procedimento de restore documentado
- Empacotamento completo para rodar indoor (compose com API, worker, banco, proxy TLS, monitoramento e backup)

---

## 3. Limitações declaradas (não são defeitos ocultos)

| Item | Situação |
|---|---|
| **Assistência social** | Sem implementação — depende de convênio de dados (CadÚnico, territórios de vulnerabilidade) |
| **Qualidade do ar** | Sem medição própria; requer conector MonitorAr/FEAM homologado ou estação municipal |
| **Queimadas (INPE)** | Serviço geográfico oficial indisponível; camada preparada |
| **Descargas atmosféricas** | Não há feed público gratuito homologado |
| **API do INMET** | `apitempo` retornando vazio; contornado por importação do catálogo |
| **Rio Betim** | Régua da ANA no município é convencional (leitura manual); telemetria vem do entorno + proxy de chuva |

---

## 4. Pendências para o go-live indoor

1. Ensaiar `infra/docker/compose.prod.yml` em máquina com Docker
2. Definir IP fixo/hostname, firewall e distribuir a CA interna nas estações
3. Executar o primeiro restore de ensaio (procedimento em `docs/operations/backup-e-restore.md`)
4. Configurar o canal de alertas no Alertmanager
5. Criar usuários nominais por perfil e treinar operadores
6. Iniciar o piloto de 4 semanas (`docs/operations/protocolo-piloto-assistido.md`)

---

## 4-A. Manual de atualização dos dados (passo a passo)

> Regra de ouro: **quem coleta é o worker, não a tela**. Abrir o portal nunca
> busca dado novo na origem — apenas mostra o que já foi coletado. Por isso o
> worker precisa estar sempre no ar.

### 0. Ligar o motor de coleta (pré-requisito de tudo)

**Opção A — ambiente indoor definitivo (recomendado).** Sobe tudo junto e
reinicia sozinho após queda de energia ou reboot:

```powershell
cd C:\Users\Keller\Downloads\Meteoro\Meteoro
docker compose -f infra/docker/compose.prod.yml --env-file infra/docker/.env.prod up -d
docker compose -f infra/docker/compose.prod.yml ps
```

Não é preciso mais nada: API, worker, Redis, banco, backup e monitoramento
ficam ativos com `restart: unless-stopped`.

**Opção B — ambiente de desenvolvimento (três terminais).**

```powershell
# Terminal 1 — fila
docker start meteoro-redis

# Terminal 2 — API
cd C:\Users\Keller\Downloads\Meteoro\Meteoro\backend
uvicorn app.main:app --reload

# Terminal 3 — worker (é ELE que coleta)
cd C:\Users\Keller\Downloads\Meteoro\Meteoro\backend
python -m app.modules.ingestion.worker
```

O `.env` precisa conter `INGESTION_SCHEDULER_ENABLED=true`.

**Como confirmar que está coletando:** portal → Operação → Visão geral →
"Operações — saúde das fontes". O topo deve dizer *"Todas as N fontes operando
normalmente"*. Se aparecer "fila Redis indisponível", o worker está parado.

---

### 1. REDEMET — atualização automática a cada 15/30 min

**Já está configurada.** Cada fonte tem sua frequência declarada no catálogo:

| Fonte REDEMET | Frequência |
|---|---|
| Status aeronáutico SBBH e SNDV | 15 min |
| METAR/SPECI SBBH e SNDV | 30 min |
| Satélite IR realçado | 15 min |
| Radar MaxCAPPI | 15 min |

O worker consulta o catálogo, identifica as fontes vencidas e enfileira a
coleta — sem intervenção humana. Para forçar uma atualização imediata:

```powershell
$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/auth/token -ContentType "application/json" -Body '{"email":"SEU_EMAIL","password":"SUA_SENHA"}'
$h = @{ Authorization = "Bearer $($r.access_token)" }
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/ingestion/runs/collect/all -Headers $h
```

Para alterar a frequência de uma fonte (exemplo: METAR a cada 20 min):

```powershell
$fontes = Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/catalog/sources -Headers $h
$metar = $fontes | Where-Object { $_.source_name -like "*METAR/SPECI SBBH*" }
$body = @{ expected_frequency_minutes = 20 } | ConvertTo-Json
Invoke-RestMethod -Method Patch -Uri "http://127.0.0.1:8000/api/v1/catalog/sources/$($metar.source_id)" -ContentType "application/json" -Headers $h -Body $body
```

> **Atenção:** o METAR é emitido de hora em hora pelo aeródromo. Coletar com
> frequência menor que 30 min não traz dado novo — só consome a cota da API.
> A chave `REDEMET_API_KEY` fica no `.env`; se expirar, todas as fontes
> REDEMET passam a falhar juntas (visível no painel de saúde das fontes).

---

### 2. Estações automáticas — o que é "tempo real" de verdade

**Não existe atualização a cada clique do usuário — e isso é correto.** Cada
origem publica com sua própria cadência; consultar mais rápido não cria dado:

| Origem | Publicação real | Coleta configurada |
|---|---|---|
| Open-Meteo (modelo) | horária | 60 min |
| ANA telemetria (nível de rio) | horária | 60 min |
| INMET estações automáticas | horária | 60 min |
| CEMADEN (camada de referência) | ~10 min | cache de 10 min no mapa |

O portal se renova sozinho: **painel operacional a cada 5 min** e **área
pública a cada 10 min**, exibindo sempre a última coleta com o horário da
medição. O que o operador deve vigiar não é o relógio da tela, e sim o
**staleness**: se uma fonte crítica passa de 2 h sem coletar, o alarme
`FonteCriticaParada` dispara no canal da equipe.

Verificação rápida do atraso de cada fonte:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/ingestion/connectors/health -Headers $h |
  Select-Object source_name, state, delay_minutes, last_success_at | Format-Table
```

---

### 3. Arquivos manuais (CSV) — o que baixar, onde e com que frequência

| Arquivo | Onde baixar | Frequência | Responsável |
|---|---|---|---|
| **Catálogo de estações automáticas do INMET** (série horária) | <https://portal.inmet.gov.br/paginas/catalogoaut> → escolher estação (A535 Florestal, A555 Ibirité, A521 Pampulha, A537 Cercadinho) → definir período → "Baixar CSV" | **Diária**, enquanto a API `apitempo` estiver indisponível | Operador de plantão |
| **BDMEP — série histórica** | <https://bdmep.inmet.gov.br/> | Eventual (climatologia, normais) | Analista |
| **Pluviômetros CEMADEN** | <https://mapainterativo.cemaden.gov.br/> (envio por e-mail) | Eventual | Analista |
| **MonitorAr/FEAM** (qualidade do ar) | Exportação estadual autorizada | A definir no convênio | SEMMAD |

**Onde colocar o arquivo:** não existe "pasta mágica". O arquivo é **enviado
para a fonte correspondente** — assim a plataforma registra origem, hash,
horário e responsável (exigência de auditoria). Sugestão de organização local:
`C:\Meteoro\importacoes\AAAA-MM-DD\`.

**Como importar (comando único, encontra a fonte e envia o arquivo):**

```powershell
$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/auth/token -ContentType "application/json" -Body '{"email":"SEU_EMAIL","password":"SUA_SENHA"}'
$h = @{ Authorization = "Bearer $($r.access_token)" }
$fontes = Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/catalog/sources -Headers $h

# Troque A535 pelo código da estação e o caminho pelo arquivo baixado
$fonte = $fontes | Where-Object { $_.source_name -like "*CSV manual A535*" }
curl.exe -X POST "http://127.0.0.1:8000/api/v1/ingestion/runs/import/source/$($fonte.source_id)" `
  -H "Authorization: Bearer $($r.access_token)" `
  -F "file=@C:\Meteoro\importacoes\2026-07-20\A535.csv"
```

**Criar fonte para uma estação nova** (uma vez só, por estação):

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/catalog/sources/profiles/inmet-manual-csv `
  -ContentType "application/json" -Headers $h -Body '{"station_codes":["A535","A555","A521","A537"]}'
```

**Como saber se deu certo:** a resposta traz `records_accepted`. Reenviar o
mesmo arquivo é seguro — o sistema deduplica (`records_deduplicated`) e não
duplica observações.

---

### 4. O que também precisa de rotina (não estava na lista inicial)

| Item | Frequência | Como |
|---|---|---|
| **Rotacionar a chave REDEMET** | Anual ou ao vazar | Portal REDEMET → atualizar `REDEMET_API_KEY` no `.env` → reiniciar |
| **Conferir o backup** | Diária (checklist) | Arquivo `meteoro_<data>.dump` + `.sha256` em `BACKUP_DIR` |
| **Ensaio de restore** | Mensal | `docs/operations/backup-e-restore.md` |
| **Triagem das filas** | Diária | Portal → Visão geral → Prioridades agora |
| **Revisar limiares** | Após evento severo | Calibrar cotas por estação com o ocorrido |
| **Reativar fontes desativadas** | Quando a origem voltar | `PATCH /catalog/sources/{id}` com `status: active` |
| **Atualizar território/organização** | Se mudar o município | `scripts/instalar_territorio_betim.py` e `PUBLIC_ORGANIZATION_ID` |
| **Certificado da CA interna** | Ao trocar de servidor | Reexportar e reinstalar nas estações (`infra/docker/README.md`) |

---

## 5. Documentação de referência

| Documento | Uso |
|---|---|
| `docs/operations/checklist-diario-operador.md` | Rotina de turno |
| `docs/operations/protocolo-piloto-assistido.md` | Condução do piloto e critérios de aceite |
| `docs/operations/backup-e-restore.md` | Continuidade |
| `docs/operacao/rede-hidrometeorologica-municipal.md` | Diagnóstico de lacunas e proposta de rede própria |
| `docs/security/gestao-de-segredos.md` | Política de credenciais |
| `infra/docker/README.md` | Subida do ambiente indoor |
| `PLANO-PRODUCAO-ASSISTIDA.md` | Plano completo com status por etapa |
| `AVALIACAO-MVP-2026-07-16.md` | Avaliação técnica inicial (referência histórica) |

---

## 6. Próximas evoluções sugeridas

**Curto prazo (piloto):** calibrar limiares por estação com cotas reais; homologar conector MonitorAr; ativar alertas no canal da equipe.

**Médio prazo:** convênio com Defesa Civil de BH para séries das estações limítrofes; sensores municipais de nível via MQTT (a plataforma já ingere); climatologia a partir do BDMEP para responder "essa chuva é excepcional?".

**Estrutural (pós-piloto):** contratos modulares com import-linter; parametrização multi-município; console operacional em SPA.
