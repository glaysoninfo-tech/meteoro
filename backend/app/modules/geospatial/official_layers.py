from __future__ import annotations

import gzip
import json
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BETIM_BOUNDS = (-44.35, -20.10, -44.05, -19.82)
EMPTY = {"type": "FeatureCollection", "features": []}
_cache: tuple[float, dict] | None = None
_lock = threading.Lock()


def _arcgis(url: str, fields: str, where: str = "1=1") -> dict:
    xmin, ymin, xmax, ymax = BETIM_BOUNDS
    query = urlencode({
        "where": where, "geometry": f"{xmin},{ymin},{xmax},{ymax}",
        "geometryType": "esriGeometryEnvelope", "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects", "outFields": fields,
        "returnGeometry": "true", "outSR": "4326", "f": "geojson",
    })
    request = Request(f"{url}/query?{query}", headers={"Accept": "application/geo+json, application/json", "Accept-Encoding": "gzip", "User-Agent": "Meteoro-Betim/1.0"})
    with urlopen(request, timeout=35) as response:
        raw = response.read()
        if response.headers.get("Content-Encoding", "").lower() == "gzip":
            raw = gzip.decompress(raw)
    data = json.loads(raw.decode("utf-8-sig"))
    if data.get("type") != "FeatureCollection":
        raise ValueError(data.get("error", {}).get("message", "resposta geográfica inválida"))
    return data


PBH_STATIONS_CSV = (
    "https://ckan.pbh.gov.br/dataset/3f658c13-5e42-418b-af06-5914573f85b9/resource/"
    "f111d2bc-dfad-47e6-9ed0-9438da4d2cc9/download/20260701_est_hidrometeorologica.csv"
)


def _utm_to_wgs84(easting: float, northing: float, zone: int = 23, south: bool = True) -> tuple[float, float]:
    """Converte UTM (SIRGAS2000/WGS84) para latitude/longitude — sem dependências.

    O cadastro da PBH publica geometria em EPSG:31983 (UTM 23S).
    """
    import math

    a, f = 6378137.0, 1 / 298.257223563
    e2 = f * (2 - f)
    e1sq = e2 / (1 - e2)
    k0 = 0.9996
    x = easting - 500000.0
    y = northing - 10000000.0 if south else northing
    m = y / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    phi1 = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
    )
    n1 = a / math.sqrt(1 - e2 * math.sin(phi1) ** 2)
    t1 = math.tan(phi1) ** 2
    c1 = e1sq * math.cos(phi1) ** 2
    r1 = a * (1 - e2) / (1 - e2 * math.sin(phi1) ** 2) ** 1.5
    d = x / (n1 * k0)
    latitude = phi1 - (n1 * math.tan(phi1) / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * e1sq) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * e1sq - 3 * c1**2) * d**6 / 720
    )
    longitude = (
        d
        - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * e1sq + 24 * t1**2) * d**5 / 120
    ) / math.cos(phi1)
    central_meridian = math.radians(zone * 6 - 183)
    return (math.degrees(latitude), math.degrees(longitude + central_meridian))


def _pbh_defesa_civil_stations() -> dict:
    """Rede hidrometeorológica da Defesa Civil de BH (cadastro CKAN/PRODABEL).

    ATENÇÃO: o dataset publica APENAS a localização das estações — não contém
    medições de chuva ou nível. Serve como camada de referência regional e
    como modelo institucional para uma rede municipal própria de Betim.
    """
    import csv
    import io
    import re

    request = Request(
        PBH_STATIONS_CSV,
        headers={"Accept": "text/csv", "Accept-Encoding": "gzip", "User-Agent": "Meteoro-Betim/1.0"},
    )
    with urlopen(request, timeout=35) as response:
        raw = response.read()
        if response.headers.get("Content-Encoding", "").lower() == "gzip" or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
    text = raw.decode("utf-8-sig", errors="replace")
    features: list[dict] = []
    for row in csv.DictReader(io.StringIO(text), delimiter=";"):
        match = re.search(r"POINT\s*\(([-\d.]+)\s+([-\d.]+)\)", row.get("GEOMETRIA", "") or "")
        if not match:
            continue
        latitude, longitude = _utm_to_wgs84(float(match.group(1)), float(match.group(2)))
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
            "properties": {
                "codigo": row.get("CODIGO"),
                "bacia": row.get("NOME_BACIA_HIDROGRAFICA"),
                "tipo": row.get("TIPO_ESTACAO"),
                "altitude": row.get("ALTITUDE"),
                "referencia": row.get("REFERENCIA_LOCALIZACAO"),
            },
        })
    return {"type": "FeatureCollection", "features": features}


def _load_source(name: str, source: str, loader) -> tuple[dict, dict]:
    try:
        data = loader()
        return data, {"available": True, "count": len(data.get("features", [])), "source": source}
    except Exception as exc:
        return dict(EMPTY), {"available": False, "count": 0, "source": source, "detail": str(exc)[:180]}


def official_layers() -> dict:
    global _cache
    now = time.monotonic()
    with _lock:
        if _cache and now - _cache[0] < 600:
            return _cache[1]
        hydro, hydro_status = _load_source(
            "hydrography", "ANA / SNIRH",
            lambda: _arcgis("https://www.snirh.gov.br/arcgis/rest/services/SPR/BHO2017_50K_TRECHODRENAGEM/FeatureServer/0", "OBJECTID,NORIOCOMP,NOGENERICO,NUSTRAHLER"),
        )
        gauges, gauge_status = _load_source(
            "rain_gauges", "CEMADEN / Infraestrutura de Dados Espaciais de MG",
            lambda: _arcgis("https://observatorio.infraestrutura.mg.gov.br/server/rest/services/00_PUBLICACOES/cemaden_estacoes_pluviometricas/FeatureServer/1", "data,acumulado,cidade,codestacao,nomeestacao,latitude,longitude"),
        )
        river_gauges, river_gauge_status = _load_source(
            "river_gauges", "ANA / SNIRH — Rede Hidrometeorológica Nacional",
            lambda: _arcgis(
                "https://portal1.snirh.gov.br/server/rest/services/Esta%C3%A7%C3%B5es_Hidrometeorol%C3%B3gicas_SNIRH/FeatureServer/0",
                "Codigo,Nome,TipoEstacao,Operando,Municipio,Rio,ResponsavelSigla,OperadoraSigla,EscalaNivel,RegistradorNivel,MedicaoDescargaLiquida,EstacaoTelemetrica,DataAlteracao",
                "TipoEstacao='Fluviométrica'",
            ),
        )
        pbh_stations, pbh_status = _load_source(
            "pbh_stations", "Defesa Civil BH / PRODABEL (cadastro)",
            _pbh_defesa_civil_stations,
        )
        pbh_status["data_kind"] = "cadastro_sem_medicoes"
        fire_status = {"available": False, "count": 0, "source": "INPE / Programa Queimadas", "detail": "Serviço geográfico oficial temporariamente indisponível."}
        result = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "bounds": BETIM_BOUNDS,
            "hydrography": hydro, "rain_gauges": gauges, "river_gauges": river_gauges,
            "pbh_stations": pbh_stations, "fire_hotspots": dict(EMPTY),
            "status": {"hydrography": hydro_status, "rain_gauges": gauge_status, "river_gauges": river_gauge_status, "pbh_stations": pbh_status, "fire_hotspots": fire_status},
        }
        _cache = (now, result)
        return result
