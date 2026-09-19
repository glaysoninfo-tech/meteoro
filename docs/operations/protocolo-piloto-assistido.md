# Protocolo do Piloto Assistido — METEORO

Período: **4 semanas** a contar do go-live indoor. Modalidade: **operação em
sombra** — a plataforma opera de verdade, mas as decisões oficiais continuam
seguindo o fluxo vigente em paralelo. Nada substitui procedimento consolidado
antes do aceite formal.

## 1. Pré-requisitos (verificar antes de iniciar)

- [ ] `compose.prod.yml` no ar com `.env.prod` preenchido (segredos fortes)
- [ ] TLS interno funcionando; certificado da CA instalado nas estações
- [ ] Primeiro backup gerado e **um restore de ensaio já executado**
- [ ] Alertas do Prometheus chegando ao canal da equipe (teste real: derrubar
      o worker e confirmar recebimento)
- [ ] Fontes instaladas: Open-Meteo, REDEMET, INMET regionais, ANA telemetria
- [ ] Usuários nominais criados por perfil (sem conta administrativa compartilhada)
- [ ] Operadores treinados na trilha `docs/training/` e com o checklist diário impresso

## 2. Papéis

| Papel | Responsabilidade no piloto |
|---|---|
| Operador de plantão | Checklist diário, triagem das filas, registro de ocorrências |
| Coordenação da Defesa Civil | Decisões, aprovação de protocolos, validação dos alertas |
| SEMMAD | Triagem das denúncias ambientais recebidas do cidadão |
| Suporte técnico | Incidentes de plataforma, ajustes de limiar, correções |
| Gabinete / Comitê | Recebe relatório semanal; decide o go/no-go final |

## 3. Rotina do piloto

**Diária:** checklist do operador (início de turno); registro de toda
divergência entre o que a plataforma indicou e o que de fato ocorreu.

**Semanal:** reunião de 30 minutos com: itens registrados, alarmes disparados
(verdadeiros × falsos), ajustes de limiar propostos, pendências de dados.

**Contínua:** cada bug, dúvida ou dado suspeito vira um registro — a lista de
ocorrências do piloto é o principal insumo do aceite.

## 4. Calibração esperada (não é falha — é o objetivo do piloto)

Durante as 4 semanas, espera-se ajustar:

- **Limiares de nível por estação** — substituir os valores genéricos (4 m / 6 m)
  pelas cotas reais de transbordamento de cada ponto;
- **Limiares de chuva** — validar a escada 20/30/50/60 mm/h contra o
  comportamento observado das bacias urbanas;
- **Regras de qualidade** — reduzir falsos suspeitos sem perder detecção;
- **Alarmes de staleness** — ajustar tolerância por fonte (REDEMET e ANA
  oscilam legitimamente).

## 5. Critérios de aceite (avaliados na 4ª semana)

| Critério | Meta | Como medir |
|---|---|---|
| Disponibilidade da plataforma | ≥ 99% no horário operacional | Métrica `up` no Prometheus |
| Perda de dados ingeridos | Zero | Comparar execuções × registros aceitos |
| Staleness de fonte crítica | Sem episódio > 6 h não justificado | Histórico `meteoro_source_staleness_seconds` |
| Backup e restore | Backup diário íntegro + 1 restore ensaiado | `docs/operations/backup-e-restore.md` |
| Autonomia dos operadores | 2 operadores executam o checklist sem apoio técnico | Observação direta |
| Alarmes úteis | Falsos positivos ≤ 20% dos alarmes críticos | Registro semanal |
| Fila de triagem | Nenhum item pendente > 72 h | Painel Visão geral |
| Denúncias do cidadão | 100% triadas dentro do prazo pactuado com a SEMMAD | Módulo de ocorrências |

## 6. Go / No-Go

Ao fim das 4 semanas, reunião formal com o Gabinete/Comitê:

- **GO** — todos os critérios atendidos: a plataforma passa a compor
  oficialmente a rotina da Defesa Civil (permanecendo o fluxo antigo como
  contingência por mais 30 dias).
- **GO CONDICIONAL** — critérios majoritariamente atendidos: define-se plano
  de correção com prazo e nova avaliação em 2 semanas.
- **NO-GO** — falha em disponibilidade, perda de dados ou autonomia: retorno
  ao desenvolvimento com causas documentadas.

A decisão é registrada como **decisão do Gabinete** na própria plataforma
(`/planning/cabinet/decisions`), com responsável e prazo — o sistema
documentando a própria homologação.

## 7. Após o aceite (fase pública)

Só então iniciar: domínio e TLS público, exposição do portal cidadão à
internet, WAF/CDN, LGPD e termo de dados abertos, teste de carga externo, e as
etapas estruturais E15–E17 (contratos modulares, parametrização multi-município,
console SPA).

---

## Registro de ocorrências do piloto

| # | Data | Tipo (bug/dado/dúvida) | Descrição | Status |
|---|---|---|---|---|
| | | | | |

## Registro de reuniões semanais

| Semana | Data | Presentes | Decisões | Ajustes aplicados |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
