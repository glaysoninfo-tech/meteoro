from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.settings import settings
from tests.conftest import bootstrap_admin


def test_public_open_data_metadata_exposes_dictionary_and_license_state(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = bootstrap_admin(client)
    current_user = client.get("/api/v1/auth/me", headers=headers)
    assert current_user.status_code == 200, current_user.text
    monkeypatch.setattr(settings, "public_organization_id", current_user.json()["organization_id"])
    monkeypatch.setattr(settings, "public_open_data_license_name", None)

    response = client.get("/api/v1/public/open-data/metadata")

    assert response.status_code == 200, response.text
    metadata = response.json()
    assert metadata["dataset_id"] == "meteoro-observacoes-normalizadas"
    assert metadata["publication_status"] == "license_pending"
    assert any(field["name"] == "quality_status" for field in metadata["fields"])
