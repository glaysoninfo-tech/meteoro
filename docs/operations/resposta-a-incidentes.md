# D10 — Resposta a incidentes de segurança e dados

## Acionamento

Abrir chamado de severidade apropriada para suspeita de vazamento, acesso não autorizado, indisponibilidade relevante, alteração de evidência, execução anômala de conector ou credencial exposta. Preservar horário, usuário, IP disponível, recurso, eventos de auditoria e logs; não apagar evidências.

## Rotina

1. **Detectar e classificar:** registrar impacto, escopo, fonte da detecção e responsável pelo incidente.
2. **Conter:** bloquear sessão/chave/fonte afetada, suspender publicação ou conector sem apagar payloads.
3. **Erradicar e recuperar:** corrigir configuração/código, rotacionar segredos, restaurar somente de backup testado e validar integridade.
4. **Comunicar:** envolver TI, encarregado e autoridade competente conforme análise de risco e obrigações legais; comunicação externa não é automática.
5. **Aprender:** encerrar com causa, evidências, decisão, prazo para ações preventivas e atualização do modelo de ameaças.

O líder técnico mantém o registro operacional; a decisão de notificação institucional é da autoridade municipal e do encarregado. Exercitar a rotina semestralmente em homologação.
