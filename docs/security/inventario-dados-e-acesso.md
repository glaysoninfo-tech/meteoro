# D10 — Inventário de dados, acesso e retenção

## Classificação operacional

| Classe | Exemplos | Portal público | Acesso interno | Retenção inicial proposta |
|---|---|---:|---|---|
| Público | alertas vigentes, estações liberadas, observações validadas agregadas | sim | papéis autorizados | conforme política de transparência |
| Interno | saúde de fonte, qualidade, tarefas e rascunhos | não | operador e papéis setoriais | 5 anos, sujeito a norma municipal |
| Restrito | evidência operacional, localização precisa não publicada | não | necessidade de conhecer e auditoria | conforme processo administrativo |
| Sensível/pessoal | denúncia identificável, saúde nominal, documentos pessoais | não | somente competência legal explícita | mínimo necessário, tabela de temporalidade e base legal |

O sistema já filtra a superfície pública por classificação de estações e territórios. Dados de denúncias e dados nominais não são publicados por APIs de dados abertos. A classificação é uma decisão administrativa registrada; não substitui análise jurídica.

## Matriz mínima de acesso

| Papel | Pode executar | Não pode executar |
|---|---|---|
| Cidadão | consultar apenas dados públicos | consultar dados internos/restritos |
| Operador | tratar qualidade, ocorrências e ações dentro da organização | administrar usuários ou aprovar fora de sua competência |
| Auditor | consultar trilha filtrável de auditoria | alterar evidências e eventos |
| ADM geral | administrar fontes, usuários e configuração | aprovar automaticamente a própria recomendação crítica |

As permissões efetivas devem ser configuradas no provedor de identidade e periodicamente revisadas. A trilha pode ser consultada por ator, módulo, ação, objeto e intervalo de tempo, com limite máximo de 500 resultados por chamada.

## Registro de operações de tratamento

Antes de integrar denúncias, saúde ou assistência, preencher para cada fluxo: controlador, finalidade, base legal, categoria de titular/dado, destinatários, medidas de segurança, prazo de eliminação, encarregado e canal de direitos do titular. Dados analíticos devem reduzir precisão, aplicar supressão para pequenas contagens e nunca conter identificadores diretos.
