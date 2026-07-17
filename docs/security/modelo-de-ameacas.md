# D10 — Modelo de ameaças e controles

## Escopo e ativos protegidos

O METEORO trata dados públicos, internos, restritos e, futuramente, dados pessoais sob regime legal específico. Os ativos prioritários são: contas institucionais, dados operacionais, payloads brutos imutáveis, geometrias, anexos, trilha de auditoria, segredos, backups e disponibilidade dos portais.

| Ameaça | Consequência | Controle implementado | Verificação recorrente |
|---|---|---|---|
| Acesso indevido | alteração ou leitura de dados internos | JWT, papéis, escopo por organização, trilha de auditoria | teste de autorização por perfil |
| Aprovação pelo próprio autor | publicação sem segregação | serviço bloqueia autoaprovação de recomendação crítica | teste de fluxo de aprovação |
| SSRF por conector | acesso à rede interna | allowlist de hosts/portas, resolução de IP público, bloqueio de IP local | teste unitário de rede |
| Payload excessivo ou malicioso | exaustão de recursos | limites de upload/resposta, timeout e retentativa limitada | teste de ingestão e revisão de limites |
| Host header / clickjacking / MIME sniffing | desvio de sessão e interface | Trusted Host, CSP, X-Frame-Options, nosniff, Referrer-Policy | verificação de cabeçalhos |
| Segredo exposto | acesso a infraestrutura | `.env` fora do controle de versão, exemplos sem segredo real, rotação no cofre municipal | varredura de segredos antes do deploy |
| Perda ou alteração de evidência | perda de rastreabilidade | hash, origem e armazenamento bruto; auditoria somente por inserção na aplicação | teste de restauração e revisão de logs |
| Fonte externa indisponível | informação enganosa | estado de saúde, falha técnica e último dado identificado como desatualizado | simulação de indisponibilidade |

## Barreiras obrigatórias de produção

`ENVIRONMENT=production` impede a inicialização com segredo JWT de exemplo/curto, `ALLOWED_HOSTS` vazio ou curinga e HTTPS desabilitado. O proxy reverso deve encaminhar corretamente o esquema HTTPS antes de ativar `FORCE_HTTPS=true`.

O banco deve usar credenciais exclusivas, TLS onde aplicável, contas sem privilégio de superusuário para a aplicação e cópias de backup criptografadas. A implantação municipal ainda deve habilitar MFA no provedor de identidade para perfis críticos e concentrar segredos em cofre próprio; estes dois itens dependem do ambiente institucional.

## Limites conhecidos e aceite

Não há alegação de conformidade legal ou pentest independente neste repositório. Antes da produção, o Município deve executar teste externo de segurança, restaurar backup em ambiente isolado, validar configurações do proxy, confirmar retenções com encarregado/LGPD e registrar os riscos aceitos com responsável e prazo.
