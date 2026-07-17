# Fontes meteorológicas gratuitas — uso inicial

## Open-Meteo

O endpoint autenticado `GET /api/v1/meteorology/open-meteo/forecast` consulta a
API pública de previsão. A resposta identifica provedor, modelo, horário de
geração, coordenadas e contém o aviso de que a previsão não é observação nem
alerta oficial.

Antes de iniciar a API, libere somente o host exato:

```env
INGESTION_NETWORK_ALLOWED_HOSTS=api.open-meteo.com,archive-api.open-meteo.com,api-redemet.decea.mil.br
```

Exemplo de consulta autenticada:

```text
GET /api/v1/meteorology/open-meteo/forecast?latitude=-19.9167&longitude=-43.9345&forecast_days=3&model=best_match
```

Modelos permitidos no primeiro incremento: `best_match`, `ecmwf_ifs025`,
`gfs_seamless` e `icon_seamless`. O uso em produção depende da validação de
licença/contratação da fonte pela Prefeitura.

## REDEMET

Use apenas uma nova chave, criada após a revogação da chave que foi exposta.
Armazene-a no gerenciador de segredos ou no ambiente de execução:

```env
REDEMET_API_KEY=<nova-chave>
```

Cadastre cada produto REDEMET como fonte HTTP com `authentication_type` igual a
`api_key_env`, sem inserir chave na URL ou no JSON de configuração:

```json
{
  "api_key_header": "X-Api-Key",
  "api_key_env_var": "REDEMET_API_KEY",
  "timeout_seconds": 15,
  "retry_attempts": 3,
  "max_response_bytes": 2097152
}
```

O caminho do endpoint precisa ser definido a partir da documentação oficial do
produto REDEMET escolhido. Ele não foi presumido no código, evitando consultas
erradas ou coleta de dados fora do escopo meteorológico municipal.

## Google Weather API

Não está habilitada no Meteoro operacional. A chave de demonstração é destinada
a prototipagem; a documentação do Google exige faturamento para produção. Assim,
ela não atende ao critério de fonte gratuita operacional atual.

## Regras comuns

- Previsão de modelo, reanálise e observação de estação são classes de dados distintas.
- Nenhum conector pode publicar alerta sem protocolo e aprovação configurados.
- A allowlist de destinos, limites de resposta, timeout, retry e bloqueio de SSRF
  permanecem obrigatórios para todas as fontes.
