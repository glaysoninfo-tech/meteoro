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

### Incremento 2 — Estações de trabalho operacionais

- Filtros persistentes por território, severidade, fonte e prazo.
- Página de detalhe para alerta, ocorrência, protocolo e evidência; links entre os objetos.
- Histórico de decisões e motivo, com visualização da trilha de auditoria.
- Ações de coleta, reprocessamento e revisão em lote com confirmação e resultado assíncrono.

**Aceite:** a equipe opera uma ocorrência do alerta à evidência sem recorrer à documentação técnica ou ao banco de dados.

### Incremento 3 — Gabinete e comunicação de decisão

- Lista decisória priorizada por prazo, severidade, território e impacto.
- Registro de decisão, responsável, prazo e acompanhamento; escalonamento de pendências.
- Geração de briefing e boletim para revisão editorial, sem envio automático por padrão.

**Aceite:** o Gabinete consegue responder o que exige decisão, por quê, por quem e até quando.

### Incremento 4 — Portal público confiável e inclusivo

- Página de alerta com território, validade, fontes e recomendações relacionadas.
- Busca, filtros, acessibilidade WCAG, linguagem clara e estados de indisponibilidade.
- Dados abertos com metadados, dicionário, licença, recorte e versão de exportação.
- PWA com cache deliberado para páginas públicas essenciais.

**Aceite:** uma pessoa encontra orientação oficial em poucos passos e consegue verificar a origem e atualização da informação.

### Incremento 5 — Prontidão para produção

- Observabilidade de jornada, logs estruturados, indicadores de serviço e alertas técnicos.
- Gestão de segredos, política de retenção, backup/restauração e acessibilidade continuada.
- Integração real de mensageria somente com sandbox, consentimento e monitoramento de entrega.

**Aceite:** o município consegue sustentar operação, auditoria e recuperação sem intervenção no código.

## Fora do escopo até a fundação estar estável

- Cadastro e contratos de empresas parceiras.
- Treinamento, operação ou governança de modelos de ML.
- Mensageria de eventos dedicada além da fila Redis atual.
- Canais externos de comunicação em produção.
