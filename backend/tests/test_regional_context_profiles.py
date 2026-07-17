import json

from app.modules.catalog.regional_context import betim_open_meteo_profiles, redemet_aviation_profiles, redemet_imagery_profiles, regional_context_profiles


def test_regional_context_profiles_cover_requested_municipalities_and_stagger_schedule() -> None:
    profiles = regional_context_profiles()

    assert len(profiles) == 12
    assert "Belo Horizonte/MG" in {profile.source_name.split(" — ")[1].split(" (modelo")[0] for profile in profiles}
    assert "São Joaquim de Bicas/MG" in {profile.source_name.split(" — ")[1].split(" (modelo")[0] for profile in profiles}
    assert len({profile.connector_config_json for profile in profiles}) == 12
    assert all("model_contextual" in (profile.connector_config_json or "") for profile in profiles)


def test_betim_open_meteo_profiles_keep_hourly_and_manual_history_separate() -> None:
    forecast, archive = betim_open_meteo_profiles()

    assert forecast.expected_frequency_minutes == 60
    assert json.loads(forecast.connector_config_json or "{}")["schedule"] == {"minute_utc": 5}
    assert "archive-api.open-meteo.com" in archive.endpoint_reference
    assert json.loads(archive.connector_config_json or "{}")["schedule"]["enabled"] is False


def test_redemet_profiles_use_environment_key_and_separate_icao_sources() -> None:
    profiles = redemet_aviation_profiles()
    assert len(profiles) == 4
    assert {profile.authentication_type for profile in profiles} == {"api_key_env"}
    assert {"SBBH", "SNDV"} == {json.loads(profile.connector_config_json or "{}")["icao"] for profile in profiles}
    assert all("api_key=" not in profile.endpoint_reference for profile in profiles)


def test_redemet_imagery_profiles_are_authenticated_and_have_distinct_products() -> None:
    satellite, radar = redemet_imagery_profiles()
    assert satellite.authentication_type == radar.authentication_type == "api_key_env"
    assert "produtos/satelite/realcada" in satellite.endpoint_reference
    assert "produtos/radar/maxcappi" in radar.endpoint_reference
    assert json.loads(radar.connector_config_json or "{}")["radar_area"] == "st"
