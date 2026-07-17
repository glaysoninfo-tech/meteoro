# Uso das APIs

A especificação interativa está em `/docs` (OpenAPI) e a versão da API é explícita em `/api/v1`.

## API pública

Não requer token quando `PUBLIC_ORGANIZATION_ID` estiver configurado.

```text
GET /api/v1/public/situation
GET /api/v1/public/alerts
GET /api/v1/public/recommendations
GET /api/v1/public/stations
GET /api/v1/public/open-data/observations?limit=500&offset=0
GET /api/v1/public/open-data/observations.csv
```

O conjunto aberto contém somente observações de estações classificadas como públicas e com qualidade `valid`. O CSV usa UTF-8 e possui os campos `observed_at_utc`, `station_id`, `station_code`, `variable_code`, `value`, `unit` e `quality_status`.

## API operacional

Requer `Authorization: Bearer <token>`.

```text
GET /api/v1/geospatial/stations/{station_id}/health
GET /api/v1/ingestion/connectors/health
GET /api/v1/data-quality/issues
GET /api/v1/incidents/reports
GET /api/v1/incidents/cases
GET /api/v1/audit/events
```

Exemplo de paginação aberta:

```text
GET /api/v1/public/open-data/observations?limit=500&offset=1000
```

Respostas incluem `limit`, `offset` e `total`. Clientes devem avançar o `offset` até receberem todos os registros, respeitando os limites publicados. Não use a API pública para inferir dados não publicados: registros internos, restritos, sensíveis, suspeitos ou rejeitados são bloqueados da exportação.
