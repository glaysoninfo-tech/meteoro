# Plano Incremental — MVP → Produção Assistida (indoor, sem domínio/IP público)

Cenário-alvo: plataforma rodando em servidor local (LAN da prefeitura/órgão), acessada por operadores autorizados, com operação assistida e critérios de aceite antes de qualquer exposição pública futura.

Regras do plano: cada etapa é pequena, tem **critério de "pronto"** verificável e deixa o sistema funcionando. Nunca avance com o CI vermelho. Uma etapa = um PR.

---

## STATUS DE EXECUÇÃO (atualizado em 18/07/2026)

| Bloco | Etapas | Status |
|---|---|---|
| A — Sanear a base | 1 a 4 | ✅ concluído |
| B — Endurecer a aplicação | 5 a 8 | ✅ concluído |
| C — Empacotar para indoor | 9, 10b, 11 | ✅ código pronto; **Etapa 10 (LAN/TLS físico) e ensaio do compose pendentes de execução no servidor** |
| D — Operação assistida | 12 | ✅ observabilidade; 13 e 14 documentadas em `docs/operations/` |
| E — Evolução estrutural | 15 a 17 | ⏳ pós-piloto |

**Entregas além do plano original** (surgidas do uso real): portal navegável por
rotas religado, superfície pública completa (resumo diário, condições, previsão,
mapa da cidade), visão executiva do Gabinete com fila de prioridades, endpoints
de decisões do Gabinete, conector ANA HidroWeb (nível d'água), estações INMET
regionais, território oficial IBGE, pontos de monitoramento com acumulados e
tendência de nível, canal público de denúncia SEMMAD, camadas ANA/CEMADEN/PBH,
limiares de cheia urbana e diagnóstico da rede hidrometeorológica municipal.

**Documentos operacionais finais:**
- `docs/operations/checklist-diario-operador.md` (Etapa 13)
- `docs/operations/protocolo-piloto-assistido.md` (Etapa 14)
- `docs/operations/backup-e-restore.md` (Etapa 11)
- `docs/operacao/rede-hidrometeorologica-municipal.md` (diagnóstico de dados)
- `docs/security/gestao-de-segredos.md` (Etapa 2)
- `infra/docker/README.md` (Etapas 9 e 10)

**Pendências para o go-live indoor:** ensaiar `compose.prod.yml` numa máquina
com Docker, definir IP fixo/hostname e firewall, distribuir a CA interna,
executar o primeiro restore de ensaio e configurar o canal de alertas no
Alertmanager.

---

## BLOCO A — Sanear a base (semana 1)

### Etapa 1 — Consertar a cadeia de migrações Alembic ⚠️ bloqueador
**Ações:**
1. Renumerar os IDs duplicados: `20260715_0012_recommendation_publication.py` → novo ID único; `20260715_0013_incident_geolocation.py` → novo ID único; reencadear `down_revision` para formar cadeia linear.
2. Integrar o head órfão `20260714_0012_cabinet_decisions` à cadeia (reencadear ou criar *merge revision* com `alembic merge`).
3. Banco local de teste do zero: `alembic upgrade head` completo em PostGIS.
4. Guard no CI: passo que falha se `alembic heads` retornar mais de 1 linha.
5. Daqui em diante, gerar IDs com `alembic revision` (hash automático) — abandonar numeração manual.

**Pronto quando:** `alembic upgrade head` roda limpo em PostGIS vazio; `pytest tests/test_migrations.py` verde; CI com guard de head único.

### Etapa 2 — Rotacionar segredo e instituir gestão de segredos ⚠️ bloqueador
**Ações:**
1. Rotacionar a `REDEMET_API_KEY` no portal da REDEMET (a atual está exposta em `backend/.env`).
2. Remover valores reais de qualquer arquivo do repositório; manter apenas `.env.example` com placeholders.
3. Se o repo git já registrou o `.env` em algum commit: reescrever histórico (`git filter-repo`) ou considerar a chave definitivamente queimada.
4. Adicionar `gitleaks` (ou `detect-secrets`) como passo do CI.
5. Definir onde os segredos vivem no servidor indoor: arquivo `.env` fora do repositório, permissão 600, dono do serviço — documentar em `docs/security/`.

**Pronto quando:** nenhum segredo real no repo; CI bloqueia novos vazamentos; chave antiga revogada.

### Etapa 3 — Higiene do repositório
**Ações:** remover `__pycache__` (há .pyc de Python 3.11/3.12/3.14), `.pytest_cache`, `.ruff_cache` versionados; adicionar `.ruff_cache/` e `backups/` ao `.gitignore`; mover os três `.docx` da raiz para `docs/especificacao/`; atualizar README distinguindo módulos **implementados** × **previstos** (air_quality, health, ml são stubs).

**Pronto quando:** `git status` limpo após clone + build; README fiel ao estado real.

### Etapa 4 — Testes contra o banco real
**Ações:**
1. No CI, apontar a suíte para o PostgreSQL/PostGIS do serviço já existente no workflow; preparar o schema com `alembic upgrade head` (não `create_all`).
2. Manter SQLite apenas para testes unitários rápidos locais (marcador pytest `@pytest.mark.unit`).
3. Corrigir divergências que aparecerem (tipos JSON, constraints, geoespacial) — esta etapa existe justamente para revelá-las.

**Pronto quando:** suíte completa verde em PostGIS no CI; smoke local documentado (`docker compose up -d && alembic upgrade head && pytest`).

---

## BLOCO B — Endurecer a aplicação (semanas 2–3)

### Etapa 5 — Boot seguro e endpoints de saúde
**Ações:**
1. Validador em `Settings`: se `environment=production` e `jwt_secret_key` for o default (ou < 32 chars), a aplicação **não sobe**.
2. Expor o `readiness_report()` já pronto em `app/core/health.py` como `GET /health/ready` (hoje é código morto); manter `/health` como liveness simples.
3. Condicionar `docs_url`/`redoc_url` a `environment != "production"`.

**Pronto quando:** subir com segredo default em production falha com mensagem clara; `/health/ready` reporta database/storage/redis; testes cobrindo os três comportamentos.

### Etapa 6 — Middleware de produção
**Ações:**
1. Logging estruturado JSON com request-id (middleware que gera/propaga `X-Request-ID`), incluindo usuário e organização quando autenticado; mesmo formato no worker.
2. Exception handler global com envelope de erro padronizado (`{"detail", "request_id"}`) — nunca stacktrace ao cliente.
3. Security headers (X-Content-Type-Options, X-Frame-Options, Referrer-Policy; CSP no portal) e GZipMiddleware.

**Pronto quando:** toda resposta carrega `X-Request-ID`; erro 500 simulado retorna envelope limpo e loga stacktrace com o mesmo id; headers verificados por teste.

### Etapa 7 — Rate limiting e proteção do /public
**Ações:** `slowapi` (ou equivalente) com limites por IP nos endpoints `/public/*`, mais restritivo no CSV de observações; paginação obrigatória com teto de linhas no export; log de excedentes.

**Pronto quando:** exceder o limite retorna 429 com `Retry-After`; teste automatizado cobre o caso.

### Etapa 8 — Sessão do operador (refresh + revogação)
**Ações:**
1. Refresh token com rotação; access token curto (15 min) + refresh (8 h de plantão).
2. Revogação via denylist de `jti` no Redis; endpoint de logout.
3. Portal: como frontend e API são mesma origem, migrar o token de variável JS para cookie httpOnly/SameSite=Strict — reload deixa de derrubar a sessão do operador.

**Pronto quando:** operador sobrevive a reload; logout revoga; token revogado é rejeitado (teste).

---

## BLOCO C — Empacotar para rodar indoor (semanas 3–4)

### Etapa 9 — Compose de produção completo
**Ações:**
1. Melhorar `backend/Dockerfile`: usuário não-root, `HEALTHCHECK`, multi-stage; criar entrada para o **worker** (mesma imagem, comando distinto).
2. Criar `infra/docker/compose.prod.yml` (a pasta está vazia): `api` + `worker` + `postgres` + `redis` + `minio` + proxy reverso (Caddy ou Nginx).
3. Senhas fortes vindas de `.env` externo (Etapa 2); Redis com `requirepass`; MinIO sem credencial default; Postgres sem porta exposta ao host (rede interna do compose); volumes nomeados com caminho de dados definido.
4. `restart: unless-stopped` em tudo; limites de memória; logs com rotação (`max-size`).

**Pronto quando:** `docker compose -f infra/docker/compose.prod.yml up -d` sobe o sistema completo numa máquina limpa; `/health/ready` verde; worker processando fila.

### Etapa 10 — Acesso na LAN e TLS interno
**Ações:**
1. Servidor com IP fixo na LAN; proxy escutando 443.
2. TLS com CA interna (mkcert para poucas máquinas, ou CA da própria organização); distribuir o certificado raiz nas estações dos operadores. Se optar por HTTP puro em VLAN isolada, registrar a decisão e o prazo em `docs/security/` como exceção formal.
3. Firewall do host: somente 443 (e 22 restrito à equipe de TI); serviços de dados inacessíveis fora do host.
4. Restringir acesso por segmento de rede/VPN interna dos operadores.

**Pronto quando:** operadores acessam `https://meteoro.local` (ou IP) sem aviso de certificado; `nmap` externo ao host mostra apenas 443/22.

### Etapa 10b — Portal resiliente para operação indoor
Crítico para o propósito: numa emergência, a internet do município pode degradar — o console operacional não pode depender de CDN externa.

**Ações:**
1. Vendorizar Leaflet e leaflet.heat: baixar e servir de `/portal/vendor/` (remover unpkg do `index.html`); fixar versões e registrar hashes.
2. Evoluir o service worker (hoje 10 linhas): cache do shell (HTML/CSS/JS/vendor) + últimos dados válidos com carimbo de idade visível ("dados de HH:MM") quando offline.
3. Corrigir os rótulos trocados do painel em `app.js`: `#runs/#sources/#worker` recebem valores de outra semântica e os textos são reescritos via `querySelector` — alinhar IDs ao conteúdo real.

**Pronto quando:** com a saída de internet do servidor bloqueada, o portal carrega completo na LAN, mapa funcional, e exibe a idade dos últimos dados; nenhum request a domínio externo no DevTools.

### Etapa 11 — Backup automatizado com restore comprovado
**Ações:**
1. Agendar `scripts/backup_postgres.sh` (cron ou container sidecar) — diário, retenção 30 dias, destino fora do host (NAS/disco secundário).
2. Incluir `data/raw` (payloads brutos) e volume do MinIO no ciclo.
3. **Ensaio de restore**: restaurar num ambiente limpo e validar com checklist; agendar reensaio mensal no runbook.

**Pronto quando:** backup roda sozinho; um restore completo foi executado e documentado com data e responsável.

---

## BLOCO D — Operação assistida (semanas 4–6)

### Etapa 12 — Observabilidade mínima viável
**Ações:**
1. Métricas Prometheus na API e no worker (`/metrics` protegido): latência, erros, fila Redis, e a métrica mais importante — **idade da última observação válida por fonte crítica** (staleness).
2. Grafana + Alertmanager (ou Uptime Kuma, mais simples) no mesmo compose; alertas para: ingestão parada > X min, `/health/ready` degradado, disco > 80%, backup ausente > 24 h.
3. Canal de alerta que a equipe realmente vê (e-mail institucional/Telegram interno).

**Pronto quando:** desligar o worker de propósito dispara alerta em minutos; dashboard mostra staleness por fonte.

### Etapa 13 — Preparação operacional
**Ações:**
1. Seed de produção: organização real, usuários nominais com perfis mínimos (nada de admin compartilhado), fontes homologadas na allowlist.
2. Atualizar `docs/operations-runbook.md` para o ambiente indoor: como subir/derrubar, ler logs, agir em cada alerta, contatos.
3. Checklist diário do operador (5 min): `/health/ready`, staleness, filas de qualidade/triagem/protocolos, backup da noite.
4. Treinar os operadores usando a trilha já existente em `docs/training/`.

**Pronto quando:** dois operadores executam o checklist sem ajuda do desenvolvedor; runbook validado por alguém que não escreveu o código.

### Etapa 14 — Piloto assistido (go-live indoor)
**Ações:**
1. Período de sombra de 2–4 semanas: sistema opera de verdade, decisões oficiais ainda seguem o fluxo antigo em paralelo.
2. Registrar toda ocorrência (bug, dado errado, dúvida de operador) como issue; revisão semanal.
3. Critérios de aceite ao final: disponibilidade ≥ 99% no horário operacional, zero perda de dados ingeridos, staleness dentro do limite por fonte, backup + restore ensaiado, operadores autônomos.
4. Reunião de go/no-go documentada.

**Pronto quando:** critérios atingidos e aceite formal registrado — plataforma em produção assistida.

---

## BLOCO E — Evolução estrutural (durante/após o piloto, não bloqueia o go-live indoor)

Refatorações da avaliação (seções 4–6) que melhoram manutenibilidade e replicabilidade. Podem rodar em paralelo ao piloto assistido, uma por vez, sempre com a suíte verde.

### Etapa 15 — Contratos modulares garantidos
**Ações:**
1. Adotar `import-linter` com contrato: módulo depende de `service`/`schemas` de outro módulo, nunca de `models` (hoje `meteorology` importa `ObservationModel`/`SourceModel` de `ingestion`/`catalog` diretamente); rodar no CI.
2. Extrair `ObservationModel` (e avaliar `SourceModel`) para `app/domain/` ou módulo `observations` — é o dado central consumido por meteorology, public, data_quality e operations; migração Alembic sem mudança de schema (só reorganização de código).
3. Unificar os três `parsers.py` (ingestion, alerts, incidents) num pacote comum de parsing com registro por perfil de origem.

**Pronto quando:** `import-linter` verde no CI; zero imports de `models` entre módulos; um único ponto de registro de parsers.

### Etapa 16 — Parametrização municipal (multi-tenant real)
**Ações:** mover `BETIM_REGIONAL_BOUNDS` (backend) e `setView([-19.9676, -44.1983])` (frontend) para configuração da organização: centro do mapa, bounds regionais e aeródromos de interesse por `organization_id`, com endpoint de configuração consumido pelo portal.

**Pronto quando:** implantar para um segundo município exige apenas cadastro, sem alteração de código.

### Etapa 17 — Separação portal público × console operacional
**Ações:**
1. Dividir `frontend/` em `frontend/public/` (portal cidadão estático, cacheável, offline-first, linguagem simples) e `frontend/console/` (SPA operacional — React ou Vue — com rotas, gestão de estado e sessão), consolidando os ~9 arquivos CSS/JS soltos (`map-fix.css/js` etc.) num build próprio.
2. Migrar as telas operacionais existentes preservando acessibilidade (aria-labels, aria-live) e disclaimers.

**Pronto quando:** dois artefatos independentes servidos pelo proxy; console com build reproduzível; portal público funciona sem JavaScript de console.

## Fora do escopo agora (pré-requisitos da fase pública futura)
Domínio + TLS público (Let's Encrypt), Keycloak em produção, WAF/CDN, exposição do portal cidadão à internet, LGPD/termo de publicação de dados abertos, teste de carga externo. Só iniciar após estabilidade comprovada na produção assistida.

## Sequência resumida
```
A1 migrações → A2 segredos → A3 higiene → A4 testes PostGIS
→ B5 boot/ready → B6 middleware → B7 rate limit → B8 sessão
→ C9 compose prod → C10 LAN/TLS → C10b portal offline → C11 backup+restore
→ D12 observabilidade → D13 preparação → D14 piloto assistido ✅
   (em paralelo ao piloto) E15 contratos modulares → E16 parametrização → E17 público×console
```
Esforço estimado: 5–6 semanas com 1 desenvolvedor até o piloto (D14); Bloco E soma ~3–4 semanas e pode correr em paralelo. Blocos B e C podem andar em paralelo com 2 pessoas.
