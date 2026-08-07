"""Application configuration loaded from environment variables / .env file."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "BusTracker"
    environment: Literal["dev", "test", "prod"] = "dev"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # --- Database -------------------------------------------------------
    database_url: str = Field(
        default="sqlite+aiosqlite:///./bus_tracker.db",
        description="SQLAlchemy async URL. Use postgresql+asyncpg://... for production.",
    )
    # Set true when database_url is Postgres/PostGIS to enable spatial SQL paths.
    use_postgis: bool = False
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # --- Redis -----------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    # In-memory fallback used when REDIS_URL is empty (dev/tests). Never true in prod.
    redis_enabled: bool = True
    redis_location_ttl_seconds: int = 60
    redis_eta_ttl_seconds: int = 30

    # --- Auth / Security --------------------------------------------------
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    refresh_token_days: int = 7
    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 5
    otp_rate_limit_window_seconds: int = 600
    otp_rate_limit_max: int = 3

    # --- Admin -------------------------------------------------------------
    admin_api_key: str = "change-me-admin"

    # --- SMS provider -----------------------------------------------------
    sms_provider: Literal["console", "msg91", "twilio"] = "console"
    sms_api_key: str = ""
    sms_sender_id: str = "BUSTKR"

    # --- OSRM routing ------------------------------------------------------
    osrm_base_url: str = "https://router.project-osrm.org"
    osrm_timeout_seconds: float = 10.0
    route_snap_threshold_m: float = 1500.0
    route_duplicate_radius_m: float = 1500.0

    # --- Tracking ----------------------------------------------------------
    location_interval_moving_seconds: int = 5
    location_interval_stopped_seconds: int = 15
    stale_after_seconds: int = 60
    trip_max_duration_hours: int = 24
    max_location_rate_per_second: int = 1
    anomaly_max_speed_kmh: float = 130.0
    anomaly_off_route_threshold_m: float = 3000.0
    location_history_retention_days: int = 90
    location_batch_size: int = 100

    # --- Push notifications ------------------------------------------------
    fcm_enabled: bool = False
    fcm_credentials_file: str = ""

    # --- CORS ---------------------------------------------------------------
    cors_origins: list[str] = ["*"]

    # --- Village pipeline ---------------------------------------------------
    village_snap_radius_m: float = 1500.0
    overpass_api_url: str = "https://overpass-api.de/api/interpreter"
    overpass_timeout_seconds: float = 240.0

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @model_validator(mode="after")
    def _guard_prod_secrets(self) -> "Settings":
        if self.environment == "prod":
            if self.jwt_secret in {"change-me-in-production", ""}:
                raise ValueError("JWT_SECRET must be a strong random secret in production")
            if self.admin_api_key in {"change-me-admin", ""}:
                raise ValueError("ADMIN_API_KEY must be set in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
