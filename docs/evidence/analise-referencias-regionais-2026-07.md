# Análise das referências meteorológicas regionais

## Arquivos avaliados

| Arquivo | Referência territorial | Registros | Período UTC | Cobertura temporal |
|---|---:|---:|---|---:|
| `pampulhat-csv.csv` | Pampulha, Belo Horizonte | 4.032 | 29/01/2026 00:00 a 15/07/2026 23:00 | 100% das horas; 11 leituras incompletas |
| `cercadinhoBH-csv.csv` | Cercadinho, Belo Horizonte | 4.032 | 29/01/2026 00:00 a 15/07/2026 23:00 | 100% das horas; 12 leituras incompletas |
| `divinopolis-csv.csv` | Divinópolis | 4.032 | 29/01/2026 00:00 a 15/07/2026 23:00 | 100% das horas; 12 leituras incompletas; 224 ausências de umidade |

Os três arquivos são exportações horárias, com cabeçalho `Data` e `Hora (UTC)`
separados. Não há timestamps inválidos ou duplicados; as ausências de variáveis
permanecem lacunas e não devem ser convertidas em zero.

## Leitura descritiva

| Referência | Temperatura média / mín.–máx. | Umidade média / mín.–máx. | Chuva acumulada | Vento médio |
|---|---|---|---:|---:|
| Pampulha | 21,27 °C / 9,0–31,4 °C | 72,43% / 26–93% | 675,0 mm | 0,92 m/s |
| Cercadinho | 19,74 °C / 9,5–29,8 °C | 72,60% / 25–93% | 452,6 mm | 4,44 m/s |
| Divinópolis | 21,38 °C / 7,7–31,9 °C | 78,23% / 27–100% | 533,6 mm | 1,90 m/s |

Esses números descrevem apenas a janela disponível; não substituem normais
climatológicas e não permitem concluir condições medidas em bairros de Betim.

## Uso no METEORO

Os arquivos podem ser cadastrados como fontes `manual_file` de categoria
`meteorology`, cada uma com seu código externo confirmado pelo administrador.
O perfil de conector deve ser:

```json
{"parser":"inmet","station_code":"<CODIGO_EXTERNO_CONFIRMADO>"}
```

O parser passa a reconhecer diretamente o layout recebido, normalizando
`Temp. Ins. (C)`, `Umi. Ins. (%)`, `Chuva (mm)` e `Vel. Vento (m/s)` para a
série temporal do sistema, com horário UTC e vínculo de estação configurado.

## Utilidade operacional

1. **Contexto regional:** comparar o comportamento regional de temperatura,
   umidade, chuva e vento com uma futura estação em Betim, deixando a origem
   claramente identificada.
2. **Qualidade e atraso:** exercitar os indicadores de completude; por exemplo,
   a série de umidade de Divinópolis deve abrir lacunas reais, não valores zero.
3. **Protocolos transparentes:** subsidiar sugestão humana de ações para calor,
   baixa umidade, chuva e vento, sempre como evidência regional e não gatilho
   automático de alerta público.
4. **Calibração futura:** depois de instalada/confirmada uma estação municipal,
   comparar diferenças por horário e estação do ano para definir limites locais.
5. **Boletim e auditoria:** gerar boletim com fonte, período, disponibilidade e
   limitações, preservando o CSV original e seu hash.

## Limitações obrigatórias de apresentação

- Pampulha e Cercadinho são referências de Belo Horizonte; Divinópolis é uma
  referência externa. Nenhuma delas equivale a observação instrumental de Betim.
- A pressão é influenciada pela altitude, portanto não deve ser comparada como
  risco municipal sem ajuste e contexto.
- Não há qualidade do ar, focos de queimadas, ocorrência ou alerta oficial
  nesses arquivos.
- Antes de uso público, o administrador deve confirmar instituição, código da
  estação, licença e método de obtenção no Catálogo Municipal de Fontes.
