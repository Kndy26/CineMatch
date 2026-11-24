"""Environment configuration shared by FastAPI and Alembic."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class MetadataSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    tmdb_read_access_token: SecretStr | None = Field(default=None, repr=False)


class Settings(MetadataSettings):
    database_url: PostgresDsn = Field(repr=False)

    @field_validator("database_url")
    @classmethod
    def use_psycopg(cls, value: PostgresDsn) -> PostgresDsn:
        if value.scheme != "postgresql+psycopg":
            raise ValueError("DATABASE_URL harus menggunakan skema postgresql+psycopg.")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
