# D01 — Plano executivo e descoberta

## Objetivo e escopo do MVP

O MVP comprova que o Município consegue catalogar fontes, preservar os dados recebidos, avaliar sua qualidade, registrar ocorrências, ativar protocolos com aprovação segregada, publicar informação pública e manter auditoria. Ele não inclui contratos empresariais, multitenancy, mensageria em produção ou ML para ativação automática.

## Plano de trabalho incremental

| Incremento | Resultado verificável | Dependência |
| --- | --- | --- |
| I1 — Fundação | identidade, RBAC, catálogo, auditoria, CI e backup operável | responsáveis municipais definidos |
| I2 — Dados confiáveis | conectores, payload bruto, idempotência, reprocessamento, estações e qualidade | endpoints e licenças das fontes |
| I3 — Resposta municipal | alertas oficiais, ocorrências, protocolos e recomendações aprovadas | fluxo de aprovação homologado |
| I4 — Transparência | portais, dados abertos, boletins, APIs e relatórios | classificação de informação validada |
| I5 — Operação assistida | capacitação, exercícios, monitoramento, SLAs e transição | equipe municipal treinada |

Cada incremento termina com demonstração, roteiro de aceite, registro de não conformidades e decisão de seguir, corrigir ou replanejar.

## Governança e responsabilidades

| Papel | Responsabilidade decisória |
| --- | --- |
| Patrocinador municipal | prioriza escopo, orçamento e aceite institucional |
| Dono do produto | prioriza backlog e aceita funcionalidades de negócio |
| Defesa Civil / operação | valida ocorrências, protocolos e cenários de resposta |
| Saúde, Meio Ambiente e Assistência | definem regras setoriais e usam dados agregados autorizados |
| Comunicação | aprova conteúdo público e canais de publicação |
| TI municipal | identidade, infraestrutura, backups, observabilidade e continuidade |
| Encarregado/LGPD e jurídico | classificação, retenção, compartilhamentos e riscos de dados pessoais |
| Controle interno | consulta auditoria, evidências e trilhas de decisão |

Nenhum autor aprova a própria versão crítica de protocolo ou recomendação. A aprovação e a publicação permanecem registradas separadamente.

## Stakeholders e comunicação

| Público | Informação | Cadência | Canal |
| --- | --- | --- |
| Comitê gestor | progresso, riscos, decisões e aceite | quinzenal | reunião e ata |
| Operadores | mudanças, fontes degradadas e exercícios | semanal | portal operacional e reunião curta |
| TI e segurança | incidentes, backups, vulnerabilidades e mudanças | semanal e sob evento | chamados e runbook |
| Cidadãos | situação, alertas oficiais e recomendações aprovadas | sob atualização | site público |
| Auditoria | acessos, aprovações, exportações e evidências | sob demanda | API/relatórios auditáveis |

## Inventário inicial de fontes

| Domínio | Produto prioritário | Uso | Estado inicial |
| --- | --- | --- | --- |
| INMET | avisos, observações e histórico BDMEP | alerta e climatologia | conector/configuração inicial |
| REDEMET/DECEA | METAR/SPECI SBBH e SNDV; TAF quando aplicável | contexto regional, não medição de Betim | requer endpoint e chave rotacionada |
| Semad/FEAM/MonitorAr | qualidade do ar e disponibilidade das estações | PM2,5, PM10 e gases | requer contrato de endpoint/dados |
| INPE | focos de calor, risco e produtos geoespaciais | evidência satelital, não incêndio confirmado | a catalogar |
| Cemaden | pluviômetros, radar e produtos disponibilizados | risco hidrometeorológico | a catalogar |
| Sistemas municipais | ocorrências, vistorias e denúncias agregadas | resposta operacional | depende de acordo e classificação |

O arquivo `docs/catalogo-inicial-fontes.csv` é a base de homologação do catálogo municipal. Ele não contém credenciais, nem presume que uma URL ainda não validada possa ser coletada.

## Riscos iniciais

| Risco | Tratamento | Dono |
| --- | --- | --- |
| Fonte externa indisponível ou alterada | health check, retry limitado, payload preservado e indicador de desatualização | TI/operação |
| URL maliciosa ou SSRF | allowlist, HTTPS, DNS/IP público, timeout, limite de resposta | TI |
| Dado pessoal em ocorrência/denúncia | classificação, zona restrita, minimização e exportação protegida | encarregado/LGPD |
| Alerta confundido com observação | tipagem explícita e legenda por origem/certeza | produto/operação |
| Aprovação sem competência | RBAC, segregação de deveres e auditoria | dono do produto |
| Falha de restauração | backup automatizado e exercício periódico de recuperação | TI |

## Ambientes

- Desenvolvimento: dados sintéticos ou anonimizados; sem credenciais de produção.
- Homologação: integrações autorizadas, testes de perfil e roteiros de aceite.
- Produção: segredos gerenciados fora do repositório, backup, monitoramento e controle de mudança.

## Backlog priorizado

1. Segurança operacional: segredos, backup/restauração, matriz de acesso e observabilidade.
2. Catálogo e ingestão das fontes prioritárias, com evidência bruta e saúde do conector.
3. Cadastro de territórios, estações, sensores, observações e qualidade.
4. Alertas, ocorrências, protocolos e recomendações com aprovação segregada.
5. Portal operacional, painel executivo, site público e dados abertos acessíveis.
6. Relatórios, APIs, capacitação e operação assistida.

## Critérios de aceite transversais

- Toda tela/API informa fonte, horário de atualização, classificação e limitação quando aplicável.
- Coleta falha sem derrubar a plataforma, sem gerar valor zero e com início/fim da indisponibilidade registrados.
- Todo dado original preservado é associado a hash, origem, horário e versão do conector.
- Dados públicos nunca expõem conteúdo interno, restrito, sensível ou identificável.
- Fluxos críticos têm teste automatizado, roteiro manual de aceite e evento de auditoria.
- Evidências institucionais (ata, oficina, aprovação, exercício e assinatura) são coletadas pelo Município; o repositório mantém os modelos e os roteiros.
