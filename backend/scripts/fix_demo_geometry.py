"""Reposiciona os dados demonstrativos de São Paulo para Betim/MG.

Uso (com o uvicorn parado, de dentro de backend/):
    python -m scripts.fix_demo_geometry

Idempotente: pode rodar mais de uma vez sem efeito colateral.
"""

from __future__ import annotations

import json
import sqlite3

BETIM_POLYGON = json.dumps(
    {
        "type": "Polygon",
        "coordinates": [
            [
                [-44.225, -19.995],
                [-44.170, -19.995],
                [-44.170, -19.945],
                [-44.225, -19.945],
                [-44.225, -19.995],
            ]
        ],
    }
)
BETIM_POINT = json.dumps({"type": "Point", "coordinates": [-44.198, -19.968]})


def main() -> None:
    db = sqlite3.connect("meteoro_local.db")
    cursor = db.cursor()
    territories = cursor.execute(
        "UPDATE territories SET geometry_geojson = ?, geometry = ? WHERE territory_code = 'CENTRO'",
        (BETIM_POLYGON, BETIM_POLYGON),
    ).rowcount
    stations = cursor.execute(
        "UPDATE stations SET location_geojson = ?, location = ?, elevation_meters = 831 "
        "WHERE station_code = 'EST-CENTRO-01'",
        (BETIM_POINT, BETIM_POINT),
    ).rowcount
    alerts = cursor.execute(
        "UPDATE official_alerts SET geometry_geojson = ? WHERE alert_code = 'DEMO-CALOR-01'",
        (BETIM_POLYGON,),
    ).rowcount
    db.commit()
    db.close()
    print(f"Atualizados: {territories} território(s), {stations} estação(ões), {alerts} alerta(s).")
    print("Dados demonstrativos agora centrados em Betim/MG (-19.968, -44.198).")


if __name__ == "__main__":
    main()
