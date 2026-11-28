"""Runtime settings read from environment variables prefixed `TE_` (12-factor).

Only infrastructure reads the environment. The domain and application layers receive values
through ports and constructors; `main.py` is the single place that builds a `Settings`.
"""

from typing import Literal

from pydantic import Field, SecretStr
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
    chunk_overlap_ms: int = 1_500  # context shared by fixed windows without silence (S11)
    asr_concurrency: int = 32  # chunks in flight per job (design: initial 32)
    asr_engine: Literal["whisper_local", "cohere_local", "vllm", "plumbing"] = (
        "whisper_local"  # D-063, D-067; plumbing S10
    )
    asr_model_id: str = Field(
        default="openai/whisper-large-v3-turbo",
        pattern=r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$",  # a repo id, never a local path (review)
    )
    asr_device: Literal["cuda", "cpu"] | None = None  # None: cuda when available, else cpu
    vllm_url: str = "http://vllm:8000"  # the vLLM service in compose (ADR-0005, D-067)
    search_enabled: bool = False  # TE_SEARCH_ENABLED: bge-m3 search on this deployment (S18, D-079)
    realign_enabled: bool = (
        False  # TE_REALIGN_ENABLED: the API loads the aligner for corrections (S22)
    )
    aligner_model_id: str = Field(
        default="parseh/aligner-ar",  # Apache-2.0 Arabic CTC aligner (D-070)
        pattern=r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$",
    )
    aligner_revision: str = Field(
        default="088bb8afed49b11e2a29a7a9b947b479e9ef3eaa",  # reviewed commit (D-070)
        pattern=r"^[0-9a-f]{40}$",  # a full commit, never a branch name
    )
    vllm_model: str = Field(
        default="CohereLabs/cohere-transcribe-arabic-07-2026",  # production default (D-067)
        pattern=r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$",  # a repo id, never a local path
    )
    secret_key: SecretStr | None = None  # base64 of 32 bytes; seals webhook signing secrets (D-082)
    lease_seconds: int = 120  # design: 2-minute lease
    heartbeat_seconds: float = 30.0
    poll_seconds: float = 1.0  # idle wait between claim attempts
