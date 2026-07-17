# Avaliação do MVP Meteoro — Estrutura, Robustez e Prontidão para Produção

Data: 16/07/2026 · Escopo: backend (FastAPI, ~12,7 mil linhas em 16 módulos), frontend (portal vanilla JS, ~700 linhas), infraestrutura (Docker Compose, CI), documentação.

---

## 1. Visão geral — o que está bem

O projeto está acima da média para um MVP. Pontos fortes concretos:

**Arquitetura.** O monólito modular está bem executado: cada módulo segue o padrão `api / models / schemas / service`, com router central limpo e versionamento de API (`/api/v1`). A separação entre API e worker de ingestão (processo próprio, fila Redis, lock distribuído por fonte, heartbeat) é a decisão certa e rara em MVPs.

**Segurança de ingestão.** O anti-SSRF é de nível profissional: allowlist fechada de hosts/portas/schemes, rejeição de IPs privados após resolução DNS, pin de conexão em IP público validado, sem redirects, limite de bytes de resposta. Poucos sistemas em produção têm isso.

**Governança de dados.** Idempotência de ingestão, hash de payload bruto, normalização para unidade canônica e UTC, regras de qualidade por variável, revisões versionadas de protocolos/recomendações, auditoria, decisão explícita de não geocodificar endereços (só geometria fornecida). Coerente com o propósito de defesa civil.

**Autenticação.** Três modos (local/hybrid/keycloak) com bloqueio correto de endpoints locais no modo keycloak, PBKDF2 com 210 mil iterações e `compare_digest`, RBAC via `require_roles`, isolamento por `organization_id` (multi-tenant desde já).

**Qualidade e documentação.** CI com lint (ruff), migração em PostGIS real e pytest; 25 arquivos de teste; docs de modelo de ameaças, runbook, resposta a incidentes e trilha de capacitação. Scripts de backup/restore existem.

---

## 2. Bloqueadores críticos (corrigir antes de qualquer deploy)

### 2.1 Migrações Alembic quebradas — IDs duplicados e dois heads

Verificado programaticamente:

```
DUPLICADO: 20260715_0012  → recommendation_approval_publication.py  e  recommendation_publication.py
DUPLICADO: 20260715_0013  → geospatial_visibility.py  e  incident_geolocation.py
HEADS sem filhos: 20260714_0012  e  20260715_0014
```

`alembic upgrade head` falha com esse estado — e o cache do pytest confirma: `test_migrations.py::test_alembic_upgrade_creates_idempotency_and_authority_schema` é o último teste com falha registrada. O CI deve estar vermelho.

**Correção:** renumerar as revisões duplicadas (IDs únicos, cadeia linear), criar uma *merge revision* para unificar `20260714_0012_cabinet_decisions` com a cadeia principal, e adicionar ao CI um passo `alembic heads` que falhe se houver mais de um head. Recomendo também trocar IDs manuais sequenciais por IDs gerados pelo Alembic (elimina a raiz do problema: dois desenvolvedores/sessões criando "0012" em paralelo).

### 2.2 Segredo real commitado no repositório

`backend/.env` contém uma `REDEMET_API_KEY` real. Mesmo com `.env` no `.gitignore`, o arquivo está no diretório do projeto e pode já ter sido versionado ou compartilhado.

**Correção imediata:** rotacionar a chave na REDEMET hoje; mover segredos para variáveis de ambiente injetadas (ou secret manager); adicionar `gitleaks`/`detect-secrets` ao CI para bloquear recorrência.

### 2.3 Testes rodam em SQLite; produção é PostgreSQL/PostGIS

O `conftest.py` cria o schema com `Base.metadata.create_all` em SQLite. Isso significa que os testes nunca exercitam as migrações nem o comportamento real do banco (JSON, tipos geoespaciais, constraints, transações). O drift entre modelos e migrações passa despercebido — exatamente o tipo de bug do item 2.1.

**Correção:** rodar a suíte contra PostgreSQL no CI (o serviço já existe no workflow — basta apontar os testes para ele, ou usar testcontainers), aplicando `alembic upgrade head` em vez de `create_all`. SQLite pode continuar para testes unitários rápidos locais.

---

## 3. Robustez para produção (backend)

**`main.py` está cru.** Faltam peças padrão de produção: middleware de logging estruturado com request-id (hoje só o worker tem `basicConfig`), handler global de exceções com envelope de erro padronizado, security headers (HSTS, X-Content-Type-Options, CSP), GZip, e condicionar `docs_url`/`redoc_url` a `environment != "production"`.

**Readiness implementado mas não exposto.** `app/core/health.py` tem um `readiness_report()` completo (banco, storage, Redis, estado degradado) que nunca é montado em endpoint. Exponha `/health/ready` (para orquestrador) separado do `/health` (liveness) — o código já está pronto.

**Sem rate limiting.** Os endpoints `/public/*` (incluindo export CSV de observações) são abertos e sem limite — vetor fácil de abuso e custo. Adicione `slowapi` ou limite no reverse proxy.

**Sem observabilidade.** Nenhuma métrica, tracing ou captura de erros (Prometheus/OpenTelemetry/Sentry ausentes). Para uma plataforma de defesa civil, o alerta mais importante é **staleness de dados**: se a ingestão parar silenciosamente, o mapa "parece" normal com dados velhos. Crie métrica/alarme de idade da última observação válida por fonte crítica (o `connectors/health` já dá a base — falta o alarme ativo, não só o painel).

**JWT.** O default `change-this-secret-in-production` deveria derrubar a aplicação na inicialização quando `environment=production`. Falta refresh token e revogação (um `jti` denylist em Redis resolve); 60 min de sessão sem renovação prejudica o operador em plantão.

**Docker Compose incompleto.** O compose só sobe Postgres/Redis/MinIO; API e worker ficam de fora (o `backend/Dockerfile` existe, mas roda uvicorn direto, sem usuário não-root, sem healthcheck, e o CMD não cobre o worker). Redis sem senha, MinIO com credencial padrão, Postgres com senha `meteoro`. Para produção: compose (ou Helm) com api + worker + proxy TLS, credenciais fortes via env, `infra/docker/` hoje está vazio — é o lugar natural desses artefatos.

**Backup.** Scripts existem, mas produção exige agendamento, retenção definida e **teste de restore periódico documentado** no runbook. A pasta `backups/` não deve viver dentro do repositório.

**Higiene do repositório.** `__pycache__` com `.pyc` de Python 3.11/3.12/3.14 e `.ruff_cache`/`.pytest_cache` presentes na árvore; adicione `.ruff_cache/` ao `.gitignore` e limpe. Os `.docx` de especificação na raiz ficariam melhor em `docs/`.

---

## 4. Separação modular

A modularidade é boa, com três ajustes recomendados:

1. **Regras de dependência explícitas.** Módulos importam `models` de outros módulos diretamente (ex.: `meteorology` importa `ObservationModel` e `SourceModel` de `ingestion`/`catalog`). Em monólito modular, a regra saudável é: dependa do `service` (ou de interfaces/schemas) do outro módulo, nunca dos `models`. Adote `import-linter` com contrato de camadas para o CI garantir isso.
2. **`ObservationModel` está no lugar errado.** Observação é o dado central consumido por meteorology, public, data_quality e operations — merece módulo próprio (`observations`) ou um `app/domain` compartilhado, em vez de viver dentro de `ingestion`.
3. **Parsers triplicados.** `ingestion/parsers.py`, `alerts/parsers.py` e `incidents/parsers.py` repetem o padrão "perfil de origem → registros". Um pacote comum de parsing com registro por perfil reduziria manutenção e divergência.

Os módulos vazios (`air_quality`, `health`, `ml`) são aceitáveis como stubs, mas o README deveria distinguir "implementado" de "previsto" para não gerar expectativa falsa em avaliadores/gestores.

---

## 5. Usabilidade e frontend

O portal atual (vanilla JS, página única com seções público/módulos/operação) é honesto para MVP e tem bons sinais de acessibilidade (aria-labels, aria-live, disclaimers claros em linguagem cidadã). Para produção:

**Separar os dois públicos.** Portal público (estático, cacheável, foco em alerta e linguagem simples) e console operacional (SPA com framework — React/Vue —, rotas, gestão de estado e sessão) têm requisitos opostos; hoje dividem um `index.html`. Os ~9 arquivos CSS/JS soltos com `map-fix.css/js` já mostram o limite da abordagem sem build.

**Resiliência offline — crítico para o propósito.** Leaflet e leaflet.heat vêm da CDN unpkg: se a internet do município degradar durante um evento extremo (cenário provável), o mapa operacional morre. Vendorize as bibliotecas (sirva de `/portal`), e evolua o service worker (hoje com 10 linhas) para cache offline real de shell + últimos dados válidos com carimbo de idade.

**Sessão.** O token vive numa variável JS: qualquer reload desloga o operador, não há logout nem aviso de expiração. Como frontend e API são mesma origem, cookie httpOnly + refresh resolve com segurança.

**Parametrização municipal.** `BETIM_REGIONAL_BOUNDS` no backend e `setView([-19.9676, -44.1983])` no frontend estão hardcoded. O multi-tenant já existe (`organization_id`) — mova centro do mapa, bounds regionais e aeródromos de interesse para configuração da organização, tornando a plataforma replicável para outros municípios sem fork.

**Painel com rótulos trocados.** Em `app.js`, os elementos `#runs/#sources/#worker` recebem valores de outra semântica e os rótulos são reescritos via `querySelector` — funciona, mas é frágil; alinhe IDs ao conteúdo real.

---

## 6. Reorganização sugerida

```text
Meteoro/
├── backend/
│   └── app/
│       ├── core/            # settings, security, logging, middleware, health
│       ├── db/
│       ├── domain/          # (novo) modelos compartilhados: observations, sources
│       └── modules/         # api/schemas/service por módulo; models só do próprio domínio
├── frontend/
│   ├── public/              # portal cidadão estático, offline-first
│   └── console/             # SPA operacional (build próprio)
├── infra/
│   ├── docker/              # Dockerfiles api/worker, compose dev e prod, proxy TLS
│   └── observability/       # prometheus, alert rules (staleness!), dashboards
├── docs/                    # incluir os .docx da raiz
└── scripts/
```

## 7. Roadmap de produção em fases

**Fase 0 — Desbloqueio (dias).** Corrigir cadeia Alembic (renumerar + merge + `alembic heads` no CI); rotacionar REDEMET_API_KEY e instituir gestão de segredos; CI verde.

**Fase 1 — Endurecimento (1–2 semanas).** Testes contra PostgreSQL com migrações reais; middleware (logging estruturado + request-id, exception handler, security headers); rate limiting no `/public`; expor `/health/ready`; falha de boot com segredo default em produção; compose completo (api + worker + TLS) com credenciais fortes.

**Fase 2 — Operação confiável (2–4 semanas).** Métricas e alarmes ativos de staleness por fonte crítica; Sentry/OTel; refresh token e revogação; backup agendado com teste de restore; Keycloak homologado em produção; import-linter garantindo contratos modulares.

**Fase 3 — Produto (contínuo).** Console operacional em SPA; portal público offline-first com libs vendorizadas; parametrização municipal completa (multi-município real); evolução dos módulos air_quality/health/ml; melhoria do motor de previsão interno (hoje tendência estatística — integrar pós-processamento de modelos numéricos, ex. Open-Meteo já permitido na allowlist).

---

## 8. Síntese

| Dimensão | Nota | Comentário |
|---|---|---|
| Estrutura | ★★★★☆ | Monólito modular bem aplicado; corrigir posse do ObservationModel e contratos de import |
| Funcionalidades | ★★★★☆ | Pipeline completo ingestão→qualidade→operação→público; previsão interna ainda simples |
| Separação modular | ★★★☆☆ | Boa por convenção, sem enforcement; parsers triplicados |
| Robustez | ★★☆☆☆ | Migrações quebradas, sem observabilidade/rate-limit, testes em banco divergente |
| Usabilidade | ★★★☆☆ | Portal claro e acessível, mas sessão frágil, dependência de CDN e monólito de UI |
| Segurança | ★★★★☆ | Anti-SSRF e auth exemplares; segredo commitado e defaults inseguros derrubam a nota |

O MVP tem fundações sólidas e decisões arquiteturais corretas. Os três bloqueadores da seção 2 são resolvíveis em poucos dias e devem preceder qualquer outra melhoria.
