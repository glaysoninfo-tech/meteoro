"""Saúde ambiental: índices operacionais de calor, umidade, queimada e fumaça.

Implementa a leitura de risco à saúde exigida pela Política Municipal para
Calor, Baixa Umidade, Queimadas e Fumaça, a partir das observações já
ingeridas pela plataforma. Todos os limiares seguem referências oficiais e
são declarados junto ao resultado — nada é caixa-preta para o gestor.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalog.models import SourceModel
from app.modules.ingestion.models import ObservationModel

# Níveis oficiais de baixa umidade (INMET / Defesa Civil Nacional).
HUMIDITY_LEVELS = (
    (12.0, "emergencia", "Estado de Emergência", "#7f1d1d"),
    (20.0, "alerta", "Estado de Alerta", "#b91c1c"),
    (30.0, "atencao", "Estado de Atenção", "#b45309"),
)

# Faixas de índice de calor (NOAA/Rothfusz), em °C.
HEAT_LEVELS = (
    (54.0, "extremo", "Perigo extremo", "#7f1d1d"),
    (41.0, "perigo", "Perigo", "#b91c1c"),
    (32.0, "cautela_extrema", "Cautela extrema", "#b45309"),
    (27.0, "cautela", "Cautela", "#ca8a04"),
)


def _heat_index_c(temperature_c: float, humidity_pct: float) -> float:
    """Índice de calor (sensação térmica por calor+umidade), fórmula de Rothfusz.

    A equação é definida em °F; abaixo de 27 °C o próprio NOAA considera o
    índice igual à temperatura do ar.
    """
    if temperature_c < 27.0:
        return temperature_c
    t = temperature_c * 9.0 / 5.0 + 32.0
    r = humidity_pct
    hi = (
        -42.379
        + 2.04901523 * t
        + 10.14333127 * r
        - 0.22475541 * t * r
        - 0.00683783 * t * t
        - 0.05481717 * r * r
        + 0.00122874 * t * t * r
        + 0.00085282 * t * r * r
        - 0.00000199 * t * t * r * r
    )
    return round((hi - 32.0) * 5.0 / 9.0, 1)


def _level_for(value: float, table, ascending: bool) -> tuple[str, str, str] | None:
    for threshold, code, label, color in table:
        if (ascending and value >= threshold) or (not ascending and value <= threshold):
            return (code, label, color)
    return None


def _fire_risk(temperature_c: float | None, humidity_pct: float | None, wind_ms: float | None, rain_72h_mm: float) -> dict:
    """Risco de propagação de queimada (aproximação operacional).

    Combina os fatores clássicos da Fórmula de Monte Alegre e do índice de
    Nesterov — calor, ar seco, vento e ausência de chuva recente. Não
    substitui o risco de fogo oficial do INPE; serve para acionar vigilância
    e fiscalização preventiva da SEMMAD.
    """
    score = 0
    fatores: list[str] = []
    if humidity_pct is not None:
        if humidity_pct < 20:
            score += 3
            fatores.append(f"ar muito seco ({humidity_pct:.0f}%)")
        elif humidity_pct < 30:
            score += 2
            fatores.append(f"ar seco ({humidity_pct:.0f}%)")
        elif humidity_pct < 40:
            score += 1
    if temperature_c is not None:
        if temperature_c >= 32:
            score += 2
            fatores.append(f"calor ({temperature_c:.0f} °C)")
        elif temperature_c >= 28:
            score += 1
    if wind_ms is not None and wind_ms >= 5:
        score += 2
        fatores.append(f"vento favorecendo propagação ({wind_ms:.1f} m/s)")
    elif wind_ms is not None and wind_ms >= 3:
        score += 1
    if rain_72h_mm < 1:
        score += 2
        fatores.append("sem chuva significativa nas últimas 72 h")
    elif rain_72h_mm < 5:
        score += 1

    if score >= 7:
        code, label, color = "critico", "Crítico", "#7f1d1d"
    elif score >= 5:
        code, label, color = "alto", "Alto", "#b91c1c"
    elif score >= 3:
        code, label, color = "moderado", "Moderado", "#b45309"
    else:
        code, label, color = "baixo", "Baixo", "#16803c"
    return {"level": code, "label": label, "color": color, "score": score, "factors": fatores}


def _recommendations(humidity_level: str | None, heat_level: str | None, fire_level: str) -> list[dict]:
    """Ações recomendadas por público, no espírito da Política Municipal."""
    acoes: list[dict] = []
    if humidity_level in {"alerta", "emergencia"}:
        acoes.append({
            "audience": "População",
            "action": "Hidratação frequente, evitar exercício físico entre 10h e 16h e umidificar ambientes.",
        })
        acoes.append({
            "audience": "Saúde",
            "action": "Reforçar atendimento respiratório em UBS e monitorar idosos e crianças com asma/DPOC.",
        })
        acoes.append({
            "audience": "Educação",
            "action": "Suspender atividades físicas ao ar livre no horário mais seco.",
        })
    elif humidity_level == "atencao":
        acoes.append({
            "audience": "População",
            "action": "Aumentar a ingestão de água e evitar exposição prolongada ao sol.",
        })
    if heat_level in {"perigo", "extremo"}:
        acoes.append({
            "audience": "Assistência Social",
            "action": "Busca ativa de população em situação de rua e distribuição de água; abrir pontos de resfriamento.",
        })
        acoes.append({
            "audience": "Trabalho",
            "action": "Pausas obrigatórias para trabalhadores expostos ao sol e ajuste de jornada.",
        })
    elif heat_level == "cautela_extrema":
        acoes.append({
            "audience": "População",
            "action": "Evitar esforço físico no período mais quente; atenção a crianças e idosos.",
        })
    if fire_level in {"alto", "critico"}:
        acoes.append({
            "audience": "SEMMAD / Fiscalização",
            "action": "Intensificar vigilância em áreas de queimada recorrente e acionar fiscalização preventiva.",
        })
        acoes.append({
            "audience": "População",
            "action": "Não queimar resíduos nem soltar balões; denunciar focos pelos canais oficiais (193).",
        })
    if not acoes:
        acoes.append({
            "audience": "Operação",
            "action": "Condições dentro da normalidade; manter monitoramento de rotina.",
        })
    return acoes


class EnvironmentalHealthService:
    TRACKED = ("temperature_c", "humidity_pct", "wind_speed_mps", "rainfall_mm_1h", "pm25_ugm3", "pm10_ugm3")

    def build_indicators(self, db: Session, organization_id: str) -> dict:
        now = datetime.now(tz=timezone.utc)
        since = now - timedelta(hours=72)
        rows = list(db.execute(
            select(ObservationModel, SourceModel)
            .join(SourceModel, SourceModel.source_id == ObservationModel.source_id)
            .where(
                ObservationModel.organization_id == organization_id,
                ObservationModel.observed_at_utc >= since,
                ObservationModel.quality_status != "rejected",
                ObservationModel.variable_code.in_(self.TRACKED),
            )
            .order_by(ObservationModel.observed_at_utc.asc())
        ).all())

        atual: dict[str, tuple[datetime, float, str]] = {}
        chuva_72h = 0.0
        umidade_minima: float | None = None
        temperatura_maxima: float | None = None
        for observation, source in rows:
            when = observation.observed_at_utc
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            valor = float(observation.value_canonical)
            code = observation.variable_code
            if code not in atual or when > atual[code][0]:
                atual[code] = (when, valor, source.source_name)
            if code == "rainfall_mm_1h":
                chuva_72h += valor
            if code == "humidity_pct" and (umidade_minima is None or valor < umidade_minima):
                umidade_minima = valor
            if code == "temperature_c" and (temperatura_maxima is None or valor > temperatura_maxima):
                temperatura_maxima = valor

        temperatura = atual.get("temperature_c", (None, None, None))[1]
        umidade = atual.get("humidity_pct", (None, None, None))[1]
        vento = atual.get("wind_speed_mps", (None, None, None))[1]

        indicadores: list[dict] = []

        if umidade is not None:
            nivel = _level_for(umidade, HUMIDITY_LEVELS, ascending=False)
            code, label, color = nivel or ("confortavel", "Dentro do conforto", "#16803c")
            indicadores.append({
                "key": "baixa_umidade",
                "title": "Umidade relativa do ar",
                "value": round(umidade, 0),
                "unit": "%",
                "level": code,
                "level_label": label,
                "color": color,
                "reference": "Níveis de atenção (<30%), alerta (<20%) e emergência (<12%) — INMET/Defesa Civil.",
                "extra": f"Mínima nas últimas 72 h: {umidade_minima:.0f}%" if umidade_minima is not None else None,
            })

        if temperatura is not None and umidade is not None:
            indice = _heat_index_c(temperatura, umidade)
            nivel = _level_for(indice, HEAT_LEVELS, ascending=True)
            code, label, color = nivel or ("normal", "Sem estresse térmico", "#16803c")
            indicadores.append({
                "key": "indice_calor",
                "title": "Índice de calor (sensação)",
                "value": indice,
                "unit": "°C",
                "level": code,
                "level_label": label,
                "color": color,
                "reference": "Índice de calor de Rothfusz (NOAA): cautela ≥27 °C, cautela extrema ≥32 °C, perigo ≥41 °C.",
                "extra": (
                    f"Ar a {temperatura:.1f} °C com {umidade:.0f}% de umidade"
                    + (f" · máxima de 72 h: {temperatura_maxima:.1f} °C" if temperatura_maxima is not None else "")
                ),
            })

        fogo = _fire_risk(temperatura, umidade, vento, chuva_72h)
        indicadores.append({
            "key": "risco_queimada",
            "title": "Risco de queimada e fumaça",
            "value": fogo["score"],
            "unit": "pts",
            "level": fogo["level"],
            "level_label": fogo["label"],
            "color": fogo["color"],
            "reference": "Combinação operacional de calor, umidade, vento e chuva acumulada (base FMA/Nesterov). Não substitui o risco oficial do INPE.",
            "extra": "; ".join(fogo["factors"]) or "Nenhum fator crítico identificado.",
        })

        material_particulado = atual.get("pm25_ugm3") or atual.get("pm10_ugm3")
        if material_particulado is not None:
            indicadores.append({
                "key": "qualidade_ar",
                "title": "Material particulado",
                "value": round(material_particulado[1], 1),
                "unit": "µg/m³",
                "level": "informativo",
                "level_label": "Monitoramento",
                "color": "#0e7490",
                "reference": "Padrões CONAMA 491/2018 e diretrizes OMS 2021.",
                "extra": f"Fonte: {material_particulado[2]}",
            })
        else:
            indicadores.append({
                "key": "qualidade_ar",
                "title": "Material particulado",
                "value": None,
                "unit": "µg/m³",
                "level": "sem_dado",
                "level_label": "Sem monitoramento",
                "color": "#5a7a80",
                "reference": "Requer conector MonitorAr/FEAM homologado ou estação municipal.",
                "extra": "Lacuna identificada: o município não dispõe de medição própria de qualidade do ar.",
            })

        nivel_umidade = next((i["level"] for i in indicadores if i["key"] == "baixa_umidade"), None)
        nivel_calor = next((i["level"] for i in indicadores if i["key"] == "indice_calor"), None)

        prioridades = {"emergencia": 4, "extremo": 4, "critico": 4, "alerta": 3, "perigo": 3, "alto": 3,
                       "atencao": 2, "cautela_extrema": 2, "moderado": 2, "cautela": 1}
        pior = max((prioridades.get(i["level"], 0) for i in indicadores), default=0)
        estado = {4: "critico", 3: "alerta", 2: "atencao", 1: "observacao", 0: "normal"}[pior]

        return {
            "generated_at_utc": now.isoformat(),
            "state": estado,
            "indicators": indicadores,
            "recommended_actions": _recommendations(nivel_umidade, nivel_calor, fogo["level"]),
            "vulnerable_groups": [
                "Crianças menores de 5 anos", "Pessoas idosas",
                "Pessoas com doenças respiratórias ou cardiovasculares",
                "População em situação de rua", "Trabalhadores expostos ao sol",
            ],
            "observations_considered": len(rows),
            "disclaimer": (
                "Indicadores calculados a partir das observações da plataforma. "
                "Apoiam decisão e comunicação; não substituem avaliação clínica "
                "nem alerta oficial de órgão competente."
            ),
        }


environmental_health_service = EnvironmentalHealthService()
