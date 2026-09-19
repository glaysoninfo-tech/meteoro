# Checklist Diário do Operador — METEORO

Rotina de 5 a 10 minutos, no início de cada turno. Marque o que verificou e
registre pendências no campo de observações do turno.

## 1. Plataforma no ar (1 min)

- [ ] Portal abre em `https://meteoro.local/portal` **sem banner vermelho** no topo
- [ ] `https://meteoro.local/health/ready` responde `"status": "ready"`
      (se `degraded`, ver qual componente está `unavailable`)
- [ ] Login funciona e a sessão permanece após atualizar a página

> Banner vermelho = API fora do ar. Ação: verificar containers
> (`docker compose -f infra/docker/compose.prod.yml ps`) e, se necessário,
> `up -d`. Persistindo, acionar o suporte técnico.

## 2. Coleta de dados viva (2 min)

Na rota **Visão geral**, confira o cartão *fontes operacionais* (formato N/N):

- [ ] Nenhuma fonte **crítica** com coleta atrasada na lista de PRIORIDADES
- [ ] Worker ativo — sem o aviso "fila Redis indisponível"
- [ ] Na rota **Monitoramento**, os pontos do mapa mostram medições recentes
      (clicar em 1 estação e conferir o horário da medição)

> Fonte parada > 2 h: o alarme `FonteCriticaParada` já terá disparado no canal
> da equipe. Verificar se é indisponibilidade da origem (comum em REDEMET e
> ANA) ou falha do worker.

## 3. Filas que exigem decisão humana (3 min)

Na rota **Visão geral**, seção **PRIORIDADES AGORA** — cada item leva à fila:

- [ ] **Dados suspeitos**: revisar e decidir (aceitar/rejeitar) os itens novos
- [ ] **Ocorrências em triagem**: classificar denúncias recebidas do cidadão
- [ ] **Protocolos aguardando aprovação**: encaminhar à autoridade competente
- [ ] **Decisões do Gabinete com prazo vencido**: cobrar responsável ou repactuar

> Fila de qualidade acima de 100 itens indica problema sistêmico (fonte
> defeituosa ou parser), não erro pontual. Não tente triar item a item —
> registre a anomalia para análise técnica.

## 4. Situação meteorológica e hidrológica (2 min)

- [ ] Ler o **Resumo do Dia** na área pública (mesma informação do cidadão)
- [ ] Na rota **Monitoramento**, verificar **tendência de nível** das estações
      fluviométricas — marcador **vermelho pulsante = rio subindo**
- [ ] Havendo chuva em curso: conferir acumulados 1 h / 6 h / 24 h nos
      pluviômetros; acima de 20 mm/h iniciar acompanhamento reforçado
- [ ] Conferir alertas oficiais vigentes na aba pública **Alertas**

## 5. Continuidade (1 min)

- [ ] Backup da noite anterior presente em `BACKUP_DIR`
      (arquivo `meteoro_<data>.dump` + `.sha256`)
- [ ] Espaço em disco do servidor acima de 20% livre

## Ações imediatas por situação

| Situação | Ação |
|---|---|
| Chuva ≥ 60 mm/h (`flash_flood_critical`) | Acionar protocolo de cheia; comunicar coordenação da Defesa Civil |
| Nível ≥ 4 m ou subindo > 20 cm/h | Verificar cota local, acionar vistoria de campo |
| Alerta oficial novo (INMET/Defesa Civil) | Publicar recomendação pública correspondente |
| Denúncia de queimada com fumaça intensa | Encaminhar à SEMMAD; se risco imediato, orientar 193 |
| Plataforma fora do ar em evento severo | Operar pelo procedimento manual de contingência e registrar o período |

## Contatos

| Situação | Contato |
|---|---|
| Emergência (incêndio, resgate) | Corpo de Bombeiros — 193 |
| Defesa Civil | 199 |
| Suporte técnico da plataforma | _preencher_ |
| Coordenação da Defesa Civil municipal | _preencher_ |

---

**Registro do turno**

| Data | Turno | Operador | Pendências / observações |
|---|---|---|---|
| | | | |
