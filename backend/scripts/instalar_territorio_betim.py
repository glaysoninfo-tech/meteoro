"""Instala o território oficial de Betim (malha municipal IBGE) no mapa público.

Substitui o retângulo demonstrativo "Centro (demonstração)" — que passava a
mensagem errada de cobertura apenas central — pelo limite municipal completo,
incluindo toda a periferia. Fonte: API de malhas do IBGE (código 3106705).

Uso (com o uvicorn PARADO, de dentro de backend/):
    python -m scripts.instalar_territorio_betim
"""

from __future__ import annotations

import json
import sqlite3
import urllib.request
import uuid
from datetime import datetime, timezone

IBGE_BETIM = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/municipios/3106705"
    "?formato=application/vnd.geo+json"
)


def main() -> None:
    print("Baixando malha municipal de Betim no IBGE…")
    with urllib.request.urlopen(IBGE_BETIM, timeout=30) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))

    if payload.get("type") == "FeatureCollection":
        geometry = payload["features"][0]["geometry"]
    elif payload.get("type") in {"Polygon", "MultiPolygon"}:
        geometry = payload
    else:
        raise SystemExit(f"Resposta inesperada do IBGE: {payload.get('type')}")
    geometry_json = json.dumps(geometry, ensure_ascii=False)

    db = sqlite3.connect("meteoro_local.db")
    cursor = db.cursor()
    organization_id = cursor.execute(
        "SELECT organization_id FROM organizations LIMIT 1"
    ).fetchone()[0]
    now = datetime.now(tz=timezone.utc).isoformat()

    existing = cursor.execute(
        "SELECT territory_id FROM territories WHERE territory_code = 'BETIM'"
    ).fetchone()
    if existing:
        cursor.execute(
            "UPDATE territories SET geometry_geojson = ?, geometry = ?, status = 'active', "
            "updated_at = ? WHERE territory_code = 'BETIM'",
            (geometry_json, geometry_json, now),
        )
        print("Território BETIM atualizado com a malha IBGE.")
    else:
        cursor.execute(
            "INSERT INTO territories (territory_id, organization_id, territory_code, "
            "territory_name, territory_type, status, geometry_geojson, geometry, "
            "created_at, updated_at) VALUES (?, ?, 'BETIM', 'Betim', 'municipio', "
            "'active', ?, ?, ?, ?)",
            (str(uuid.uuid4()), organization_id, geometry_json, geometry_json, now, now),
        )
        print("Território BETIM (município completo) criado.")

    demo = cursor.execute(
        "UPDATE territories SET status = 'inactive', updated_at = ? "
        "WHERE territory_code = 'CENTRO' AND territory_name LIKE '%demonstra%'",
        (now,),
    ).rowcount
    if demo:
        print("Território demonstrativo 'Centro' desativado (sai do mapa público).")

    db.commit()
    db.close()
    print("\nPronto: o mapa público passa a mostrar o limite municipal inteiro de Betim.")


if __name__ == "__main__":
    main()
