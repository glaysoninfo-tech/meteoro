# Gestão de Segredos — Meteoro

Política mínima para desenvolvimento e produção assistida (indoor). Vigente a partir de 2026-07-16.

## Regras

1. **Nenhum segredo entra no repositório.** Arquivos `.env` estão no `.gitignore`; somente `.env.example` (com placeholders vazios) é versionado. O CI roda `gitleaks` em todo push/PR e falha se detectar credencial.
2. **Segredos vivem em variáveis de ambiente**, carregadas de um `.env` local que nunca é compartilhado, anexado a chats/e-mails ou copiado para documentação. No servidor indoor: arquivo em `/etc/meteoro/.env` (ou equivalente), permissão `600`, dono = usuário de serviço da aplicação.
3. **Rotação imediata em caso de exposição.** Qualquer chave que apareça em texto plano fora do `.env` local (commit, chat, print, documento) é considerada queimada e deve ser rotacionada no provedor no mesmo dia.
4. **Um segredo por finalidade.** Não reutilizar a mesma chave/senha entre serviços (banco, Redis, MinIO, APIs externas). Em produção assistida, todas as senhas default do `docker-compose` devem ser substituídas por valores fortes e únicos.
5. **`endpoint_reference` do Catálogo de fontes nunca contém chave.** Conectores referenciam a variável de ambiente pelo nome (`api_key_env_var`), nunca o valor.

## Inventário de segredos da plataforma

| Segredo | Onde é usado | Rotação |
|---|---|---|
| `JWT_SECRET_KEY` | Assinatura de tokens locais da API | A cada exposição ou 12 meses; invalida sessões ativas |
| `REDEMET_API_KEY` | Conectores REDEMET/DECEA (via `api_key_env_var`) | Portal REDEMET |
| `DATABASE_URL` (senha) | PostgreSQL/PostGIS | `ALTER ROLE ... PASSWORD` + atualizar `.env` |
| `REDIS_URL` (senha, produção) | Fila do worker | `requirepass` + atualizar `.env` |
| Credenciais MinIO | Object storage | Console/`mc admin` |
| Credenciais Keycloak (futuro) | Modo `keycloak`/`hybrid` | Admin do realm |

## Registro de incidentes de exposição

| Data | Segredo | Ocorrido | Ação |
|---|---|---|---|
| 2026-07-16 | `REDEMET_API_KEY` | Presente em `backend/.env` dentro da pasta do projeto (sem histórico git; pasta não versionada) e citada em análise externa | Rotação solicitada ao titular; gitleaks adicionado ao CI |

## Checklist antes do primeiro `git init`/push

- [ ] `git init` só após confirmar que `.gitignore` cobre `.env`, `.env.*`, `*.db` e `data/`
- [ ] Rodar `gitleaks detect --source .` localmente antes do primeiro commit
- [ ] Conferir que `backend/.env` e backups `*.db.bak-*` não aparecem em `git status`
