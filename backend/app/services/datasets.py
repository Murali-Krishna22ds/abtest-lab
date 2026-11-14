"""In-memory dataset store: CSV parsing, type detection, profiling and bundled samples."""
from __future__ import annotations

import io
import re
import threading
import time
import uuid
from dataclasses import dataclass, field

import pandas as pd

from ..config import settings
from ..errors import AppError

_DATE_NAME = re.compile(r"(date|time|_at$|timestamp|day|week|month)", re.I)


@dataclass
class Dataset:
    id: str
    name: str
    kind: str  # rows | aggregated | labels
    df: pd.DataFrame
    meta: dict = field(default_factory=dict)
    created: float = field(default_factory=time.time)


class DatasetStore:
    """Thread-safe store with TTL expiry and a hard cap on the number of datasets."""

    def __init__(self, ttl: int | None = None, max_items: int | None = None):
        self._items: dict[str, Dataset] = {}
        self._lock = threading.Lock()
        self.ttl = ttl if ttl is not None else settings.dataset_ttl_seconds
        self.max_items = max_items if max_items is not None else settings.max_datasets

    def _purge(self) -> None:
        now = time.time()
        for k in [k for k, v in self._items.items() if now - v.created > self.ttl]:
            del self._items[k]
        while len(self._items) > self.max_items:
            del self._items[min(self._items, key=lambda k: self._items[k].created)]

    def add(self, df: pd.DataFrame, name: str, kind: str | None = None, meta: dict | None = None) -> Dataset:
        ds = Dataset(uuid.uuid4().hex[:12], name, kind or detect_kind(df), df, meta or {})
        with self._lock:
            self._purge()
            self._items[ds.id] = ds
        return ds

    def get(self, dataset_id: str) -> Dataset:
        with self._lock:
            self._purge()
            ds = self._items.get(dataset_id)
        if ds is None:
            raise AppError("Dataset not found or expired. Please upload it again.", 404)
        return ds


store = DatasetStore()


# --------------------------------------------------------------------------- parsing
def parse_csv(content: bytes, name: str) -> pd.DataFrame:
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise AppError(f"File is larger than {settings.max_upload_mb} MB.", 413)
    if not content.strip():
        raise AppError("The file is empty.")
    try:
        df = pd.read_csv(io.BytesIO(content), encoding_errors="replace")
        if df.shape[1] == 1 and len(content) < 5_000_000:  # maybe ';' or tab separated
            alt = pd.read_csv(io.BytesIO(content), sep=None, engine="python", encoding_errors="replace")
            if alt.shape[1] > 1:
                df = alt
    except Exception as e:
        raise AppError(f"Could not read '{name}' as CSV: {str(e)[:150]}") from e
    df.columns = [str(c).strip() for c in df.columns]
    if df.shape[0] < 2 or df.shape[1] < 1:
        raise AppError("The file needs a header row and at least two data rows.")
    if df.shape[0] > settings.max_rows:
        raise AppError(f"The file has {df.shape[0]:,} rows; the limit is {settings.max_rows:,}.", 413)
    if len(set(df.columns)) != len(df.columns):
        raise AppError("Column names must be unique.")
    return coerce_types(df)


def coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    """Parse date-like text columns to datetimes (only when almost all values parse)."""
    df = df.copy()
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_numeric_dtype(s) or pd.api.types.is_bool_dtype(s) or pd.api.types.is_datetime64_any_dtype(s):
            continue
        if not _DATE_NAME.search(c):
            continue
        sample = s.dropna().astype(str).head(200)
        if sample.empty:
            continue
        parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
        if parsed.notna().mean() >= 0.95:
            full = pd.to_datetime(s, errors="coerce", format="mixed")
            if full.notna().sum() >= 0.95 * s.notna().sum():
                df[c] = full
    return df


def detect_kind(df: pd.DataFrame) -> str:
    cols = {c.lower() for c in df.columns}
    if {"variant_key", "variant_name"} <= cols and not ({"total_users", "conversions"} & cols):
        return "labels"
    if {"variant_key", "total_users", "conversions"} <= cols:
        return "aggregated"
    return "rows"


# --------------------------------------------------------------------------- profiling
def column_role(s: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(s):
        return "binary"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime"
    nun = s.nunique(dropna=True)
    if pd.api.types.is_numeric_dtype(s):
        vals = set(pd.unique(s.dropna()))
        return "binary" if vals and vals <= {0, 1} and nun <= 2 else "numeric"
    if nun <= 50 or (len(s) and nun / len(s) < 0.05):
        return "categorical"
    return "id"


def profile(ds: Dataset) -> dict:
    df = ds.df
    cols = []
    for c in df.columns:
        s = df[c]
        role = column_role(s)
        info = {"name": c, "role": role, "n_unique": int(s.nunique(dropna=True)), "n_missing": int(s.isna().sum())}
        if role in {"binary", "categorical"}:
            info["levels"] = [str(v) for v in s.value_counts().head(12).index]
        elif role == "numeric":
            info["min"], info["max"] = float(s.min()), float(s.max())
        elif role == "datetime":
            info["min"], info["max"] = s.min().isoformat(), s.max().isoformat()
        cols.append(info)
    by_role = lambda *roles: [c["name"] for c in cols if c["role"] in roles]  # noqa: E731
    variants = [c["name"] for c in cols if c["role"] == "categorical" and 2 <= c["n_unique"] <= 6
                and (re.search(r"variant|(^|_)arm|treat|bucket|cohort|experiment", c["name"], re.I) or "control" in c.get("levels", []))]
    return {
        "id": ds.id, "name": ds.name, "kind": ds.kind, "n_rows": int(len(df)), "n_cols": int(df.shape[1]),
        "columns": cols,
        "preview": df.head(5).astype(object).where(df.head(5).notna(), None).to_dict("records"),
        "suggestions": {
            "variant_columns": variants,
            "binary": by_role("binary"),
            "outcomes": by_role("binary", "numeric"),
            "time_columns": by_role("datetime") or by_role("numeric"),
            "datetime_columns": by_role("datetime"),
            "unit_columns": [c["name"] for c in cols if c["role"] in {"categorical", "id"} and 3 <= c["n_unique"] <= 500],
            "categorical": by_role("categorical", "binary"),
            "numeric": by_role("numeric"),
        },
        "meta": ds.meta,
    }


# --------------------------------------------------------------------------- samples
def list_samples() -> list[dict]:
    d = settings.sample_dir
    return [{"name": p.stem, "file": p.name, "size_kb": round(p.stat().st_size / 1024, 1)} for p in sorted(d.glob("*.csv"))] if d.exists() else []


def load_sample(name: str) -> Dataset:
    path = settings.sample_dir / f"{name}.csv"
    if not re.fullmatch(r"[\w\-]+", name) or not path.exists():
        raise AppError(f"Unknown sample '{name}'.", 404)
    return store.add(parse_csv(path.read_bytes(), path.name), path.name)
