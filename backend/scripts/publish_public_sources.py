"""Publica na superfície cidadã as fontes aprovadas para exibição pública.

O portal público só exibe dados de fontes com classification "public" ou
"public_aggregate" — decisão explícita de governança. Este script marca as
fontes de demonstração/modelo de Betim como públicas, destravando:
condições atuais, previsão 24h e resumo diário do portal.

Uso (com o uvicorn parado, de dentro de backend/):
    python -m scripts.publish_public_sources
"""

from __future__ import annotations

import json
import sqlite3

# Fontes aprovadas para a superfície pública (nome exato no catálogo).
APPROVED_PUBLIC_SOURCES = (
    "Betim — estimativa e previsão horária de modelo",
    "Leituras da estação Centro (demonstração)",
)


def main() -> None:
    db = sqlite3.connect("meteoro_local.db")
    cursor = db.cursor()
    updated = 0
    for source_name in APPROVED_PUBLIC_SOURCES:
        row = cursor.execute(
            "SELECT source_id, connector_config_json FROM sources WHERE source_name = ?",
            (source_name,),
        ).fetchone()
        if row is None:
            print(f"AVISO: fonte não encontrada: {source_name}")
            continue
        source_id, config_json = row
        config = json.loads(config_json or "{}")
        if config.get("classification") == "public":
            print(f"já pública: {source_name}")
            continue
        config["classification"] = "public"
        cursor.execute(
            "UPDATE sources SET connector_config_json = ? WHERE source_id = ?",
            (json.dumps(config, ensure_ascii=False), source_id),
        )
        updated += 1
        print(f"publicada: {source_name}")
    db.commit()
    db.close()
    print(f"\n{updated} fonte(s) publicada(s). Reinicie a API e recarregue o portal público.")


if __name__ == "__main__":
    main()
