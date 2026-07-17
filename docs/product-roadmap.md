# Estratégia incremental da camada de produto

## Princípios de decisão

1. **Uma jornada completa antes de mais telas.** Cada incremento deve deixar uma pessoa capaz de concluir uma tarefa, com estado, autorização, evidência e retorno claro.
2. **A informação pública não depende da área restrita.** Transparência e continuidade operacional têm ritmos e permissões diferentes.
3. **Decisões críticas exigem autoria e motivo.** A interface só aciona transições já protegidas pela API e apresenta o contexto necessário para decidir.
4. **Dados e integração vêm depois da experiência mínima confiável.** Não adicionar canais, ML ou parceiros antes de haver operação mensurável e auditável.

## Sequência de entregas

### Incremento 1 — Fundação de produto (em implementação)

- Sessão explícita, restauração segura e encerramento de sessão.
- Navegação por papel e ações somente para perfis autorizados.
- Estados de carregamento, erro e confirmação não intrusivos.
- Tratamento no portal de: dados suspeitos, ocorrências e aprovações de protocolo.
- Proteção de apresentação contra conteúdo retornado pela API.

**Aceite:** um operador consegue entrar, entender a fila, registrar uma decisão e vê-la desaparecer da pendência; um aprovador só vê a aprovação que pode executar.

### Incremento 2 — Estações de trabalho operacionais (em implementação)

- Filtros persistentes por severidade e texto livre (território, fonte e prazo na próxima fatia).
- Janela de detalhe para ocorrência, dado suspeito, protocolo e evidência; acesso à auditoria quando autorizado.
- Histórico de decisões e motivo, com visualização da trilha de auditoria.
- Ações de coleta, reprocessamento e revisão em lote com confirmação e resultado assíncrono.

**Aceite:** a equipe opera uma ocorrência do alerta à evidência sem recorrer à documentação técnica ou ao banco de dados.

### Incremento 3 — Gabinete e comunicação de decisão (em implementação)

- Lista decisória por risco, severidade, território, prazo e impacto.
- Registro persistente de decisão, responsável, prazo, situação e acompanhamento; escalonamento de pendências permanece como próxima fatia.
- Geração de briefing e boletim para revisão editorial, sem envio automático por padrão.

**Aceite:** o Gabinete consegue responder o que exige decisão, por quê, por quem e até quando.

### Incremento 4 — Portal público confiável e inclusivo (em implementação)

- Detalhe de alerta com território, validade, fontes e recomendações publicadas.
- Busca e filtros persistentes por texto, severidade e território, com controles rotulados e estados de indisponibilidade.
- Dados abertos com metadados, dicionário, recorte e situação explícita de licença configurável por ambiente.
- PWA com cache deliberado para páginas públicas essenciais.

**Aceite:** uma pessoa encontra orientação oficial em poucos passos e consegue verificar a origem e atualização da informação.

### Incremento 5 — Prontidão para produção (em implementação)

- Liveness, readiness de dependências, correlação por requisição e logs de acesso estruturados.
- Runbook de backup/restauração e health checks do ambiente Docker. Gestão de segredos, retenção formal e alertas externos permanecem como próxima fatia.
- Integração real de mensageria somente com sandbox, consentimento e monitoramento de entrega.

**Aceite:** o município consegue sustentar operação, auditoria e recuperação sem intervenção no código.

## Fora do escopo até a fundação estar estável

- Cadastro e contratos de empresas parceiras.
- Treinamento, operação ou governança de modelos de ML.
- Mensageria de eventos dedicada além da fila Redis atual.
- Canais externos de comunicação em produção.
