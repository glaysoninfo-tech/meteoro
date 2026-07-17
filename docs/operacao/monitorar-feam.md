# Conector MonitorAr / FEAM — rotina do administrador

## Objetivo

Importar leituras de qualidade do ar identificáveis por estação, preservando o
arquivo/resposta original, o horário de coleta e o código de estação. O conector
aceita JSON, CSV e GeoJSON publicados por endereço oficial homologado.

## Antes de ativar

1. Confirme com FEAM/SEMAD ou MMA qual URL oficial pode ser consumida por
   máquina e quais campos ela entrega.
2. Confirme que o produto identifica a estação e contém horário da leitura.
3. Inclua somente o domínio aprovado em `INGESTION_NETWORK_ALLOWED_HOSTS` e
   mantenha `https` como esquema permitido.
4. Cadastre no METEORO a estação e seus sensores; registre o código externo da
   estação no campo `station_code`.
5. Não use a página interativa do MonitorAr como endpoint do worker. Ela é uma
   interface de consulta e pode aplicar proteção contra automação.

## Cadastro da fonte

No módulo Administração → Fontes, crie uma fonte com os seguintes valores:

```json
{
  "institution_name": "MonitorAr / FEAM",
  "source_name": "Leituras oficiais de qualidade do ar — Alterosa",
  "source_type": "air_quality",
  "access_method": "http",
  "authentication_type": "none",
  "endpoint_reference": "https://<dominio-oficial-homologado>/arquivo-ou-api",
  "connector_config_json": "{\"parser\":\"monitorar_feam\"}",
  "status": "active",
  "expected_frequency_minutes": 60,
  "criticality": "high"
}
```

Vincule `station_id` e, quando a origem entregar apenas uma variável, também
`sensor_id`. Para Centro Administrativo Betim e Petrovale, crie fontes próprias
quando os identificadores externos e URLs oficiais forem confirmados.

## Execução e conferência

1. Execute **Coletar agora** na fonte cadastrada.
2. Confira o resultado na Saúde de fontes: duração, hash do payload, quantidade
   de observações, última coleta e última observação.
3. Confira a estação: uma leitura ausente deve permanecer ausente; o sistema não
   substitui indisponibilidade por zero.
4. Se a estrutura do arquivo mudar ou o domínio falhar, a fonte ficará degradada
   e o payload anterior continuará auditável.
5. Após o teste manual aprovado, habilite o worker. A frequência da fonte é o
   teto para avaliar atraso e saúde operacional.

## Campos reconhecidos

O parser reconhece códigos ou nomes de estação como `codigo_estacao`,
`station_code`, `estacao` e `nome_estacao`; horário como `data_hora`,
`timestamp` ou `observed_at`; e os poluentes PM₂,₅, PM₁₀, O₃, NO₂, SO₂ e CO.
Também aceita produto GeoJSON com valores em `features[].properties`.

## Limite da homologação atual

O MonitorAr informa que a consulta pública permite procurar estações, histórico
e mapas, mas não disponibiliza nesta etapa um endpoint público, versionado e
documentado para uso pelo worker. Portanto o conector está pronto para receber
um endpoint oficial autorizado; ele não deve contornar proteção da página web.
