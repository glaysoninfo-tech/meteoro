# D12 — Operação assistida

## Rotina de operação

| Frequência | Responsável | Ação | Evidência |
|---|---|---|---|
| A cada turno | Operador | consultar situação, alertas técnicos, fila suspeita e protocolos pendentes | registro no chamado/diário |
| Diária | ADM | verificar conectores, observações atrasadas, jobs e capacidade | exportação de saúde |
| Semanal | Técnico | revisar falhas recorrentes, patches, auditoria e retenção | ata curta e plano de ação |
| Mensal | Gestor | revisar SLA, disponibilidade, pendências decisórias e fontes suspensas | relatório mensal |
| Trimestral | TI/ADM | testar restauração e revisar acessos/perfis | evidência do teste |

## Atendimento e SLA inicial

| Severidade | Exemplo | Resposta | Atualização |
|---|---|---:|---:|
| S1 | vazamento, indisponibilidade total ou publicação incorreta crítica | 1 h | a cada 2 h |
| S2 | fonte prioritária indisponível ou falha de protocolo | 4 h úteis | diária |
| S3 | defeito sem impacto imediato | 2 dias úteis | semanal |
| S4 | melhoria ou dúvida | priorização mensal | por backlog |

Os prazos são objetivos operacionais iniciais, a confirmar no contrato/gestão municipal. Todo chamado deve vincular impacto, responsável, decisão, horário e correção. Não classificar indisponibilidade externa como valor zero: manter último dado apenas com sinalização de desatualização.

## Transição

A operação assistida termina somente após equipe municipal executar, com acompanhamento, uma coleta manual, uma rotina automática, tratamento de exceção, restauração de homologação e publicação aprovada. O relatório final consolida chamados, SLAs, riscos abertos, correções e aceite do responsável municipal.
