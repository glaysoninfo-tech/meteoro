# Backup e Restore — Meteoro (produção assistida)

## Política

| Item | Valor |
|---|---|
| Frequência | Diária, `BACKUP_HOUR_UTC` (padrão 02:00 UTC) + um backup na subida do serviço |
| Conteúdo | Dump PostgreSQL (formato custom) + tar dos payloads brutos (`/data/raw`) |
| Integridade | SHA-256 gravado ao lado de cada arquivo |
| Retenção | `BACKUP_RETENTION_DAYS` (padrão 30 dias), poda automática |
| Destino | `BACKUP_DIR` no host — **obrigatoriamente disco secundário ou NAS**, nunca o disco do banco |
| Ensaio de restore | **Mensal**, registrado na tabela de evidências abaixo |

O serviço `backup` do `compose.prod.yml` executa tudo automaticamente; os logs
saem em `docker compose -f infra/docker/compose.prod.yml logs backup`.

## O que NÃO está coberto (decidir antes do piloto)

- **MinIO**: se object storage entrar em uso real, adicionar `mc mirror` ao ciclo.
- **Cópia externa (off-site)**: a política 3-2-1 pede uma cópia fora do prédio —
  avaliar rotação de HD externo ou NAS de outro órgão municipal.

## Restore de verificação (ensaio mensal)

Nunca restaure sobre o banco de produção. O ensaio usa um banco de teste:

```bash
# 1. Escolha o backup mais recente
ls -lt ${BACKUP_DIR:-infra/docker/backups}/meteoro_*.dump | head -1

# 2. Confira a integridade
cd ${BACKUP_DIR:-infra/docker/backups} && sha256sum -c meteoro_<STAMP>.dump.sha256

# 3. Restaure num banco de teste dentro do próprio postgres do compose
docker compose -f infra/docker/compose.prod.yml exec -T postgres \
  psql -U meteoro -d postgres -c "DROP DATABASE IF EXISTS meteoro_drill; CREATE DATABASE meteoro_drill;"
docker compose -f infra/docker/compose.prod.yml exec -T postgres \
  pg_restore --exit-on-error --no-owner --no-privileges -U meteoro -d meteoro_drill \
  < ${BACKUP_DIR:-infra/docker/backups}/meteoro_<STAMP>.dump

# 4. Valide o conteúdo (contagens mínimas)
docker compose -f infra/docker/compose.prod.yml exec -T postgres \
  psql -U meteoro -d meteoro_drill -c \
  "SELECT (SELECT count(*) FROM observations) AS observacoes,
          (SELECT count(*) FROM sources) AS fontes,
          (SELECT count(*) FROM users) AS usuarios,
          (SELECT version_num FROM alembic_version) AS migracao;"

# 5. Limpe
docker compose -f infra/docker/compose.prod.yml exec -T postgres \
  psql -U meteoro -d postgres -c "DROP DATABASE meteoro_drill;"
```

**Critérios de aprovação do ensaio:** hash confere; `pg_restore` sem erro;
contagens coerentes com a produção; `alembic_version` presente e igual ao head.

Para restaurar payloads brutos: `tar -xzf raw_<STAMP>.tar.gz -C <destino>`.

## Desastre real (perda do banco de produção)

1. Suba um postgres vazio (`docker compose up -d postgres`).
2. Restaure o dump mais recente no banco `meteoro` (mesmos comandos, alvo `meteoro`).
3. Restaure `/data/raw` a partir do tar no volume `raw-data`.
4. Suba o restante (`up -d`) — o serviço `migrate` aplicará migrações pendentes
   se o dump for anterior ao código.
5. Valide `/health/ready` e o login de um operador.

## Registro de ensaios (evidência)

| Data | Backup usado | Resultado | Responsável | Observações |
|---|---|---|---|---|
| _preencher no primeiro ensaio_ | | | | |

## Ambiente de desenvolvimento (SQLite)

O banco local `backend/meteoro_local.db` é descartável: recriável com
`alembic upgrade head` + `python -m scripts.seed_demo`. Para preservar um
estado específico, basta copiar o arquivo com o uvicorn parado.
