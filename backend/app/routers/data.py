"""Dataset upload, bundled samples and simulated datasets."""
from __future__ import annotations

from typing import Literal

import pandas as pd
from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel, Field

from ..errors import AppError
from ..services import datasets as dsv
from ..stats import simulate
from ..utils import clean

router = APIRouter(prefix="/api", tags=["data"])


@router.post("/datasets")
async def upload(file: UploadFile = File(...)) -> dict:
    """Upload a CSV; returns its profile (columns, roles, preview, suggested column choices)."""
    content = await file.read()
    df = dsv.parse_csv(content, file.filename or "upload.csv")
    return clean(dsv.profile(dsv.store.add(df, file.filename or "upload.csv")))


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str) -> dict:
    return clean(dsv.profile(dsv.store.get(dataset_id)))


@router.get("/samples")
def samples() -> list[dict]:
    return dsv.list_samples()


@router.post("/samples/{name}")
def load_sample(name: str) -> dict:
    ds = dsv.load_sample(name)
    if ds.kind != "labels" and (dsv.settings.sample_dir / "ab_test_variants.csv").exists():
        ds.meta["labels_id"] = dsv.load_sample("ab_test_variants").id
    return clean(dsv.profile(ds))


class SimRequest(BaseModel):
    scenario: Literal["ab_test", "observational", "panel"]
    seed: int = 0
    # ab_test
    n_total: int = Field(default=20000, ge=100, le=300_000)
    baseline: float = Field(default=0.10, gt=0, lt=1)
    rel_lift: float = Field(default=0.10, gt=-0.9, lt=5)
    n_variants: int = Field(default=2, ge=2, le=5)
    metric: Literal["binary", "continuous"] = "binary"
    sd: float = Field(default=10.0, gt=0)
    days: int = Field(default=14, ge=1, le=365)
    # observational
    n: int = Field(default=4000, ge=200, le=100_000)
    true_effect: float = 2.0
    confounding: float = Field(default=1.0, ge=0, le=5)
    # panel
    n_units: int = Field(default=30, ge=6, le=300)
    n_periods: int = Field(default=40, ge=8, le=200)
    n_treated: int = Field(default=5, ge=1, le=100)
    intervention_period: int = Field(default=28, ge=4, le=199)


@router.post("/datasets/simulate")
def simulate_dataset(req: SimRequest) -> dict:
    """Generate a synthetic dataset with a known true effect and register it like an upload."""
    if req.scenario == "ab_test":
        df = simulate.simulate_ab(req.n_total, req.baseline, req.rel_lift, req.n_variants, req.metric, req.sd, req.days, req.seed)
        outcome = [c for c in df.columns if c not in {"user_id", "timestamp", "variant"}][0]
        meta = {"truth": {"rel_lift": req.rel_lift, "baseline": req.baseline},
                "suggested": {"variant_columns": ["variant"], "variant_column": "variant", "outcome": outcome, "time_column": "timestamp"}}
    elif req.scenario == "observational":
        df = simulate.simulate_observational(req.n, req.true_effect, req.confounding, req.seed)
        meta = {"truth": {"effect": req.true_effect},
                "suggested": {"treatment": "treated", "outcome": "outcome", "covariates": ["age", "income", "engagement", "plan"]}}
    else:
        if req.intervention_period >= req.n_periods:
            raise AppError("The intervention period must fall inside the observed periods.", 422)
        if req.n_treated >= req.n_units:
            raise AppError("Need at least one untreated unit.", 422)
        df = simulate.simulate_panel(req.n_units, req.n_periods, req.n_treated, req.intervention_period, req.true_effect, req.seed)
        cutoff = (pd.Timestamp(df["date"].min()) + pd.Timedelta(weeks=req.intervention_period)).date().isoformat()
        meta = {"truth": {"effect": req.true_effect},
                "suggested": {"outcome": "outcome", "unit_col": "unit", "time_col": "date", "group_col": "group",
                              "treated_value": "treated", "cutoff": cutoff}}
    name = f"simulated_{req.scenario}.csv"
    ds = dsv.store.add(df, name, meta=meta)
    return clean(dsv.profile(ds))


@router.get("/datasets/{dataset_id}/download")
def download(dataset_id: str):
    from fastapi.responses import Response

    ds = dsv.store.get(dataset_id)
    return Response(ds.df.to_csv(index=False), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{ds.name}"'})
