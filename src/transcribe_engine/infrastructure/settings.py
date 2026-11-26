"""Runtime settings read from environment variables prefixed `TE_` (12-factor).

Only infrastructure reads the environment. The domain and application layers receive values
through ports and constructors; `main.py` is the single place that builds a `Settings`.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

# Local development defaults match docker-compose.yml. They are throwaway values; production
# sets TE_DATABASE_URL explicitly.
LOCAL_DATABASE_URL = "postgresql+asyncpg://te:te@localhost:5432/transcribe"
# Local MinIO from docker-compose.yml. Throwaway values; production sets TE_S3_* explicitly.
LOCAL_S3_ENDPOINT = "http://localhost:9000"
LOCAL_S3_ACCESS_KEY = "te-local"
LOCAL_S3_SECRET_KEY = "te-local-secret"  # noqa: S105 - throwaway local dev credential (compose)


class Settings(BaseSettings):
    """Process configuration. Add a field only together with the code that reads it."""

    model_config = SettingsConfigDict(env_prefix="TE_", extra="ignore")

    database_url: str = LOCAL_DATABASE_URL
    s3_endpoint_url: str = LOCAL_S3_ENDPOINT
    s3_access_key: str = LOCAL_S3_ACCESS_KEY
    s3_secret_key: str = LOCAL_S3_SECRET_KEY
    s3_bucket: str = "transcribe-local"
    s3_region: str = "us-east-1"
    scratch_dir: str = ".scratch"  # ingest and FFmpeg work files; git-ignored
    chunk_max_ms: int = 30_000  # longest core of one chunk (S10)
    chunk_pad_ms: int = 500  # padding either side of a core, inside the file (S10)
    asr_concurrency: int = 32  # chunks in flight per job (design: initial 32)
    lease_seconds: int = 120  # design: 2-minute lease
    heartbeat_seconds: float = 30.0
    poll_seconds: float = 1.0  # idle wait between claim attempts
