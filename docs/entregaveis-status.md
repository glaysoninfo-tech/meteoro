# Matriz de entregáveis D01–D12

Status: **implementado no repositório**, **parcial** ou **evidência municipal pendente**. A última categoria não é defeito de código: depende de aprovação, oficina, ambiente ou exercício realmente executado.

| Entregável | Estado atual | Próxima evidência/ação de aceite |
| --- | --- | --- |
| D01 — Plano executivo e descoberta | parcial documentado | aprovar plano, realizar oficinas e arquivar atas, mapa de stakeholders e riscos |
| D02 — Arquitetura e fundação | implementado com evidência de ambiente pendente | executar CI municipal, configurar segredos, backup externo e teste de restauração |
| D03 — Catálogo, ingestão e bruto | implementado parcialmente | catálogo inicial sem segredos em `docs/catalogo-inicial-fontes.csv`; falta homologar endpoints reais, simular falha e reprocessar período com evidência |
| D04 — Estações, observações e qualidade | implementado parcialmente | saúde por sensor calcula atraso, completude e lacunas sem preencher zero; falta carregar estações reais e homologar regras setoriais |
| D05 — Alertas, ocorrências e protocolos | implementado parcialmente | ciclo de confirmação, conversão em incidente, ações e encerramento está codificado; falta cenário homologado com autoridade e relatório final |
| D06 — Recomendações e comunicação | implementado parcialmente | aprovar/publicar recomendação real, testar expiração e homologar modelos de mensagem |
| D07 — Portal operacional | parcial | painel apresenta coletas, worker, rotinas INMET e saúde por sensor; faltam mapa, roteiros por perfil, auditoria visual e testes de desempenho/acessibilidade |
| D08 — Site público | parcial | situação, alertas, recomendações, metodologia e CSV público foram incluídos; faltam eMAG/WCAG formal, conteúdo institucional e teste de carga |
| D09 — Relatórios e APIs | parcial | OpenAPI, guia de uso, paginação JSON e CSV de observações estão disponíveis; faltam PDF, filtros/CSV para os demais relatórios e exemplos completos |
| D10 — Segurança e privacidade | implementado parcialmente | barreiras de produção, cabeçalhos, auditoria filtrável, modelo de ameaças, inventário e runbook incluídos; faltam pentest independente, restauração executada e aceite LGPD municipal |
| D11 — Capacitação e transferência | documentado, pendente em campo | trilhas e exercícios incluídos; faltam laboratório, presença, avaliação e gravações executadas |
| D12 — Operação assistida | documentado, pendente em campo | rotina, SLAs iniciais e healthcheck incluídos; faltam canal de suporte, medição real e transição final |

## Mapeamento de incrementos

1. D01–D02: documentos, CI, ambiente, segredos, backup e observabilidade.
2. D03–D04: fontes reais, ingestão, estações e qualidade com evidência de dados.
3. D05–D06: resposta municipal e governança editorial; aprovação segregada.
4. D07–D09: experiência operacional/pública, relatórios e contratos de API.
5. D10–D12: segurança, privacidade, capacitação e operação assistida.

## Critério de conclusão de cada entregável

Um item só passa a concluído quando houver: código/configuração versionada, teste automatizado quando aplicável, roteiro manual executado, evidência arquivada e aceite do responsável municipal. Uma demonstração local não substitui essas quatro últimas provas.
