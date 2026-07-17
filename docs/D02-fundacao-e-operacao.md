# D02 — Arquitetura e fundação

## Implementado no repositório

| Item | Implementação | Como verificar |
| --- | --- | --- |
| Arquitetura | C4 e ADRs em `docs/architecture/c4-e-adrs.md` | revisão arquitetural |
| Banco | PostgreSQL/PostGIS, Alembic e migrações versionadas | `alembic upgrade head` |
| Ambientes | Compose para API, worker, PostgreSQL, Redis e MinIO | `docker compose up -d --build` |
| CI | lint, migração PostGIS e testes em GitHub Actions | workflow `.github/workflows/ci.yml` |
| Identidade | JWT local/Keycloak, RBAC e trilha de login | endpoints `/api/v1/auth/*` |
| Logs/auditoria | módulo audit com registro de operações governadas | `/api/v1/audit/*` conforme perfil |
| Segredos | variáveis em `.env`, arquivo ignorado e Compose sem senha fixa | `cp .env.example .env` e preencher valores |
| Backup | scripts de dump/restauração e roteiro de exercício | `scripts/backup_postgres.sh` e `restore_postgres.sh` |

## Inicialização local controlada

```bash
cd Meteoro
cp .env.example .env
# Troque todas as senhas e JWT_SECRET_KEY antes de qualquer ambiente compartilhado.
docker compose up -d --build
docker compose exec api alembic upgrade head
```

O portal fica em `http://localhost:8000/portal/` e a documentação OpenAPI em `http://localhost:8000/docs`.

## Rotina de backup e restauração

```bash
cd Meteoro
./scripts/backup_postgres.sh
./scripts/restore_postgres.sh backups/arquivo.dump meteoro_restore_test
```

A restauração deve ocorrer em banco de teste separado. Registre data, operador, arquivo, hash, duração, resultado e eventual divergência em uma ata de exercício. Um script disponível não substitui a evidência de restauração executada.

## Aceite pendente de ambiente

- Criar repositório municipal e habilitar o workflow de CI.
- Configurar gerenciador de segredos do ambiente de produção; `.env` é apenas mecanismo local.
- Executar backup e restauração de homologação, anexando a evidência institucional.
- Definir RPO/RTO, retenção e destino externo criptografado para cópias.
- Centralizar logs/métricas em ferramenta municipal e configurar alertas de disponibilidade.
