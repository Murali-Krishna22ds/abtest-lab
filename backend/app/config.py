"""Runtime configuration, overridable with ABLAB_* environment variables."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ABLAB_", env_file=".env", extra="ignore")

    max_upload_mb: int = 10
    max_rows: int = 500_000
    dataset_ttl_seconds: int = 3600
    max_datasets: int = 50
    sample_dir: Path = _REPO_ROOT / "data" / "sample"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    max_concurrent_heavy_jobs: int = 2
    heavy_job_wait_seconds: float = 60.0
    warmup_pymc: bool = False


settings = Settings()
