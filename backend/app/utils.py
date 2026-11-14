"""Small shared helpers."""
from __future__ import annotations

import math
import threading
from contextlib import contextmanager
from typing import Any, Iterator

import numpy as np
import pandas as pd

from .config import settings
from .errors import AppError

_heavy = threading.BoundedSemaphore(settings.max_concurrent_heavy_jobs)


@contextmanager
def heavy_slot() -> Iterator[None]:
    """Bound concurrency of expensive jobs (MCMC, bootstraps) so the API stays responsive."""
    if not _heavy.acquire(timeout=settings.heavy_job_wait_seconds):
        raise AppError("The server is busy running other heavy analyses. Please retry in a few seconds.", 503)
    try:
        yield
    finally:
        _heavy.release()


def clean(obj: Any) -> Any:
    """Recursively convert numpy/pandas values to JSON-safe Python (NaN/inf -> None)."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [clean(v) for v in obj.tolist()]
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return f if math.isfinite(f) else None
    return obj
