"""Perfis de pontos regionais para contextualização de Betim.

As coordenadas representam sedes municipais para consulta de modelo. Elas não
substituem estações e não autorizam afirmar que uma condição ocorreu em todo o
município. Produtos derivados devem conservar `method=model_contextual` e a
lista de fontes utilizadas.
"""

from __future__ import annotations

import json

from app.modules.catalog.schemas import SourceCreate


REGIONAL_CONTEXT_LOCATIONS: tuple[tuple[str, str, float, float], ...] = (
    ("BELO_HORIZONTE", "Belo Horizonte/MG", -19.9167, -43.9345),
    ("CONTAGEM", "Contagem/MG", -19.9317, -44.0536),
    ("PARA_DE_MINAS", "Pará de Minas/MG", -19.8606, -44.6083),
    ("BRUMADINHO", "Brumadinho/MG", -20.1436, -44.2003),
    ("DIVINOPOLIS", "Divinópolis/MG", -20.1389, -44.8839),
    ("IGARAPE", "Igarapé/MG", -20.0700, -44.3017),
    ("IBIRITE", "Ibirité/MG", -20.0219, -44.0589),
    ("SARZEDO", "Sarzedo/MG", -20.0353, -44.1448),
    ("MARIO_CAMPOS", "Mário Campos/MG", -20.0589, -44.1881),
    ("ESMERALDAS", "Esmeraldas/MG", -19.7625, -44.3136),
    ("JUATUBA", "Juatuba/MG", -19.9447, -44.3422),
    ("SAO_JOAQUIM_DE_BICAS", "São Joaquim de Bicas/MG", -20.0497, -44.2739),
)


def regional_context_profiles() -> list[SourceCreate]:
    """Build one independently auditable source per reference municipality."""
    profiles: list[SourceCreate] = []
    for minute, (code, name, latitude, longitude) in enumerate(REGIONAL_CONTEXT_LOCATIONS, start=6):
        query = (
            f"latitude={latitude}&longitude={longitude}"
            "&hourly=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m"
            "&timezone=UTC&past_days=1&forecast_days=1"
        )
        config = {
            "parser": "open_meteo",
            "station_code": f"MODEL_{code}",
            "classification": "model_contextual",
            "purpose": "regional_context_for_betim",
            "schedule": {"minute_utc": minute},
        }
        profiles.append(
            SourceCreate(
                institution_name="Open-Meteo",
                source_name=f"Contexto regional — {name} (modelo horário)",
                source_type="meteorology_model",
                access_method="http",
                authentication_type="none",
                endpoint_reference=f"https://api.open-meteo.com/v1/forecast?{query}",
                connector_config_json=json.dumps(config, ensure_ascii=False),
                status="active",
                expected_frequency_minutes=60,
                criticality="low",
            )
        )
    return profiles


def betim_open_meteo_profiles() -> list[SourceCreate]:
    """Profiles requested for Betim's hourly model context and historical runs."""
    forecast_config = {
        "parser": "open_meteo",
        "station_code": "BETIM_MODEL_POINT",
        "classification": "model_contextual",
        "schedule": {"minute_utc": 5},
    }
    archive_config = {
        "parser": "open_meteo",
        "station_code": "BETIM_MODEL_POINT",
        "classification": "model_contextual",
        "schedule": {"enabled": False},
        "reprocess": {"start_query_param": "start_date", "end_query_param": "end_date"},
    }
    hourly = "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m"
    return [
        SourceCreate(
            institution_name="Open-Meteo",
            source_name="Betim — estimativa e previsão horária de modelo",
            source_type="meteorology_model",
            access_method="http",
            authentication_type="none",
            endpoint_reference=(
                "https://api.open-meteo.com/v1/forecast?latitude=-19.9676&longitude=-44.1983"
                # forecast_days=2 garante 24h completas de previsão pública a
                # qualquer hora do dia (com 1, a partir do meio-dia o horizonte encurta).
                f"&hourly={hourly}&timezone=UTC&past_days=1&forecast_days=2"
            ),
            connector_config_json=json.dumps(forecast_config, ensure_ascii=False),
            status="active",
            expected_frequency_minutes=60,
            criticality="low",
        ),
        SourceCreate(
            institution_name="Open-Meteo",
            source_name="Betim — histórico de modelo para reprocessamento",
            source_type="meteorology_model_historical",
            access_method="http",
            authentication_type="none",
            endpoint_reference=(
                "https://archive-api.open-meteo.com/v1/archive?latitude=-19.9676&longitude=-44.1983"
                f"&hourly={hourly}&timezone=UTC"
            ),
            connector_config_json=json.dumps(archive_config, ensure_ascii=False),
            status="active",
            expected_frequency_minutes=1440,
            criticality="low",
        ),
    ]


# Estações automáticas do INMET mais próximas de Betim. O município não possui
# estação automática própria do INMET; estas são as vizinhas imediatas da
# região metropolitana — observação REGIONAL, nunca "medição de bairro de Betim".
INMET_REGIONAL_STATIONS: tuple[tuple[str, str], ...] = (
    ("A555", "Ibirité — Rola-Moça"),
    ("A521", "Belo Horizonte — Pampulha"),
    ("A537", "Belo Horizonte — Cercadinho"),
    ("A535", "Florestal"),
)


def inmet_regional_stations_profiles() -> list[SourceCreate]:
    """Observação horária real das estações automáticas INMET vizinhas.

    classification=public: alimentam os cartões públicos como 'Observação',
    complementando a estimativa de modelo do Open-Meteo.
    """
    profiles: list[SourceCreate] = []
    for offset, (code, name) in enumerate(INMET_REGIONAL_STATIONS):
        config = {
            "parser": "inmet",
            "station_code": code,
            "classification": "public",
            "purpose": "regional_observation_for_betim",
            "timeout_seconds": 25,
            "retry_attempts": 3,
            "schedule": {"minute_utc": 12 + offset * 2},
        }
        profiles.append(
            SourceCreate(
                institution_name="INMET",
                source_name=f"INMET — estação automática {code} ({name})",
                source_type="weather_station_observation",
                access_method="http",
                authentication_type="none",
                endpoint_reference=(
                    "https://apitempo.inmet.gov.br/estacao/"
                    "{DATA_ONTEM_ISO}/{DATA_HOJE_ISO}/" + code
                ),
                connector_config_json=json.dumps(config, ensure_ascii=False),
                status="active",
                expected_frequency_minutes=60,
                criticality="medium",
            )
        )
    return profiles


def ana_hidroweb_profiles(station_codes: list[str]) -> list[SourceCreate]:
    """Telemetria fluviométrica da ANA por código de estação.

    O operador obtém o código na camada 'Réguas fluviométricas (ANA)' do mapa
    operacional (popup mostra 'Código ANA'). Nível em cm vira river_level_m e
    alimenta os limiares river_level_high/critical do módulo de planejamento.
    """
    profiles: list[SourceCreate] = []
    for code in station_codes:
        clean = str(code).strip()
        if not clean.isdigit() or not (6 <= len(clean) <= 10):
            raise ValueError(
                f"Código de estação ANA inválido: '{code}'. Use o código numérico "
                "exibido no popup da camada de réguas fluviométricas."
            )
        config = {
            "parser": "ana_hidroweb",
            "station_code": f"ANA_{clean}",
            "classification": "internal_operational",
            "purpose": "river_level_monitoring_for_flood_response",
            "timezone_offset_hours": -3,
            "timeout_seconds": 25,
            "retry_attempts": 3,
            "schedule": {"minute_utc": 20},
        }
        profiles.append(
            SourceCreate(
                institution_name="ANA / HidroWeb Telemetria",
                source_name=f"ANA — telemetria fluviométrica {clean}",
                source_type="hydrology_telemetry",
                access_method="http",
                authentication_type="none",
                endpoint_reference=(
                    "https://telemetriaws1.ana.gov.br/ServiceANA.asmx/DadosHidrometeorologicos"
                    f"?CodEstacao={clean}"
                    "&DataInicio={DATA_ONTEM_BR}&DataFim={DATA_HOJE_BR}"
                ),
                connector_config_json=json.dumps(config, ensure_ascii=False),
                status="active",
                expected_frequency_minutes=60,
                criticality="high",
            )
        )
    return profiles


def redemet_aviation_profiles() -> list[SourceCreate]:
    """Perfis REDEMET para contexto aeronáutico regional, nunca alerta municipal.

    SBBH (Pampulha) e SNDV (Divinópolis) são coletados separadamente: cada
    payload conserva ICAO, horário de coleta e resultado de sua própria fonte.
    A chave permanece exclusivamente no ambiente do worker/backend.
    """
    profiles: list[SourceCreate] = []
    airports = (
        ("SBBH", "Belo Horizonte — Pampulha", -19.8519, -43.9506),
        ("SNDV", "Divinópolis — Brigadeiro Antônio Cabral", -20.1817, -44.8700),
    )
    for icao, name, latitude, longitude in airports:
        common = {
            "api_key_header": "X-Api-Key",
            "api_key_env_var": "REDEMET_API_KEY",
            "icao": icao,
            "airport_name": name,
            "latitude": latitude,
            "longitude": longitude,
            "classification": "aviation_regional_context",
            "purpose": "regional_aviation_context_for_betim",
            "timeout_seconds": 15,
            "retry_attempts": 3,
            "max_response_bytes": 1_048_576,
        }
        status_config = {**common, "parser": "redemet_status"}
        profiles.append(
            SourceCreate(
                institution_name="REDEMET / DECEA",
                source_name=f"REDEMET — status aeronáutico {icao}",
                source_type="aviation_aerodrome_status",
                access_method="http",
                authentication_type="api_key_env",
                endpoint_reference=(
                    "https://api-redemet.decea.mil.br/aerodromos/status/"
                    f"localidades/{icao}"
                ),
                connector_config_json=json.dumps(status_config, ensure_ascii=False),
                status="active",
                expected_frequency_minutes=15,
                criticality="medium",
            )
        )
        metar_config = {**common, "parser": "redemet_metar"}
        profiles.append(
            SourceCreate(
                institution_name="REDEMET / DECEA",
                source_name=f"REDEMET — METAR/SPECI {icao}",
                source_type="aviation_metar",
                access_method="http",
                authentication_type="api_key_env",
                endpoint_reference=f"https://api-redemet.decea.mil.br/mensagens/metar/{icao}",
                connector_config_json=json.dumps(metar_config, ensure_ascii=False),
                status="active",
                expected_frequency_minutes=30,
                criticality="medium",
            )
        )
    return profiles


def redemet_imagery_profiles() -> list[SourceCreate]:
    """Camadas visuais REDEMET para o mapa operacional.

    O radar é uma imagem de eco, não uma medição de chuva no solo. O satélite
    é uma imagem remota; ambos permanecem visualizações contextuais.
    """
    common = {
        "api_key_header": "X-Api-Key",
        "api_key_env_var": "REDEMET_API_KEY",
        "parser": "redemet_imagery",
        "classification": "remote_sensing_context",
        "purpose": "visual_weather_context_for_betim",
        "timeout_seconds": 20,
        "retry_attempts": 3,
        "max_response_bytes": 1_048_576,
    }
    return [
        SourceCreate(
            institution_name="REDEMET / DECEA",
            source_name="REDEMET — satélite infravermelho realçado",
            source_type="satellite_imagery",
            access_method="http",
            authentication_type="api_key_env",
            endpoint_reference="https://api-redemet.decea.mil.br/produtos/satelite/realcada?anima=1",
            connector_config_json=json.dumps({**common, "image_kind": "satellite", "product": "realcada"}, ensure_ascii=False),
            status="active",
            expected_frequency_minutes=15,
            criticality="low",
        ),
        SourceCreate(
            institution_name="REDEMET / DECEA",
            source_name="REDEMET — radar MaxCAPPI Minas Gerais",
            source_type="radar_imagery",
            access_method="http",
            authentication_type="api_key_env",
            endpoint_reference="https://api-redemet.decea.mil.br/produtos/radar/maxcappi?area=st&anima=1",
            connector_config_json=json.dumps({**common, "image_kind": "radar", "product": "maxcappi", "radar_area": "st"}, ensure_ascii=False),
            status="active",
            expected_frequency_minutes=15,
            criticality="medium",
        ),
    ]
