"""Run an analysis on an uploaded or simulated dataset."""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..services import analysis
from ..services import datasets as dsv
from ..services.experiments import LabelBook

router = APIRouter(prefix="/api/analyze", tags=["analysis"])

Alpha = Field(default=0.05, gt=0, lt=0.5)


class Base(BaseModel):
    dataset_id: str
    labels_id: Optional[str] = Field(default=None, description="Optional dataset holding friendly variant names")


def _labels(labels_id: Optional[str]) -> LabelBook:
    return LabelBook(dsv.store.get(labels_id).df) if labels_id else LabelBook(None)


class FrequentistReq(Base):
    outcome: Optional[str] = None
    outcome_kind: Optional[Literal["binary", "continuous"]] = None
    variant_columns: list[str] = []
    control_level: Optional[str] = None
    alpha: float = Alpha
    correction: Literal["none", "bonferroni", "holm", "bh"] = "holm"


@router.post("/frequentist")
def frequentist(req: FrequentistReq) -> dict:
    """Chi-square (binary) or Welch t-test (continuous) for every variant vs control, with multiple-testing correction."""
    return analysis.run_frequentist(dsv.store.get(req.dataset_id), req, _labels(req.labels_id))


class SequentialReq(Base):
    variant_column: str
    outcome: str
    outcome_kind: Optional[Literal["binary", "continuous"]] = None
    control_level: Optional[str] = None
    variant_level: Optional[str] = None
    time_column: Optional[str] = None
    n_looks: int = Field(default=10, ge=2, le=50)
    alpha: float = Alpha
    tau: Optional[float] = Field(default=None, gt=0, description="Prior sd of the effect for mSPRT (default: 10% of the metric scale)")
    spending: Literal["obf", "pocock"] = "obf"


@router.post("/sequential")
def sequential(req: SequentialReq) -> dict:
    """Peek safely: group-sequential boundaries and always-valid (mSPRT) p-values at every look."""
    return analysis.run_sequential(dsv.store.get(req.dataset_id), req, _labels(req.labels_id))


class BayesReq(Base):
    outcome: Optional[str] = None
    variant_columns: list[str] = []
    control_level: Optional[str] = None
    prior_alpha: float = Field(default=1.0, gt=0)
    prior_beta: float = Field(default=1.0, gt=0)
    rope: float = Field(default=0.0, ge=0, lt=1, description="Practically-negligible difference, in absolute rate points")
    engine: Literal["pymc", "conjugate"] = "pymc"
    draws: int = Field(default=1000, ge=200, le=10000)
    chains: int = Field(default=4, ge=1, le=8)
    hdi_prob: float = Field(default=0.95, gt=0.5, lt=1)


@router.post("/bayesian")
def bayesian(req: BayesReq) -> dict:
    """Probability that each variant beats control, expected lift and expected loss (Beta-Binomial, PyMC)."""
    return analysis.run_bayesian(dsv.store.get(req.dataset_id), req, _labels(req.labels_id))


class PsmReq(Base):
    treatment: str
    treated_value: Optional[Any] = None
    outcome: str
    covariates: list[str] = Field(min_length=1)
    caliper: float = Field(default=0.2, gt=0, le=5)
    n_neighbors: int = Field(default=1, ge=1, le=10)
    n_boot: int = Field(default=100, ge=0, le=1000)
    alpha: float = Alpha
    cross_check: bool = Field(default=True, description="Also estimate with DoWhy matching and an EconML doubly-robust learner")
    refute: bool = False


@router.post("/psm")
def psm(req: PsmReq) -> dict:
    """Propensity-score matching (effect on the treated) with balance diagnostics."""
    return analysis.run_psm(dsv.store.get(req.dataset_id), req)


class DidReq(Base):
    outcome: str
    group_col: str
    treated_value: Any
    time_col: str
    cutoff: Any = Field(description="First time point after the intervention")
    unit_col: Optional[str] = None
    covariates: list[str] = []
    alpha: float = Alpha
    cross_check: bool = True


@router.post("/did")
def did(req: DidReq) -> dict:
    """Difference-in-differences with cluster-robust errors and a parallel-trends check."""
    return analysis.run_did(dsv.store.get(req.dataset_id), req)


class SyntheticReq(Base):
    outcome: str
    unit_col: str
    time_col: str
    intervention: Any
    treated_units: list[str] = []
    group_col: Optional[str] = None
    treated_value: Optional[Any] = None
    freq: str = "W"


@router.post("/synthetic-control")
def synthetic(req: SyntheticReq) -> dict:
    """Synthetic control with placebo-in-space inference."""
    return analysis.run_synthetic(dsv.store.get(req.dataset_id), req)
