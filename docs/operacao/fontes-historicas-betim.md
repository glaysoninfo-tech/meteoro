# Fontes históricas e rotina automática — Betim

## Regra de classificação

O METEORO não apresenta todas as séries como se tivessem a mesma certeza.

| Produto | Natureza no sistema | Uso permitido |
| --- | --- | --- |
| Estação automática INMET próxima | observação regional | contexto meteorológico e comparação; não representa um bairro de Betim |
| BDMEP/INMET | observação histórica diária | climatologia, percentis, anomalias e estudos retrospectivos |
| Pluviômetro Cemaden | observação instrumental | risco hidrológico após confirmar estação, licença e município |
| MonitorAr/FEAM | observação instrumental de qualidade do ar | IQAr e séries; somente com endpoint ou exportação oficial homologada |
| Open-Meteo | estimativa/previsão de modelo | continuidade horária e cenário; nunca "estação de Betim" |

## Fontes verificadas

1. **INMET**: as estações automáticas possuem atualização horária para os últimos 90 dias; o portal disponibiliza mapa/tabela de estações. O BDMEP contém séries históricas diárias de estações convencionais e mantém dados digitalizados desde 1961. Fontes: [estações automáticas](https://portal.inmet.gov.br/servicos/esta%C3%A7%C3%B5es-autom%C3%A1ticas), [BDMEP](https://portal.inmet.gov.br/servicos/bdmep-dados-hist%C3%B3ricos) e [orientação de acesso](https://portal.inmet.gov.br/noticias/saiba-como-acessar-os-dados-meteorol%C3%B3gicos-dispon%C3%ADveis-no-site-do-inmet).
2. **Cemaden**: o Mapa Interativo disponibiliza localização e download de séries de pluviômetros por UF/município/mês. O fluxo atual envia link por e-mail e contém confirmação de segurança; portanto é um conector assistido/manual até que o Cemaden forneça uma interface de máquina homologada. Fonte: [Mapa Interativo](https://mapainterativo.cemaden.gov.br/).
3. **Qualidade do ar em Minas**: o boletim estadual divulga IQAr calculado a partir de estações automáticas e contínuas. O conector MonitorAr/FEAM já existe no METEORO, mas só deve ser ativado com endpoint oficial documentado ou exportação autorizada. Fonte: [serviço estadual](https://www.mg.gov.br/servico/acessar-boletim-da-qualidade-do-ar).
4. **Open-Meteo**: fonte aberta complementar para estimativa e previsão de ponto para Betim. É configurada como modelo, não como observação.

## Perfil automático disponível agora

Cadastre a fonte abaixo uma vez, em **Catálogo de fontes**. A allowlist precisa conter `api.open-meteo.com` (já exemplificada em `.env.example`). O `schedule.minute_utc: 5` dispara às `HH:05 UTC`, uma vez por hora; a primeira coleta de uma fonte nova ocorre de imediato.

```json
{
  "institution_name": "Open-Meteo",
  "source_name": "Betim — estimativa e previsão horária de modelo",
  "source_type": "meteorology_model",
  "access_method": "http",
  "authentication_type": "none",
  "endpoint_reference": "https://api.open-meteo.com/v1/forecast?latitude=-19.9676&longitude=-44.1983&hourly=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m&timezone=UTC&past_days=1&forecast_days=1",
  "connector_config_json": "{\"parser\":\"open_meteo\",\"station_code\":\"BETIM_MODEL_POINT\",\"schedule\":{\"minute_utc\":5}}",
  "status": "active",
  "expected_frequency_minutes": 60,
  "criticality": "low"
}
```

Para recuperação histórica do modelo, cadastre a fonte separada abaixo. Ela permanece **ativa** para permitir reprocessamento manual, mas `schedule.enabled:false` impede qualquer coleta automática.

```json
{
  "institution_name": "Open-Meteo",
  "source_name": "Betim — histórico de modelo para reprocessamento",
  "source_type": "meteorology_model_historical",
  "access_method": "http",
  "authentication_type": "none",
  "endpoint_reference": "https://archive-api.open-meteo.com/v1/archive?latitude=-19.9676&longitude=-44.1983&hourly=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m&timezone=UTC",
  "connector_config_json": "{\"parser\":\"open_meteo\",\"station_code\":\"BETIM_MODEL_POINT\",\"schedule\":{\"enabled\":false},\"reprocess\":{\"start_query_param\":\"start_date\",\"end_query_param\":\"end_date\"}}",
  "status": "active",
  "expected_frequency_minutes": 1440,
  "criticality": "low"
}
```

## Operação pelo ADM

1. Verifique a saúde em `GET /api/v1/ingestion/connectors/health`.
2. Para executar agora, use `POST /api/v1/ingestion/jobs/collect/source/{source_id}`; acompanhe em `GET /api/v1/ingestion/jobs/{job_id}`.
3. Para atualizar automaticamente, execute o worker separado com `INGESTION_SCHEDULER_ENABLED=true`: `python -m app.modules.ingestion.worker`.
4. Para recuperar uma janela, use `POST /api/v1/ingestion/runs/reprocess` com `source_id`, `period_start_utc` e `period_end_utc`. A chave de observação e o hash do payload impedem duplicidade.

## Contexto regional e interpolação responsável

O ADM instala os doze pontos regionais solicitados com uma única chamada autenticada:

```http
POST /api/v1/catalog/sources/profiles/regional-context
```

Os pontos são Belo Horizonte, Contagem, Pará de Minas, Brumadinho, Divinópolis, Igarapé, Ibirité, Sarzedo, Mário Campos, Esmeraldas, Juatuba e São Joaquim de Bicas. As coletas são escalonadas entre `HH:06` e `HH:17 UTC`; cada fonte preserva município, coordenada, método e horário próprios.

Eles servem para leitura de gradiente e coerência regional. Uma futura superfície interpolada deverá declarar método, raio/distância, fontes válidas, horário e incerteza. Ela é proibida de substituir uma observação instrumental local, de validar sozinha um alerta oficial ou de afirmar condição em bairro sem cobertura suficiente.

## Pendências de homologação

- Confirmar quais estações INMET, Cemaden e FEAM têm cobertura útil para Betim, identificador externo, responsável e licença.
- Registrar endpoint oficial de máquina, frequência e limites de cada uma antes de ativar coleta automática.
- Não usar páginas protegidas por CAPTCHA, nem simular interface humana como integração. Enquanto isso, importar exportações oficiais pelo endpoint de arquivo preservando o payload bruto.
