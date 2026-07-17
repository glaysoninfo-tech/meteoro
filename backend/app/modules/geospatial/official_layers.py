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
        fire_status = {"available": False, "count": 0, "source": "INPE / Programa Queimadas", "detail": "Serviço geográfico oficial temporariamente indisponível."}
        result = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "bounds": BETIM_BOUNDS,
            "hydrography": hydro, "rain_gauges": gauges, "river_gauges": river_gauges, "fire_hotspots": dict(EMPTY),
            "status": {"hydrography": hydro_status, "rain_gauges": gauge_status, "river_gauges": river_gauge_status, "fire_hotspots": fire_status},
        }
        _cache = (now, result)
        return result
