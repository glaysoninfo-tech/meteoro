# Rede Hidrometeorológica Municipal — diagnóstico e proposta

Data: 18/07/2026 · Base: levantamento executado pelo próprio METEORO sobre as
redes federal (ANA), nacional de alertas (CEMADEN), federal meteorológica
(INMET) e municipal vizinha (Defesa Civil de Belo Horizonte).

## 1. O que existe hoje sobre Betim

| Rede | Cobertura em Betim | Tipo de dado | Latência |
|---|---|---|---|
| **CEMADEN** | Pluviômetros no município (21 feições na região) | Chuva acumulada | Quase real |
| **ANA / SNIRH telemetria** | Estações no Rio Betim e Paraopeba (8 integradas) | Nível e vazão | Horária |
| **ANA convencional** | Réguas com leitura humana (ex.: 40790100) | Nível | Semanas/meses |
| **INMET** | **Nenhuma estação automática dentro de Betim** | — | — |
| **INMET vizinhas** | Ibirité/Rola-Moça (A555), Pampulha (A521), Cercadinho (A537), Florestal (A535) | Meteorologia completa | Horária |
| **Open-Meteo** | Ponto de modelo sobre Betim | Estimativa/previsão | Horária |

**Lacuna crítica identificada:** Betim não possui estação meteorológica
automática própria nem rede municipal de monitoramento de córregos urbanos.
O Rio Betim — curso d'água que atravessa a cidade, de resposta rápida — é
observado apenas indiretamente (telemetria da ANA no exutório e chuva do
CEMADEN como proxy).

## 2. Referência institucional: Belo Horizonte

A Defesa Civil de BH mantém **37 estações hidrometeorológicas próprias**
(pluviométricas, fluviométricas e climatológicas), distribuídas por bacia
urbana — Arrudas, Onça, Vilarinho, Ressaca, Jatobá, Leitão, Sarandi e outras.
O cadastro é público no Portal de Dados Abertos da PBH (CKAN/PRODABEL,
licença CC-BY) e está integrado ao METEORO como **camada de referência**.

> Observação técnica importante: o dataset publicado contém **apenas a
> localização** das estações (código, bacia, altitude, tipo, endereço,
> geometria EPSG:31983). As **medições não são publicadas** em dados abertos.
> Para obter séries de chuva e nível dessas estações seria necessário acordo
> de compartilhamento com a Defesa Civil de BH.

O arranjo de BH é o modelo direto do que se propõe para Betim: rede própria,
por bacia urbana, operada pela Defesa Civil, com dados abertos.

## 3. Proposta para Betim (fases)

**Fase 1 — Aproveitamento máximo do existente (concluída no METEORO):**
telemetria ANA, pluviômetros CEMADEN, estações INMET vizinhas e modelo
Open-Meteo integrados, com alertas por limiar de chuva e nível.

**Fase 2 — Convênios de dados (custo zero, prazo curto):**
- Defesa Civil de BH: séries das estações das bacias limítrofes;
- COPASA: nível dos reservatórios Vargem das Flores e Serra Azul;
- Defesa Civil estadual (MG): compartilhamento de pluviômetros regionais.

**Fase 3 — Rede municipal própria (investimento):**
- 2 a 4 sensores de nível (ultrassônico/radar) nos pontos historicamente
  críticos do Rio Betim e afluentes urbanos;
- 4 a 6 pluviômetros automáticos distribuídos por bairro/vertente;
- 1 estação meteorológica automática municipal completa.

**Integração já pronta:** a plataforma suporta ingestão direta por **MQTT**
(`sensor_stream`) e **OPC UA** — sensores novos entram sem desenvolvimento
adicional, bastando cadastro no Catálogo de Fontes e liberação do host na
allowlist de rede.

## 3-A. Interpolação: a ponte enquanto não há estação própria

Betim não possui estação meteorológica automática dentro do território. Até
que exista (item da Fase 3), as condições de temperatura, umidade, vento e
chuva no ponto do município são estimadas por **interpolação IDW** (Inverse
Distance Weighting) das estações e pontos com dado recente:

- **Peso = 1 / distância²** — cada estação contribui na proporção inversa do
  quadrado da distância a Betim (Haversine).
- **Correção de altitude** — a temperatura de cada estação é ajustada pela
  taxa de lapso térmico (~6,5 °C/km) antes de entrar na média.
- **Janela de 3 h** — só entram observações recentes; estação parada é
  ignorada automaticamente.

Endpoint: `GET /api/v1/public/conditions/interpolated`.

**Propriedade importante:** o método **melhora sozinho**. Hoje seus insumos
automáticos são majoritariamente de modelo (Open-Meteo); assim que estações
reais passarem a coletar (retorno da API do INMET, convênio ou sensor
municipal via MQTT), elas entram no cálculo sem nenhuma alteração de código —
basta terem coordenada e dado recente. A estimativa passa de "modelo
interpolado" a "estimativa observacional" na medida em que a rede real cresce.

O resultado é sempre rotulado como **estimativa espacial, não medição no
local** — coerente com a política de honestidade de dados da plataforma.

## 4. Justificativa técnica dos limiares

Rios urbanos de pequena bacia respondem à chuva em **horas**. Por isso o
METEORO opera uma escada de alerta baseada em chuva horária, complementar aos
limiares de nível:

| Chuva (mm/h) | Alerta | Ação sugerida |
|---|---|---|
| ≥ 20 | `urban_rain_advisory` | Acompanhar acumulados CEMADEN |
| ≥ 30 | `storm_rain_watch` | Monitoramento reforçado |
| ≥ 50 | `storm_heavy_rain` | Preparar equipes |
| ≥ 60 | `flash_flood_critical` | Acionar protocolo de cheia |

| Nível (m) | Alerta |
|---|---|
| ≥ 4 | `river_level_high` |
| ≥ 6 | `river_level_critical` |

Os limiares de nível devem ser **recalibrados por estação** durante o piloto,
a partir das cotas de transbordamento locais — o valor genérico serve apenas
como ponto de partida.

## Fontes

- Portal de Dados Abertos PBH — Estação Hidrometeorológica (Defesa Civil/PRODABEL, CC-BY)
- ANA / SNIRH — HidroWeb e telemetria (`telemetriaws1.ana.gov.br`)
- CEMADEN — pluviômetros automáticos
- INMET — estações automáticas e BDMEP
