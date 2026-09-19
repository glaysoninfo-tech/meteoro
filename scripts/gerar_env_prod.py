"""Gera infra/docker/.env.prod com segredos fortes a partir do modelo.

Uso (da raiz do repositório):
    python scripts/gerar_env_prod.py

Não sobrescreve um .env.prod existente. Os segredos são aleatórios e ficam
apenas no arquivo local, que nunca é versionado.
"""

from __future__ import annotations

import secrets
import string
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MODELO = RAIZ / "infra" / "docker" / ".env.prod.example"
DESTINO = RAIZ / "infra" / "docker" / ".env.prod"


def senha(tamanho: int = 32) -> str:
    """Senha forte sem caracteres que atrapalham URLs de conexão."""
    alfabeto = string.ascii_letters + string.digits
    return "".join(secrets.choice(alfabeto) for _ in range(tamanho))


def main() -> None:
    if not MODELO.is_file():
        raise SystemExit(f"Modelo não encontrado: {MODELO}")
    if DESTINO.exists():
        raise SystemExit(
            f"{DESTINO} já existe. Apague-o manualmente se quiser regerar os segredos."
        )

    postgres = senha()
    redis = senha()
    minio = senha()
    grafana = senha(20)
    jwt = secrets.token_urlsafe(48)

    linhas: list[str] = []
    for linha in MODELO.read_text(encoding="utf-8").splitlines():
        if linha.startswith("JWT_SECRET_KEY="):
            linha = f"JWT_SECRET_KEY={jwt}"
        elif linha.startswith("POSTGRES_PASSWORD="):
            linha = f"POSTGRES_PASSWORD={postgres}"
        elif linha.startswith("DATABASE_URL="):
            linha = f"DATABASE_URL=postgresql+psycopg://meteoro:{postgres}@postgres:5432/meteoro"
        elif linha.startswith("REDIS_PASSWORD="):
            linha = f"REDIS_PASSWORD={redis}"
        elif linha.startswith("REDIS_URL="):
            linha = f"REDIS_URL=redis://:{redis}@redis:6379/0"
        elif linha.startswith("MINIO_ROOT_PASSWORD="):
            linha = f"MINIO_ROOT_PASSWORD={minio}"
        elif linha.startswith("GRAFANA_ADMIN_PASSWORD="):
            linha = f"GRAFANA_ADMIN_PASSWORD={grafana}"
        linhas.append(linha)

    DESTINO.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f"Criado: {DESTINO}")
    print("\nSegredos gerados (guarde em local seguro):")
    print(f"  Grafana  usuário: meteoro  senha: {grafana}")
    print("\nAinda é preciso preencher manualmente:")
    print("  REDEMET_API_KEY=  (chave do portal REDEMET)")
    print("  PUBLIC_ORGANIZATION_ID=  (após o primeiro bootstrap-admin)")
    print("  OPENAI_API_KEY=  (opcional, para o resumo diário assistido por IA)")


if __name__ == "__main__":
    main()
