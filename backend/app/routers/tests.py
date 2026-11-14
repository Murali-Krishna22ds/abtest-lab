"""Classical tests and multiple-testing corrections from summary numbers (no upload needed)."""
from __future__ import annotations

import dataclasses
from typing import Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field, model_validator

from ..stats import corrections, tests
from ..utils import clean

router = APIRouter(prefix="/api/tests", tags=["classical tests"])


class ProportionsReq(BaseModel):
    x_control: int = Field(ge=0)
    n_control: int = Field(ge=1)
    x_treatment: int = Field(ge=0)
    n_treatment: int = Field(ge=1)
    alpha: float = Field(default=0.05, gt=0, lt=0.5)

    @model_validator(mode="after")
    def _counts(self):
        if self.x_control > self.n_control or self.x_treatment > self.n_treatment:
            raise ValueError("Conversions cannot exceed the number of users.")
        return self


@router.post("/chi-square")
def chi_square(req: ProportionsReq) -> dict:
    """Two-proportion test (Pearson chi-square, equivalent to the pooled z-test) with a CI for the lift."""
    r = tests.two_proportion_test(req.x_control, req.n_control, req.x_treatment, req.n_treatment, req.alpha)
    return clean(dataclasses.asdict(r))


class MeansReq(BaseModel):
    mean_control: float
    sd_control: float = Field(ge=0)
    n_control: int = Field(ge=2)
    mean_treatment: float
    sd_treatment: float = Field(ge=0)
    n_treatment: int = Field(ge=2)
    alpha: float = Field(default=0.05, gt=0, lt=0.5)


@router.post("/t-test")
def t_test(req: MeansReq) -> dict:
    """Welch's unequal-variance t-test from summary statistics."""
    r = tests.welch_t_test_from_stats(req.mean_control, req.sd_control, req.n_control, req.mean_treatment,
                                      req.sd_treatment, req.n_treatment, req.alpha)
    return clean(dataclasses.asdict(r))


class TableReq(BaseModel):
    table: list[list[int]] = Field(description="r x c contingency table of counts")


@router.post("/chi-square-table")
def chi_square_table(req: TableReq) -> dict:
    return clean(tests.chi_square_table(req.table))


class SrmReq(BaseModel):
    counts: list[int] = Field(min_length=2)
    expected_ratios: Optional[list[float]] = None


@router.post("/srm")
def srm(req: SrmReq) -> dict:
    """Sample-ratio-mismatch check: does the traffic split match the plan?"""
    return clean(tests.srm_check(req.counts, req.expected_ratios))


class AdjustReq(BaseModel):
    p_values: list[float] = Field(min_length=1, max_length=100_000)
    method: Literal["none", "bonferroni", "holm", "bh"] = "bh"
    alpha: float = Field(default=0.05, gt=0, lt=0.5)


@router.post("/adjust-pvalues")
def adjust(req: AdjustReq) -> dict:
    """Multiple-testing correction: Bonferroni, Holm (FWER) or Benjamini-Hochberg (FDR)."""
    adj = corrections.adjust_pvalues(req.p_values, req.method)
    return clean({"method": req.method, "alpha": req.alpha, "adjusted": adj, "reject": adj <= req.alpha,
                  "n_rejected": int((adj <= req.alpha).sum())})
