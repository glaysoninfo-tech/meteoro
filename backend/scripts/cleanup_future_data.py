"""Limpa o passivo da fila de qualidade causado por horas futuras do Open-Meteo.

Antes da correção do parser, horas de PREVISÃO eram gravadas como observação e
rejeitadas pela regra timestamp_future — inundando a fila de triagem. Este
script remove esse passivo. As previsões continuam disponíveis: o portal as lê
diretamente do payload bruto (public/model_forecast).

Uso (com o uvicorn parado, de dentro de backend/):
    python -m scripts.cleanup_future_data
"""

from __future__ import annotations

import sqlite3


def main() -> None:
    db = sqlite3.connect("meteoro_local.db")
    cursor = db.cursor()
    issues = cursor.execute(
        "DELETE FROM quality_issues WHERE flag_code = 'timestamp_future'"
    ).rowcount
    observations = cursor.execute(
        "DELETE FROM observations WHERE observed_at_utc > datetime('now', '+5 minutes')"
    ).rowcount
    db.commit()
    restantes = cursor.execute(
        "SELECT count(*) FROM quality_issues WHERE review_status = 'pending'"
    ).fetchone()[0]
    db.close()
    print(f"Removidos: {issues} issue(s) timestamp_future e {observations} observação(ões) futura(s).")
    print(f"Fila de qualidade pendente agora: {restantes} item(ns).")


if __name__ == "__main__":
    main()
