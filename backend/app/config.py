from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base backend directory pointing to backend/.env
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    """Application configuration loaded from backend/.env and environment variables."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/devflow"
    TEST_DATABASE_URL: str = "postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/devflow_test"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        """Split CORS_ORIGINS string into a list of allowed origins."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
