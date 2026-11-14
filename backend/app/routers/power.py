"""Power, sample-size and minimum-detectable-effect calculator."""
from __future__ import annotations

import math
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field, model_validator

from ..stats import power as pw
from ..utils import clean

router = APIRouter(prefix="/api/power", tags=["power & sample size"])


class Common(BaseModel):
    alpha: float = Field(default=0.05, gt=0, lt=0.5)
    ratio: float = Field(default=1.0, gt=0, le=20, description="n_treatment / n_control")
    two_sided: bool = True
    n_comparisons: int = Field(default=1, ge=1, le=1000, description="Bonferroni-adjust alpha for this many comparisons")


class ProportionPlan(Common):
    baseline: float = Field(gt=0, lt=1, description="Control conversion rate")
    mde: Optional[float] = Field(default=None, description="Smallest lift worth detecting")
    target: Optional[float] = Field(default=None, gt=0, lt=1, description="Alternatively, the treatment rate to detect")
    relative: bool = Field(default=False, description="Interpret mde as a relative lift (0.1 = +10%)")
    power: float = Field(default=0.8, gt=0.1, lt=0.999)
    daily_traffic: Optional[int] = Field(default=None, gt=0, description="Users per day across all arms")

    @model_validator(mode="after")
    def _one_effect(self):
        if (self.mde is None) == (self.target is None):
            raise ValueError("Provide exactly one of mde or target.")
        return self


class MeanPlan(Common):
    delta: float = Field(gt=0, description="Smallest absolute difference in means worth detecting")
    sd: float = Field(gt=0, description="Standard deviation of the metric")
    power: float = Field(default=0.8, gt=0.1, lt=0.999)
    daily_traffic: Optional[int] = Field(default=None, gt=0)


@router.post("/proportions/sample-size")
def plan_proportions(req: ProportionPlan) -> dict:
    return clean(pw.plan_proportions(**req.model_dump()))


@router.post("/means/sample-size")
def plan_means(req: MeanPlan) -> dict:
    return clean(pw.plan_means(**req.model_dump()))


class ProportionPower(Common):
    baseline: float = Field(gt=0, lt=1)
    target: float = Field(gt=0, lt=1)
    n_control: int = Field(ge=2)
    n_treatment: Optional[int] = Field(default=None, ge=2)


@router.post("/proportions/power")
def power_proportions(req: ProportionPower) -> dict:
    n2 = req.n_treatment or math.ceil(req.ratio * req.n_control)
    a = req.alpha / req.n_comparisons
    return clean({"power": pw.power_proportions(req.baseline, req.target, req.n_control, n2, a, req.two_sided),
                  "n_control": req.n_control, "n_treatment": n2, "alpha_adjusted": a})


class MeanPower(Common):
    delta: float
    sd: float = Field(gt=0)
    n_control: int = Field(ge=2)
    n_treatment: Optional[int] = Field(default=None, ge=2)


@router.post("/means/power")
def power_means(req: MeanPower) -> dict:
    n2 = req.n_treatment or math.ceil(req.ratio * req.n_control)
    a = req.alpha / req.n_comparisons
    return clean({"power": pw.power_means(req.delta, req.sd, req.n_control, n2, a, req.two_sided),
                  "n_control": req.n_control, "n_treatment": n2, "alpha_adjusted": a})


class MdeProportions(Common):
    baseline: float = Field(gt=0, lt=1)
    n_control: int = Field(ge=2)
    n_treatment: Optional[int] = Field(default=None, ge=2)
    power: float = Field(default=0.8, gt=0.1, lt=0.999)


@router.post("/proportions/mde")
def mde_proportions(req: MdeProportions) -> dict:
    n2 = req.n_treatment or math.ceil(req.ratio * req.n_control)
    a = req.alpha / req.n_comparisons
    d = pw.mde_proportions(req.baseline, req.n_control, n2, a, req.power, req.two_sided)
    return clean({"absolute_mde": d, "relative_mde": d / req.baseline, "n_control": req.n_control, "n_treatment": n2, "alpha_adjusted": a})


class MdeMeans(Common):
    sd: float = Field(gt=0)
    n_control: int = Field(ge=2)
    n_treatment: Optional[int] = Field(default=None, ge=2)
    power: float = Field(default=0.8, gt=0.1, lt=0.999)


@router.post("/means/mde")
def mde_means(req: MdeMeans) -> dict:
    n2 = req.n_treatment or math.ceil(req.ratio * req.n_control)
    a = req.alpha / req.n_comparisons
    d = pw.mde_means(req.sd, req.n_control, n2, a, req.power, req.two_sided)
    return clean({"absolute_mde": d, "standardized_mde": d / req.sd, "n_control": req.n_control, "n_treatment": n2, "alpha_adjusted": a})
