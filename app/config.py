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
    # The seeded admin account. Empty password -> scripts/seed.py generates and prints a random one.
    admin_phone: str = "9000000001"
    admin_name: str = "DhabaGo Admin"
    admin_password: str = ""

    google_places_api_key: str = ""
    gemini_api_key: str = ""

    order_cutoff_buffer_minutes: int = 10
    # Kitchens aim to have food ready this long before the bus pulls in.
    ready_before_arrival_minutes: int = 6

    # Money is whole rupees. Fee is added to every order; commission is the
    # default per-dhaba cut (dhabas.commission_pct overrides it per dhaba).
    # Comma-separated origins allowed to call the API from a browser. The bundled
    # frontend is same-origin; set this when hosting a frontend elsewhere.
    cors_origins: str = "*"

    convenience_fee_inr: int = 7
    default_commission_pct: int = 12

    # Razorpay. Test-mode keys look like "rzp_test_...". The key id is public and
    # is handed to the browser; the secret never leaves the server. Set both as
    # environment variables, never in a committed file.
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""

    @property
    def payments_enabled(self) -> bool:
        """Payments are on only when both keys are configured. Without them the app
        behaves exactly as it did before: orders go straight to the kitchen."""
        return bool(self.razorpay_key_id and self.razorpay_key_secret)


settings = Settings()
