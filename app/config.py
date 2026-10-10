from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://busfood:busfood@localhost:5432/busfood"

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        """Railway (and Heroku-style providers) hand out `postgres://`, which
        SQLAlchemy 2.0 no longer accepts — rewrite it to `postgresql://`.
        """
        if value.startswith("postgres://"):
            return "postgresql://" + value[len("postgres://"):]
        return value

    secret_key: str = "change-this-to-a-random-secret-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    seed_user_password: str = "password123"

    google_places_api_key: str = ""
    gemini_api_key: str = ""

    order_cutoff_buffer_minutes: int = 10


settings = Settings()
