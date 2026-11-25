"""Runtime settings read from environment variables prefixed `TE_` (12-factor).

Only infrastructure reads the environment. The domain and application layers receive values
through ports and constructors; `main.py` is the single place that builds a `Settings`.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

# Local development defaults match docker-compose.yml. They are throwaway values; production
# sets TE_DATABASE_URL explicitly.
LOCAL_DATABASE_URL = "postgresql+asyncpg://te:te@localhost:5432/transcribe"


class Settings(BaseSettings):
    """Process configuration. Add a field only together with the code that reads it."""

    model_config = SettingsConfigDict(env_prefix="TE_", extra="ignore")

    database_url: str = LOCAL_DATABASE_URL
