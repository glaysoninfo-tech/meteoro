# Produção assistida (indoor) — como subir

Sobe a plataforma completa (API, worker, PostGIS, Redis, MinIO e proxy TLS)
numa única máquina da rede local, sem domínio nem IP público.

## Passo a passo

1. **Segredos**: copie `.env.prod.example` para `.env.prod` nesta pasta e
   preencha todos os `TROQUE_POR_*` (gere com
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`).
   O `.env.prod` nunca é versionado.

2. **Hostname**: edite o `Caddyfile` — troque `meteoro.local` pelo DNS interno
   ou descomente o bloco de IP fixo do servidor.

3. **Suba** (da raiz do repositório):

   ```bash
   docker compose -f infra/docker/compose.prod.yml --env-file infra/docker/.env.prod up -d --build
   ```

   O serviço `migrate` roda `alembic upgrade head` e termina; API e worker só
   iniciam após a migração concluir com sucesso.

4. **Verifique**:

   ```bash
   docker compose -f infra/docker/compose.prod.yml ps
   curl -k https://meteoro.local/health/ready
   ```

5. **Bootstrap do primeiro administrador** (uma única vez):

   ```bash
   curl -k -X POST https://meteoro.local/api/v1/auth/bootstrap-admin \
     -H "Content-Type: application/json" \
     -d '{"name":"...","email":"...","password":"...","organization_name":"..."}'
   ```

   Depois preencha `PUBLIC_ORGANIZATION_ID` no `.env.prod` com o
   `organization_id` criado e reinicie a API:
   `docker compose -f infra/docker/compose.prod.yml up -d api`.

6. **Certificado nas estações**: exporte a CA interna do Caddy e instale nas
   máquinas dos operadores:

   ```bash
   docker compose -f infra/docker/compose.prod.yml cp caddy:/data/caddy/pki/authorities/local/root.crt ./meteoro-ca.crt
   ```

   Instale `meteoro-ca.crt` como autoridade confiável (Windows: certmgr →
   Autoridades de Certificação Raiz Confiáveis).

## Decisões de segurança embutidas

- Só o Caddy expõe portas (80/443); Postgres, Redis, MinIO, API e worker vivem
  em rede interna do compose (`internal: true`).
- Redis com senha e AOF; Postgres e MinIO sem credenciais default.
- Containers rodam como usuário não-root (uid 10001) com healthcheck.
- Logs com rotação (20 MB × 5 arquivos por serviço).
- Boot da API falha se `JWT_SECRET_KEY` for fraco (validação da Etapa 5).
