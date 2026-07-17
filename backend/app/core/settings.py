import os

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_JWT_DEFAULT = "change-this-secret-in-production"
MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    app_name: str = "Meteoro API"
    app_version: str = "0.1.0"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://meteoro:meteoro@localhost:5432/meteoro"
    auth_mode: str = "local"
    jwt_secret_key: str = INSECURE_JWT_DEFAULT
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_hours: int = 8
    keycloak_issuer_url: str | None = None
    keycloak_jwks_url: str | None = None
    keycloak_audience: str | None = None
    keycloak_jwt_algorithm: str = "RS256"
    ingestion_http_timeout_seconds: int = 30
    ingestion_http_retry_attempts: int = 3
    ingestion_http_retry_backoff_seconds: float = 0.5
    ingestion_http_max_response_bytes: int = 25 * 1024 * 1024
    ingestion_http_allowed_schemes: str = "https"
    ingestion_network_allowed_hosts: str = ""
    ingestion_network_allowed_ports: str = "443,1883,4840"
    ingestion_s3_allowed_buckets: str = ""
    ingestion_mqtt_capture_timeout_seconds: int = 30
    ingestion_opcua_timeout_seconds: int = 15
    ingestion_storage_path: str = "../data/raw"
    ingestion_max_upload_bytes: int = 25 * 1024 * 1024
    ingestion_upload_chunk_bytes: int = 1024 * 1024
    ingestion_scheduler_enabled: bool = False
    ingestion_scheduler_poll_seconds: int = 60
    redis_url: str = "redis://localhost:6379/0"
    ingestion_worker_queue_name: str = "meteoro:ingestion:jobs"
    ingestion_worker_poll_seconds: int = 5
    ingestion_worker_lock_ttl_seconds: int = 300
    public_organization_id: str | None = None
    # Rate limit por IP dos endpoints públicos (janela fixa de 60 s).
    public_rate_limit_enabled: bool = True
    public_rate_limit_per_minute: int = 120
    public_csv_rate_limit_per_minute: int = 10
    # Usados por app/core/health.py (readiness_report) — Etapa 5 do plano.
    readiness_require_redis: bool = False
    readiness_redis_timeout_seconds: float = 2.0
    # Chave da REDEMET/DECEA lida do ambiente pelos conectores (api_key_env_var).
    # Declarada aqui para que a presença de REDEMET_API_KEY no .env não derrube o boot.
    redemet_api_key: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_production_safety(self) -> "Settings":
        """Em produção, a aplicação NÃO SOBE com segredo default ou fraco."""
        if self.environment.strip().lower() == "production":
            if self.jwt_secret_key == INSECURE_JWT_DEFAULT:
                raise ValueError(
                    "ENVIRONMENT=production exige JWT_SECRET_KEY próprio: o valor "
                    "default do repositório não é permitido. Gere um segredo forte "
                    "(ex.: python -c \"import secrets; print(secrets.token_urlsafe(48))\") "
                    "e defina-o no ambiente."
                )
            if len(self.jwt_secret_key) < MIN_JWT_SECRET_LENGTH:
                raise ValueError(
                    f"ENVIRONMENT=production exige JWT_SECRET_KEY com pelo menos "
                    f"{MIN_JWT_SECRET_LENGTH} caracteres (atual: {len(self.jwt_secret_key)})."
                )
        return self

    @field_validator("auth_mode")
    @classmethod
    def validate_auth_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed = {"local", "hybrid", "keycloak"}
        if normalized not in allowed:
            allowed_modes = ", ".join(sorted(allowed))
            raise ValueError(f"auth_mode inválido '{value}'. Use: {allowed_modes}.")
        return normalized

    @field_validator("ingestion_http_timeout_seconds")
    @classmethod
    def validate_ingestion_http_timeout_seconds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("ingestion_http_timeout_seconds deve ser maior que zero.")
        return value

    @field_validator("ingestion_mqtt_capture_timeout_seconds")
    @classmethod
    def validate_ingestion_mqtt_capture_timeout_seconds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("ingestion_mqtt_capture_timeout_seconds deve ser maior que zero.")
        return value

    @field_validator("ingestion_opcua_timeout_seconds")
    @classmethod
    def validate_ingestion_opcua_timeout_seconds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("ingestion_opcua_timeout_seconds deve ser maior que zero.")
        return value

    @field_validator("ingestion_scheduler_poll_seconds")
    @classmethod
    def validate_ingestion_scheduler_poll_seconds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("ingestion_scheduler_poll_seconds deve ser maior que zero.")
        return value

    @field_validator("ingestion_worker_poll_seconds", "ingestion_worker_lock_ttl_seconds")
    @classmethod
    def validate_worker_positive_seconds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Os intervalos do worker devem ser maiores que zero.")
        return value

    @field_validator("ingestion_http_retry_attempts")
    @classmethod
    def validate_ingestion_http_retry_attempts(cls, value: int) -> int:
        if value < 1 or value > 10:
            raise ValueError("ingestion_http_retry_attempts deve estar entre 1 e 10.")
        return value

    @field_validator("ingestion_http_retry_backoff_seconds")
    @classmethod
    def validate_ingestion_http_retry_backoff_seconds(cls, value: float) -> float:
        if value < 0 or value > 30:
            raise ValueError("ingestion_http_retry_backoff_seconds deve estar entre 0 e 30.")
        return value

    @field_validator("ingestion_http_max_response_bytes")
    @classmethod
    def validate_ingestion_http_max_response_bytes(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("ingestion_http_max_response_bytes deve ser maior que zero.")
        return value

    @field_validator("ingestion_max_upload_bytes", "ingestion_upload_chunk_bytes")
    @classmethod
    def validate_positive_ingestion_size(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Os limites de tamanho da ingestão devem ser maiores que zero.")
        return value


settings = Settings()

# Os conectores resolvem credenciais via os.getenv(api_key_env_var), mas o .env
# lido pelo pydantic-settings não popula o ambiente do processo. Esta ponte
# garante que a chave definida no .env chegue aos conectores (API e worker).
if settings.redemet_api_key and not os.getenv("REDEMET_API_KEY"):
    os.environ["REDEMET_API_KEY"] = settings.redemet_api_key
