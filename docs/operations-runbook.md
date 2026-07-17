# Runbook de operação e recuperação

## Sinais de saúde

- `GET /health/live`: o processo HTTP está em execução.
- `GET /health/ready`: banco e armazenamento bruto estão utilizáveis. Redis é reportado separadamente e só torna a API indisponível quando `READINESS_REQUIRE_REDIS=true`.
- Toda resposta inclui `X-Request-ID`. Informe esse identificador ao investigar falhas ou consultar logs.

## Rotina de backup

1. Execute diariamente um backup consistente do PostgreSQL/PostGIS com `pg_dump` em formato custom.
2. Preserve o diretório/objeto de payloads brutos no mesmo ponto de recuperação, sem sobrescrever evidências existentes.
3. Armazene cópias fora do servidor primário, criptografadas e com acesso restrito.
4. Registre data, versão da migração Alembic, checksum e responsável pela execução.

Exemplo para ambiente Docker local:

```bash
docker compose exec -T postgres pg_dump -U meteoro -Fc meteoro > meteoro-$(date +%F).dump
```

## Restauração testada

1. Isole uma base de recuperação; nunca restaure primeiro sobre a produção.
2. Restaure o dump com `pg_restore`, aplique `alembic upgrade head` e restaure o armazenamento bruto correspondente.
3. Compare a versão Alembic, contagens de organizações, fontes, observações, alertas e decisões do Gabinete.
4. Aponte uma instância temporária da API para a base recuperada e valide `/health/ready`.
5. Registre resultado, duração e quaisquer diferenças. Só então autorize uma recuperação produtiva.

## Incidente de dependência

- Banco indisponível: trate `/health/ready` como `503`, suspenda ações de escrita e inicie o procedimento de recuperação.
- Redis indisponível: verifique o worker e a fila. Com Redis opcional, a API pode ficar `degraded`, mas novas coletas assíncronas não devem ser consideradas concluídas.
- Armazenamento bruto indisponível: bloqueie importações e coletas; não descarte a referência de evidência ou tente reprocessar até restaurar o armazenamento.
