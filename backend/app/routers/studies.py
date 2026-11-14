"""Monte-Carlo studies that demonstrate why peeking and multiple testing need correction."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..stats import sequential as seq
from ..stats import simulate
from ..utils import clean, heavy_slot

router = APIRouter(prefix="/api", tags=["simulation studies"])


class PeekingReq(BaseModel):
    baseline: float = Field(default=0.10, gt=0, lt=1)
    rel_lift: float = Field(default=0.0, gt=-0.9, lt=5, description="0 = null world (measures false positives)")
    n_max: int = Field(default=10_000, ge=100, le=200_000, description="Per-arm sample size at the final look")
    n_looks: int = Field(default=10, ge=2, le=50)
    alpha: float = Field(default=0.05, gt=0, lt=0.5)
    sims: int = Field(default=2000, ge=100, le=5000)
    seed: int = 0


@router.post("/sequential/peeking-simulation")
def peeking(req: PeekingReq) -> dict:
    with heavy_slot():
        return clean(simulate.simulate_peeking(**req.model_dump()))


class BoundsReq(BaseModel):
    n_looks: int = Field(default=5, ge=1, le=50)
    alpha: float = Field(default=0.05, gt=0, lt=0.5)
    spending: str = Field(default="obf", pattern="^(obf|pocock)$")


@router.post("/sequential/boundaries")
def boundaries(req: BoundsReq) -> dict:
    """Two-sided critical z-values for equally spaced looks (Lan-DeMets alpha spending)."""
    info = [(i + 1) / req.n_looks for i in range(req.n_looks)]
    z = seq.group_sequential_bounds(info, req.alpha, req.spending)
    return clean({"info_fractions": info, "z_bounds": z, "spending": req.spending, "alpha": req.alpha})


class MultiReq(BaseModel):
    m: int = Field(default=20, ge=2, le=500)
    m_true: int = Field(default=5, ge=0, le=500)
    effect_z: float = Field(default=3.0, ge=0, le=10)
    alpha: float = Field(default=0.05, gt=0, lt=0.5)
    sims: int = Field(default=4000, ge=200, le=20000)
    seed: int = 0


@router.post("/multiple-testing/simulation")
def multiple_testing(req: MultiReq) -> dict:
    """Family-wise error, false-discovery rate and power for each correction method."""
    return clean(simulate.simulate_multiple_testing(**req.model_dump()))
