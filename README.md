# Meteoro — Plataforma Municipal de Inteligência Climática

Repositório principal do sistema municipal de inteligência climática, ambiental e sanitária, com estratégia de **monólito modular orientado a eventos** e evolução incremental do MVP.

## Estrutura inicial

```text
Meteoro/
├── backend/                  # API e regras de domínio (FastAPI)
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   └── modules/
│   └── tests/
├── frontend/                 # Portal público e operacional autenticado
├── infra/                    # Infraestrutura local (Docker)
├── data/                     # Volumes locais de dados (não versionados)
└── .github/                  # Automação futura
```

## Módulos de backend

**Implementados** (api + models + service): identity, catalog, geospatial, ingestion,
data_quality, meteorology, incidents, alerts, recommendations, planning,
communications, operations, audit, public.

**Previstos** (stubs sem implementação): air_quality, health, ml.

## Stack inicial de referência

- **Backend:** Python + FastAPI
- **Dados:** PostgreSQL/PostGIS + Redis + Object Storage (MinIO)
- **Frontend:** portal web responsivo, com Leaflet no ambiente operacional e demonstração React hospedada
- **Arquitetura:** modular, auditável, com separação entre observação, previsão e inferência

## Como executar localmente (base)

1. Suba os serviços de dados (Docker Desktop aberto):
   ```bash
   docker compose up -d
   ```
2. Crie e ative um ambiente Python 3.12 em `backend/` (mesma versão do CI):
   ```bash
   python3.12 -m venv .venv
   .venv\Scripts\activate       # Windows  |  source .venv/bin/activate (Linux/macOS)
   ```
3. Instale dependências:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure o ambiente: copie `.env.example` para `backend/.env` e preencha
   (o `.env` nunca é versionado — ver `docs/security/gestao-de-segredos.md`).
5. Aplique as migrações (caminho canônico de criação do banco; não use `create_all`):
   ```bash
   alembic upgrade head
   ```
6. (Opcional) Popule dados fictícios de demonstração:
   ```bash
   python -m scripts.seed_demo
   ```
7. Rode a API:
   ```bash
   uvicorn app.main:app --reload
   ```
8. (Opcional) Worker de coletas agendadas, em outro terminal:
   ```bash
   python -m app.modules.ingestion.worker
   ```

Portal: <http://127.0.0.1:8000/portal>. Documentação da API: `/docs`.

### Testes e qualidade

Para executar a suíte local e a verificação estática:

```bash
cd backend
pip install -r requirements-dev.txt
ruff check app
pytest -q
```

A esteira em `.github/workflows/ci.yml` executa lint, migração Alembic em PostgreSQL/PostGIS e a suíte automatizada a cada push ou pull request.

### Modos de autenticação

- `AUTH_MODE=local`: usa JWT interno da própria API.
- `AUTH_MODE=hybrid`: aceita JWT interno e token do Keycloak.
- `AUTH_MODE=keycloak`: aceita apenas token do Keycloak.

> Em `AUTH_MODE=keycloak`, os endpoints `/api/v1/auth/bootstrap-admin` e `/api/v1/auth/token` ficam bloqueados.

Configuração mínima para Keycloak:

- `KEYCLOAK_ISSUER_URL`
- `KEYCLOAK_AUDIENCE` (quando o token tiver validação de audiência)
- `KEYCLOAK_JWKS_URL` (opcional; se vazio, será derivada do issuer)

No modo Keycloak, o token externo é validado por assinatura/JWKS e o usuário da plataforma é resolvido por `identity_provider_subject` (sub do token), com vínculo administrativo explícito.

Onboarding administrativo de vínculo:
- `POST /api/v1/auth/admin/keycloak/link` (perfil `admin_general`)

### Ingestão automatizada

O sistema está preparado para operação sem cadastro manual de eventos de ingestão:

- Fontes com `access_method=http`, `s3` ou `manual_file`.
- Fontes de sensores com `access_method=mqtt` (Mosquitto) e `access_method=opcua`.
- Comando de atualização em lote (`collect/all`).
- Monitor de saúde por fonte (`connectors/health`).
- Armazenamento de payload bruto em `INGESTION_STORAGE_PATH` com hash e metadados.
- Parsing automático de payload por perfil de origem (INMET, OPMET, SEMMAD, Sentinel e fallback genérico).
- Parsing automático para fluxo de sensores MQTT/OPC UA (registros com `variable_code`, `value`, `unit`).
- Parsing específico para fiscalização/denúncia com persistência de `incident_reports`.
- Incidentes podem preservar somente a geometria fornecida pela fonte (`location_geojson` ou latitude/longitude); a plataforma não geocodifica endereço nem cria ponto estimado.
- Parsing específico para alertas oficiais (JSON/CSV) com persistência de `official_alerts`.
- Normalização de observações para unidade canônica e UTC.
- Regras automáticas de qualidade por variável (faixa rígida, outlier suave e validação temporal), com geração de `quality_issues`.
- Fechamento automático de alertas vencidos e cobertura territorial consolidada para operação.
- Coleta agendada executada exclusivamente em processo worker, fora da API, com fila Redis e lock distribuído por fonte (`INGESTION_SCHEDULER_ENABLED=true`).

Segurança dos conectores:

- Todo destino de rede precisa estar em `INGESTION_NETWORK_ALLOWED_HOSTS`; a lista aceita host exato e curinga de subdomínio, como `*.dados.gov.br`. Lista vazia bloqueia as coletas de rede.
- HTTP aceita somente HTTPS por padrão (`INGESTION_HTTP_ALLOWED_SCHEMES=https`), não segue redirecionamentos, rejeita IPs privados/locais após resolução DNS, desabilita proxies de ambiente e fixa a conexão em um IP público validado.
- As portas são fechadas por `INGESTION_NETWORK_ALLOWED_PORTS`; `80` só deve ser incluída mediante exceção formal para HTTP sem TLS.
- Buckets S3 precisam estar em `INGESTION_S3_ALLOWED_BUCKETS`.
- HTTP tem tempo máximo (`INGESTION_HTTP_TIMEOUT_SECONDS`), tentativas limitadas com backoff (`INGESTION_HTTP_RETRY_ATTEMPTS`, `INGESTION_HTTP_RETRY_BACKOFF_SECONDS`) e teto de resposta (`INGESTION_HTTP_MAX_RESPONSE_BYTES`). Os limites por fonte podem apenas reduzir o teto global.
- Uploads aceitam apenas JSON/CSV e são lidos em blocos, respeitando `INGESTION_MAX_UPLOAD_BYTES`.

Exemplos de configuração por fonte:
- API OPMET/INMET: `access_method=http`
- MonitorAr/FEAM: `access_method=http` + `source_type=air_quality`, com `connector_config_json={"parser":"monitorar_feam"}`. O ADM informa somente uma URL oficial homologada (JSON, CSV ou GeoJSON); o parser preserva código/nome da estação e normaliza PM₂,₅, PM₁₀, O₃, NO₂, SO₂ e CO. O portal do MonitorAr permite consulta pública por estação, mas não há endpoint público versionado documentado para fixar em código; portanto a URL deve ser registrada no Catálogo Municipal e liberada em `INGESTION_NETWORK_ALLOWED_HOSTS` após validação técnica.
- Planilha SEMMAD: `access_method=manual_file` + endpoint de upload
- AWS/Sentinel em S3: `access_method=s3` com `endpoint_reference=s3://bucket/chave`
- Fiscalização/Denúncia: `access_method=manual_file` + `source_type=incident_report`
- Alertas oficiais: `access_method=manual_file|http|s3` + `source_type=official_alert`
- Sensores via Mosquitto: `access_method=mqtt` + `endpoint_reference=mqtt://broker:1883/topico`
- Sensores via OPC UA: `access_method=opcua` + `endpoint_reference=opc.tcp://host:4840`

Para reprocessar uma fonte HTTP, declare como a API recebe o intervalo; a operação falha se esse contrato não estiver configurado:

```json
{
  "reprocess": {
    "start_query_param": "data_inicio",
    "end_query_param": "data_fim"
  }
}
```

Autenticação de sensores:
- MQTT: `authentication_type=none` ou `mqtt_userpass_env` com `username_env_var/password_env_var` no `connector_config_json`
- OPC UA: `authentication_type=none` ou `opcua_userpass_env` com `username_env_var/password_env_var` no `connector_config_json`

Configuração do scheduler:
- `INGESTION_SCHEDULER_ENABLED=true`
- `INGESTION_SCHEDULER_POLL_SECONDS=60`
- Inicie o processo separado: `python -m app.modules.ingestion.worker`
- A fila usa `REDIS_URL`, `INGESTION_WORKER_QUEUE_NAME`, `INGESTION_WORKER_POLL_SECONDS` e `INGESTION_WORKER_LOCK_TTL_SECONDS`.
- A API expõe `POST /api/v1/ingestion/jobs/collect/source/{source_id}`, `GET /api/v1/ingestion/jobs/{job_id}` e `GET /api/v1/ingestion/worker/status` para operação assíncrona.
- Por padrão, uma fonte é executada após `expected_frequency_minutes`. Para horário previsível, use no `connector_config_json` `{"schedule":{"minute_utc":5}}`: uma fonte de 60 minutos será coletada em `HH:05 UTC`. Use `{"schedule":{"enabled":false}}` em fontes exclusivas de reprocessamento manual.
- O perfil de referência histórica e horária de Betim está em [docs/operacao/fontes-historicas-betim.md](docs/operacao/fontes-historicas-betim.md). O Open-Meteo é tratado como estimativa/previsão de modelo, não como estação local.
- Para instalar de uma vez os 12 pontos regionais de contexto de Betim, o ADM usa `POST /api/v1/catalog/sources/profiles/regional-context`. As coletas são horárias e escalonadas; não constituem medição municipal nem alertas oficiais.
- Para instalar idempotentemente as duas fontes Open-Meteo de Betim (previsão horária e histórico manual), use `POST /api/v1/catalog/sources/profiles/betim-open-meteo` com perfil `admin_general` ou `operator`. A API retorna as fontes existentes quando a chamada é repetida.
- Para instalar os quatro conectores REDEMET de contexto aeronáutico regional (status e METAR/SPECI de SBBH e SNDV), use `POST /api/v1/catalog/sources/profiles/redemet-aviation`. Defina `REDEMET_API_KEY` no ambiente do backend e do worker e inclua `api-redemet.decea.mil.br` na allowlist. A chave não é enviada ao navegador nem fica no Catálogo. Após login, o painel mostra o mapa e as mensagens em `GET /api/v1/meteorology/aviation/conditions`. As cores `g/y/r` são condições do aeródromo por visibilidade/teto, não alertas municipais nem observações em Betim.
- Para ativar as camadas visuais, use `POST /api/v1/catalog/sources/profiles/redemet-imagery`. O perfil cria satélite infravermelho realçado e radar MaxCAPPI; o painel operacional consulta `GET /api/v1/meteorology/map/layers` e aplica as imagens como sobreposições Leaflet. As camadas podem ser ligadas/desligadas sem nova coleta. Radar é eco remoto, não confirmação de chuva no solo; satélite não é observação de superfície.
- O mapa também aceita uma fonte municipal/federal homologada de raios em GeoJSON, registrada com `connector_config_json={"parser":"lightning_geojson"}`. O contador é calculado apenas sobre eventos georreferenciados recebidos na última hora dentro do envelope regional de Betim; o ADM pode declarar `interest_bounds` (south, west, north, east) na configuração da fonte. Enquanto não houver fonte configurada, a interface declara indisponibilidade e não apresenta zero artificial.

Configuração adicional de sensores:
- `INGESTION_MQTT_CAPTURE_TIMEOUT_SECONDS=30`
- `INGESTION_OPCUA_TIMEOUT_SECONDS=15`

### Relatório analítico do comitê

Relatório sob demanda com base nas observações normalizadas:
- Tendência por variável (temperatura, umidade, chuva, vento, nível e vazão do rio).
- Alertas por limiar para temperatura, umidade, tempestade (chuva/vento) e nível/vazão dos rios.
- Distribuição de qualidade dos dados e cobertura por fonte.

### Previsão meteorológica solicitada

Previsão operacional sob demanda com base na janela recente de observações:
- projeção por horizonte (ex.: 24h, 48h, 72h),
- séries por variável com tendência horária e score de confiança,
- classificação de risco previsto por ponto de tempo.

### Alertas oficiais e protocolos

Módulo operacional para resposta oficial:
- cadastro/ingestão de alertas oficiais e status (`active`, `expired`, `closed`);
- cobertura por território com priorização por severidade;
- encerramento automático de alertas vencidos e encerramento manual com motivo;
- protocolos versionados com fluxo de ativação, aprovação por autoridade e encerramento.

Governança de conteúdo:

- Protocolos são imutáveis por revisão: uma atualização cria uma nova revisão, preserva a anterior, encadeia a substituição e calcula hash de conteúdo.
- Regras de qualidade e recomendações possuem registros de revisão, família, hash, autor e motivo de alteração.
- Eventos de auditoria guardam snapshot anterior/posterior quando a operação altera conteúdo governado.
- Recomendações entram como `draft`, podem seguir para `in_review` e só passam a `approved` por perfil `authority_approver` distinto do autor. A publicação é uma operação explícita posterior à aprovação, também auditada.

### Portal operacional e público

- A API serve o portal estático em `/portal/`, incluindo manifesto e service worker para instalação como PWA.
- A área operacional autentica contra `/api/v1/auth/token` e apresenta execuções, conectores e saúde do worker.
- A visão operacional autenticada consolida situação, territórios, estações, alertas oficiais e ocorrências georreferenciadas em `GET /api/v1/operations/situation` e `GET /api/v1/operations/map`. A geometria de alerta representa cobertura territorial, não confirmação de ocorrência no local.
- Ocorrências sem coordenada ou GeoJSON ficam na fila de triagem e não são desenhadas no mapa. A resposta do mapa não inclui endereço, relato ou outros dados pessoais.
- A superfície pública permanece desabilitada até `PUBLIC_ORGANIZATION_ID` ser configurado.
- Quando habilitada, a API pública expõe somente alertas oficiais vigentes, recomendações cuja versão mais recente esteja publicada, territórios ativos e observações com qualidade `valid` originadas de fonte explicitamente classificada como pública. Nunca expõe payload bruto, URL de conector, erro técnico ou dado interno.
- Para autorizar uma fonte no catálogo para dados abertos, o ADM inclui `"classification":"public"` (ou `public_aggregate`) no `connector_config_json`. Também pode declarar `"data_kind":"observation|forecast|model_estimate_or_forecast"`; o tipo é devolvido para impedir que uma estimativa seja apresentada como medição local.

### Mensageria multicanal e boletins

Módulo de comunicação operacional com rastreabilidade:
- cadastro de destinatários multicanal (`email`, `sms`, `whatsapp`, `webhook`);
- gestão de consentimento (`opt_in`, `opt_out`, `pending`) para conformidade de envio;
- criação de despachos manuais (`bulletin_dispatches`) e trilha de entregas por destinatário;
- geração de boletim diário com resumo analítico e alertas oficiais ativos;
- envio simulado com status (`sent`, `skipped_opt_out`) e consolidação (`sent`, `partial`, `cancelled`).

## Endpoints iniciais

- `GET /health` — status da API
- `GET /api/v1/status` — status da versão inicial
- `POST /api/v1/auth/bootstrap-admin` — criação inicial do primeiro administrador
- `POST /api/v1/auth/token` — login e emissão de JWT
- `GET /api/v1/auth/me` — dados do usuário autenticado
- `GET /api/v1/auth/provider` — modo de autenticação ativo
- `POST /api/v1/auth/admin/keycloak/link` — vincula usuário da plataforma a subject do Keycloak (**requer admin_general**)
- `GET /api/v1/catalog/sources` — fontes cadastradas (**requer token**)
- `POST /api/v1/catalog/sources` — cadastro de fonte (**requer token**)
- `PATCH /api/v1/catalog/sources/{source_id}` — atualização de configuração da fonte (**requer token**)
- `GET /api/v1/ingestion/runs/latest` — últimas execuções (**requer token**)
- `POST /api/v1/ingestion/runs/reprocess` — reprocessamento (**requer token**)
- `POST /api/v1/ingestion/runs/collect/source/{source_id}` — coleta imediata de uma fonte (**requer token**)
- `POST /api/v1/ingestion/runs/import/source/{source_id}` — importação de arquivo para fonte manual (**requer token**)
- `POST /api/v1/ingestion/runs/collect/all?only_due=false` — atualização da base por comando (**requer token**)
- `GET /api/v1/ingestion/connectors/health` — monitor de conectores (**requer token**)
- `GET /api/v1/ingestion/observations/latest` — observações parseadas e qualificadas (**requer token**)
- `POST /api/v1/ingestion/jobs/collect/source/{source_id}` — enfileira coleta de fonte (**requer token**)
- `GET /api/v1/ingestion/jobs/{job_id}` — status de um job de ingestão (**requer token**)
- `GET /api/v1/ingestion/worker/status` — saúde da fila e heartbeat do worker (**requer token**)
- `GET /api/v1/meteorology/forecast` — previsão meteorológica sob demanda (**requer token**)
- `GET /api/v1/operations/situation` — resumo para central operacional (**requer token**)
- `GET /api/v1/operations/map` — coleções GeoJSON de territórios, estações, alertas e ocorrências georreferenciadas (**requer token**)
- `GET /api/v1/incidents/reports` — fila de incidentes importados por arquivo (**requer token**)
- `PATCH /api/v1/incidents/reports/{report_id}/triage` — triagem de ocorrência (**requer token**)
- `GET /api/v1/planning/committee/climate-report` — relatório analítico para comitê (**requer token**)
- `GET /api/v1/planning/committee/climate-report.pdf` — relatório analítico em PDF textual (**requer token**)
- `GET /api/v1/planning/committee/climate-report.csv` — tendências e alertas por limiar em CSV (**requer token**)
- `GET /api/v1/planning/stations/availability` — disponibilidade, completude e atraso por estação (**requer token**)
- `GET /api/v1/planning/stations/availability.csv` — disponibilidade por estação em CSV (**requer token**)
- `GET /api/v1/planning/stations/availability.pdf` — disponibilidade por estação em PDF textual (**requer token**)
- `GET /api/v1/alerts/official` — lista de alertas oficiais (**requer token**)
- `POST /api/v1/alerts/official` — cadastro manual de alerta oficial (**requer token**)
- `POST /api/v1/alerts/official/close-expired` — encerra alertas vencidos (**requer token**)
- `POST /api/v1/alerts/official/{official_alert_id}/close` — encerra alerta manualmente (**requer token**)
- `GET /api/v1/alerts/official/coverage` — cobertura territorial de alertas ativos (**requer token**)
- `GET /api/v1/alerts/protocols` — lista de templates de protocolo (**requer token**)
- `POST /api/v1/alerts/protocols` — cria template de protocolo (**requer token**)
- `PATCH /api/v1/alerts/protocols/{protocol_id}` — atualiza template de protocolo (**requer token**)
- `POST /api/v1/alerts/protocols/{protocol_id}/activate` — ativa protocolo (**requer token**)
- `GET /api/v1/alerts/protocol-activations` — lista ativações de protocolo (**requer token**)
- `POST /api/v1/alerts/protocol-activations/{activation_id}/approve` — aprova ativação pendente (**requer token**)
- `POST /api/v1/alerts/protocol-activations/{activation_id}/close` — encerra ativação (**requer token**)
- `POST /api/v1/recommendations/{revision_id}/approve` — aprova recomendação em revisão (**requer authority_approver e segregação do autor**)
- `POST /api/v1/recommendations/{revision_id}/publish` — publica recomendação aprovada (**requer authority_approver**)
- `GET /api/v1/communications/recipients` — lista destinatários de comunicação (**requer token**)
- `POST /api/v1/communications/recipients` — cadastra destinatário de comunicação (**requer token**)
- `PATCH /api/v1/communications/recipients/{recipient_id}/consent` — atualiza consentimento (**requer token**)
- `GET /api/v1/communications/dispatches` — lista despachos de boletins (**requer token**)
- `POST /api/v1/communications/dispatches` — cria despacho manual de boletim (**requer token**)
- `POST /api/v1/communications/dispatches/{dispatch_id}/send` — envia despacho em rascunho (**requer token**)
- `GET /api/v1/communications/dispatches/{dispatch_id}/deliveries` — lista entregas do despacho (**requer token**)
- `POST /api/v1/communications/bulletins/daily/generate` — gera boletim diário e pode enviar automaticamente (**requer token**)
- `GET /api/v1/data-quality/issues` — fila de qualidade (**requer token**)
- `POST /api/v1/data-quality/issues/{issue_id}/review` — revisão (**requer token**)
- `GET /api/v1/audit/events` — trilha de auditoria (**requer token e perfil auditor/admin**)
- `GET /api/v1/public/situation` — situação pública controlada (**sem autenticação; requer PUBLIC_ORGANIZATION_ID**)
- `GET /api/v1/public/alerts` — alertas oficiais vigentes (**sem autenticação**)
- `GET /api/v1/public/recommendations` — recomendações publicadas e vigentes (**sem autenticação**)
- `GET /api/v1/public/open-data` — catálogo e dicionário de dados abertos (**sem autenticação**)
- `GET /api/v1/public/open-data/observations` — dados abertos paginados e filtráveis (**sem autenticação**)
- `GET /api/v1/public/open-data/observations.csv` — exportação CSV dos dados publicados (**sem autenticação**)
- `GET /api/v1/public/methodology` — metodologia de publicação (**sem autenticação**)

## Próximos passos sugeridos

1. Configurar e homologar `PUBLIC_ORGANIZATION_ID`, a licença municipal e as fontes que podem ser classificadas como públicas.
2. Hospedar a API, banco e worker com identidade municipal; apontar o portal operacional autenticado e o site público para esses endpoints; executar testes de acessibilidade e carga antes da abertura externa.
3. Evoluir parser para layouts XLSX/ZIP e classificações municipais específicas.
4. Acrescentar autenticação por certificado para OPC UA e TLS mútuo para MQTT.

### Saídas analíticas e relatórios

- A previsão interna é solicitada em `GET /api/v1/meteorology/forecast`, com `horizon_hours` de 1 a 168, `step_hours` de 1 a 24 e janela-base de 6 a 720 horas. Ela usa tendência estatística das observações válidas, registra auditoria e devolve risco/confiança; não substitui previsão oficial ou de modelo meteorológico.
- O relatório climático do Gabinete aceita período e fontes, retorna tendências, qualidade, cobertura e alertas por limiar em JSON, CSV ou PDF textual autocontido.
- A disponibilidade de estações informa sensores, observações válidas/suspeitas/rejeitadas, completude calculada quando a frequência da fonte está cadastrada e estado operacional. Ausência de observação resulta em `unknown`, jamais em valor zero.
- O portal operacional autenticado oferece a mesma consulta e os downloads PDF/CSV. Os arquivos contêm somente dados permitidos ao perfil do usuário e cada geração é auditada.
