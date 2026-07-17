# Rascunhos de migração descartados — 2026-07-16

Estes arquivos foram removidos de `alembic/versions/` por serem rascunhos abandonados que
duplicavam IDs de revisão (quebrando `alembic upgrade head`) e **não correspondem aos modelos atuais**:

- `20260715_0012_recommendation_approval_publication.py` — criava `approved_at_utc`,
  `published_at_utc` e `expires_at_utc` em `recommendation_revisions`. O modelo canônico
  (`app/modules/recommendations/models.py`) usa `approved_at`/`published_at` (sem sufixo `_utc`,
  sem expiração), cobertos pela revisão mantida `20260715_0012_recommendation_publication.py`.
- `20260715_0013_geospatial_visibility.py` — criava coluna `visibility` em `territories` e
  `stations`. A coluna não existe nos modelos e não é referenciada em nenhum service/api.

Se a feature de visibilidade geoespacial for retomada, crie uma NOVA revisão com
`alembic revision` (ID gerado automaticamente) em vez de restaurar este arquivo.

Esta pasta não é lida pelo Alembic e pode ser apagada quando não for mais útil como referência.
