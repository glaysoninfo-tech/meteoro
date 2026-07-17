"""Vendoriza as bibliotecas do portal (Leaflet + leaflet.heat).

Baixa as versões fixadas para frontend/vendor/, eliminando a dependência de
CDN externa — o mapa operacional precisa funcionar com a internet degradada.

Uso (da raiz do repositório):
    python scripts/vendorize_frontend.py

Idempotente; grava vendor-manifest.json com o SHA-256 de cada arquivo.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

LEAFLET_VERSION = "1.9.4"
BASE = Path(__file__).resolve().parents[1] / "frontend" / "vendor"

FILES: dict[str, str] = {
    f"https://unpkg.com/leaflet@{LEAFLET_VERSION}/dist/leaflet.js": "leaflet/leaflet.js",
    f"https://unpkg.com/leaflet@{LEAFLET_VERSION}/dist/leaflet.css": "leaflet/leaflet.css",
    f"https://unpkg.com/leaflet@{LEAFLET_VERSION}/dist/images/layers.png": "leaflet/images/layers.png",
    f"https://unpkg.com/leaflet@{LEAFLET_VERSION}/dist/images/layers-2x.png": "leaflet/images/layers-2x.png",
    f"https://unpkg.com/leaflet@{LEAFLET_VERSION}/dist/images/marker-icon.png": "leaflet/images/marker-icon.png",
    f"https://unpkg.com/leaflet@{LEAFLET_VERSION}/dist/images/marker-icon-2x.png": "leaflet/images/marker-icon-2x.png",
    f"https://unpkg.com/leaflet@{LEAFLET_VERSION}/dist/images/marker-shadow.png": "leaflet/images/marker-shadow.png",
    "https://unpkg.com/leaflet.heat/dist/leaflet-heat.js": "leaflet-heat.js",
}


def main() -> None:
    manifest: dict[str, str] = {}
    for url, relative in FILES.items():
        destination = BASE / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        print(f"baixando {url}")
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
            payload = response.read()
        destination.write_bytes(payload)
        manifest[relative] = hashlib.sha256(payload).hexdigest()
    (BASE / "vendor-manifest.json").write_text(
        json.dumps(
            {"leaflet_version": LEAFLET_VERSION, "sha256": manifest},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nOK: {len(FILES)} arquivos em frontend/vendor/ (manifest com SHA-256 gravado).")


if __name__ == "__main__":
    main()
