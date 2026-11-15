"""Plain-English conclusions.

Every function returns::

    {"headline": str, "verdict": "positive|negative|mixed|inconclusive|neutral",
     "summary": [str, ...], "caveats": [str, ...]}

Wording rules: report the size of the effect and its uncertainty, never say a result
"proves" anything, and never read "not significant" as "no effect".
"""
from __future__ import annotations

CORRECTION_NAMES = {
    "none": "no correction",
    "bonferroni": "Bonferroni",
    "holm": "Holm",
    "bh": "Benjamini-Hochberg",
}


# --------------------------------------------------------------------------- formatting
def fp(p: float | None, adjusted: bool = False) -> str:
    label = "adjusted p" if adjusted else "p"
    if p is None:
        return f"{label} = n/a"
    return f"{label} < 0.001" if p < 0.001 else f"{label} = {p:.3f}"


def pct(x: float, d: int = 1) -> str:
    return f"{x * 100:.{d}f}%"


def pts(x: float, d: int = 1) -> str:
    return f"{x * 100:+.{d}f} percentage points"


def num(x: float) -> str:
    ax = abs(x)
    d = 0 if ax >= 1000 else 1 if ax >= 100 else 2 if ax >= 1 else 3
    return f"{x:,.{d}f}"


def snum(x: float) -> str:
    return ("+" if x >= 0 else "-") + num(abs(x))


def ci_level(alpha: float) -> str:
    return f"{(1 - alpha) * 100:g}%"


# --------------------------------------------------------------------------- frequentist
def frequentist(res: dict) -> dict:
    comps, alpha, m = res["comparisons"], res["alpha"], len(res["comparisons"])
    method = res["correction"]["method"]
    sig = [c for c in comps if c["significant"]]
    pos = [c for c in sig if c["diff"] > 0]
    neg = [c for c in sig if c["diff"] < 0]

    if m == 1:
        c = comps[0]
        if not sig:
            headline = f"No clear difference: {c['variant_label']} is not statistically distinguishable from {c['control_label']}."
        elif pos:
            headline = f"{c['variant_label']} is significantly better than {c['control_label']}."
        else:
            headline = f"{c['variant_label']} is significantly worse than {c['control_label']}."
    elif not sig:
        headline = f"None of the {m} comparisons is statistically significant."
    else:
        headline = f"{len(sig)} of {m} comparisons are statistically significant ({len(pos)} better, {len(neg)} worse than control)."
    verdict = "mixed" if pos and neg else "positive" if pos else "negative" if neg else "inconclusive"

    summary = []
    for c in comps[:10]:
        summary.append(_sentence_freq(c, alpha))
    if m > 10:
        summary.append(f"...and {m - 10} more comparisons in the table below.")

    caveats = []
    if m > 1 and method != "none":
        if method == "bh":
            caveats.append(
                f"{m} comparisons were tested together, so p-values were adjusted with the Benjamini-Hochberg procedure, "
                f"which keeps the expected share of false discoveries among the significant results near {alpha:.0%}."
            )
        else:
            caveats.append(
                f"{m} comparisons were tested together, so p-values were adjusted with the {CORRECTION_NAMES[method]} method "
                f"to keep the chance of even one false positive near {alpha:.0%}."
            )
    elif m > 1:
        caveats.append(
            f"{m} comparisons were tested without any correction: the chance that at least one looks significant "
            f"by luck alone is about {(1 - (1 - alpha) ** m):.0%}."
        )
    for s in res.get("srm", []):
        if s["p_value"] < 0.001:
            caveats.append(
                f"Warning: the traffic split in '{s['title']}' is not the even split expected from random assignment "
                f"({fp(s['p_value'])}). This sample-ratio mismatch usually means a bug in assignment or logging; do not trust these results until it is explained."
            )
    ind = res.get("independence")
    if ind and ind["p_value"] < 0.01:
        caveats.append(
            f"The assignments of '{ind['pair'][0]}' and '{ind['pair'][1]}' are not independent ({fp(ind['p_value'])}), "
            "so analysing each test on its own can be misleading."
        )
    elif ind:
        caveats.append(
            "Several tests ran on the same users. Their assignments look independent, so each test is analysed on its own "
            "(the effect shown is its average effect across the other tests' variants)."
        )
    caveats.extend(n for e in res["experiments"] for n in e["notes"])
    if any("excluded" in n for e in res["experiments"] for n in e["notes"]):
        caveats.append(
            "Rows with a missing outcome were dropped. If missing values depend on the variant (for example, ratings exist only for "
            "users who converted) the comparison can be biased: treat it as a comparison among converters only."
        )
    caveats.append(
        "Statistically significant is not the same as worth shipping: check that the effect, and the low end of its "
        "confidence interval, are large enough to matter for the business."
    )
    return {"headline": headline, "verdict": verdict, "summary": summary, "caveats": caveats}


def _sentence_freq(c: dict, alpha: float) -> str:
    lvl = ci_level(alpha)
    if c["metric"] == "binary":
        body = (
            f"In {c['title']}, {c['variant_label']} converted at {pct(c['mean_variant'])} versus {pct(c['mean_control'])} for "
            f"{c['control_label']}: {pts(c['diff'])}"
        )
        if c["rel_lift"] is not None:
            body += f" ({c['rel_lift'] * 100:+.0f}% relative)"
        body += f", with a {lvl} confidence interval of {c['ci_low'] * 100:+.1f} to {c['ci_high'] * 100:+.1f} points."
    else:
        body = (
            f"In {c['title']}, the average {c['outcome']} was {num(c['mean_variant'])} for {c['variant_label']} versus "
            f"{num(c['mean_control'])} for {c['control_label']}: a difference of {snum(c['diff'])} "
            f"({lvl} CI {snum(c['ci_low'])} to {snum(c['ci_high'])})."
        )
    p = c["p_adjusted"]
    adj = c["p_adjusted"] != c["p_value"]
    if c["significant"]:
        tail = f" This is statistically significant ({fp(p, adj)}): data this extreme would be rare if the variants truly performed the same."
    else:
        tail = f" This is not statistically significant ({fp(p, adj)}); the data are consistent with no real difference, but a small one cannot be ruled out."
    return body + tail


# --------------------------------------------------------------------------- sequential
def sequential(res: dict) -> dict:
    K, alpha = res["n_looks"], res["alpha"]
    first = res["first_look"]
    fin = res["final"]
    v, c = res["variant_label"], res["control_label"]
    gs, ms, nv = first["group_sequential"], first["msprt"], first["naive"]
    last = res["looks"][-1]
    direction = "better" if last["theta"] > 0 else "worse"
    stop = [x for x in (gs, ms) if x]
    if gs and ms:
        headline = f"Safe to stop: both sequential methods show {v} is significantly {direction} than {c}, from look {min(gs, ms)} of {K}."
        verdict = "positive" if last["theta"] > 0 else "negative"
    elif stop:
        which = "the group-sequential boundary" if gs else "the always-valid p-value"
        headline = f"Borderline: only {which} crossed its threshold (look {stop[0]} of {K}); the other method did not."
        verdict = "inconclusive"
    else:
        headline = f"Keep collecting data: neither sequential method finds a significant difference between {v} and {c} yet."
        verdict = "inconclusive"
    summary = [
        f"The data were examined at {K} checkpoints, each time using everything collected so far. "
        f"At the last look the estimated difference was {_eff(res, last['theta'])} "
        f"(always-valid {ci_level(alpha)} interval {_eff(res, last['cs_low'])} to {_eff(res, last['cs_high'])})."
    ]
    if gs:
        summary.append(
            f"Group-sequential (O'Brien-Fleming-style alpha spending): the |z| boundary was first crossed at look {gs}; "
            f"early boundaries are deliberately very strict (about {res['looks'][0]['gs_bound']:.1f} at look 1) and relax to about {res['looks'][-1]['gs_bound']:.2f} at the end."
            if res["spending"] == "obf" else f"Group-sequential (Pocock-style spending): the boundary was first crossed at look {gs}."
        )
    else:
        summary.append("Group-sequential: the z-statistic never left the boundaries.")
    summary.append(
        f"Always-valid (mSPRT): the p-value that stays valid however often you look "
        + (f"first dropped below {alpha:g} at look {ms}." if ms else f"never dropped below {alpha:g}; it ended at {fin['always_valid_p']:.3f}.")
    )
    if nv and not (gs and ms and min(gs, ms) <= nv):
        summary.append(
            f"A naive repeated t-test/chi-square test would have declared significance at look {nv}, "
            "which is exactly the trap: stopping the first time p < 0.05 inflates false positives."
            if not (gs or ms) or nv < min(stop or [K + 1]) else
            f"A naive repeated test would have flagged significance already at look {nv}, before the sequential methods agreed."
        )
    fpr = res.get("naive_peeking_false_positive_rate")
    if fpr is not None:
        summary.append(
            f"With {K} looks and no true effect, stopping at the first p < {alpha:g} gives a false-positive rate of about "
            f"{fpr:.0%} (simulated from your baseline rate), not {alpha:.0%}. The sequential methods stay at or below {alpha:.0%}."
        )
    caveats = [
        "Sequential guarantees only hold if you stop according to the rule. Decide the rule (and the maximum sample size) before the experiment starts.",
        "Looks here are evenly spaced slices of data that were already collected; a real prospective test would look at calendar or traffic checkpoints.",
    ]
    if res.get("ordering_note"):
        caveats.append(res["ordering_note"])
    return {"headline": headline, "verdict": verdict, "summary": summary, "caveats": caveats}


def _eff(res: dict, x: float) -> str:
    return f"{x * 100:+.2f} percentage points" if res["metric"] == "binary" else snum(x)


# --------------------------------------------------------------------------- bayesian
def bayesian(res: dict) -> dict:
    comps = [c for e in res["experiments"] for c in e["comparisons"]]
    best = max(comps, key=lambda c: c["prob_beats_control"])
    worst = min(comps, key=lambda c: c["prob_beats_control"])
    strong_pos = [c for c in comps if c["prob_beats_control"] >= 0.95]
    strong_neg = [c for c in comps if c["prob_beats_control"] <= 0.05]
    if len(comps) == 1:
        c = comps[0]
        headline = f"There is a {pct(c['prob_beats_control'])} probability that {c['variant_label']} beats {c['control_label']}."
    else:
        headline = f"Strongest candidate: {best['variant_label']} ({best['title']}) has a {pct(best['prob_beats_control'])} probability of beating {best['control_label']}."
    verdict = "mixed" if strong_pos and strong_neg else "positive" if strong_pos else "negative" if strong_neg else "inconclusive"
    summary = []
    for c in comps[:10]:
        s = (
            f"{c['title']}: {c['variant_label']} beats {c['control_label']} with probability {pct(c['prob_beats_control'])}. "
            f"The expected difference is {pts(c['expected_diff'], 2)} ({c['expected_rel_lift'] * 100:+.1f}% relative); there is a "
            f"{pct(res['hdi_prob'], 0)} probability that the true difference lies between {c['diff_hdi_low'] * 100:+.2f} and {c['diff_hdi_high'] * 100:+.2f} points."
        )
        s += (
            f" If you ship it and it turns out to be worse, you would lose about {c['expected_loss_if_choose_variant'] * 100:.3f} points of conversion on average."
        )
        if "prob_in_rope" in c:
            s += (
                f" The chance the difference is practically negligible (within +/-{c['rope'] * 100:.2f} points) is {pct(c['prob_in_rope'])}; "
                f"the chance it is a practically meaningful improvement is {pct(c['prob_practically_better'])}."
            )
        summary.append(s)
    if len(comps) > 10:
        summary.append(f"...and {len(comps) - 10} more comparisons in the table below.")
    caveats = [
        "These probabilities come from the data plus the prior "
        f"(Beta({res['prior']['alpha']:g}, {res['prior']['beta']:g}) for every conversion rate). With this much data the prior barely matters, but with small samples it can.",
        "Many teams ship when the probability of beating control is above 95% and the expected loss is tiny; pick your threshold before looking.",
        "Bayesian probabilities do not need a fixed sample size, but they do not fix the cost of stopping early on a lucky streak; combine with a sensible minimum runtime.",
    ]
    if len(comps) > 1:
        caveats.append("Each comparison is evaluated separately; with many comparisons, some high probabilities will occur by chance.")
    d = res["diagnostics"]
    if d.get("r_hat_max") and d["r_hat_max"] > 1.01:
        caveats.append(f"The sampler's convergence diagnostic (R-hat = {d['r_hat_max']:.3f}) is above 1.01; re-run with more draws.")
    return {"headline": headline, "verdict": verdict, "summary": summary, "caveats": caveats}


# --------------------------------------------------------------------------- PSM
def psm(res: dict, outcome: str, alpha: float, truth: float | None = None) -> dict:
    est, lo, hi = res["estimate"], res["ci_low"], res["ci_high"]
    sig = lo > 0 or hi < 0
    naive = res["naive_difference"]
    direction = "higher" if est > 0 else "lower"
    if sig:
        headline = f"After matching on the selected covariates, treated units have a {direction} average {outcome}: {snum(est)}."
        verdict = "positive" if est > 0 else "negative"
    else:
        headline = f"After matching, there is no clear effect on {outcome} (estimate {snum(est)}, interval includes zero)."
        verdict = "inconclusive"
    summary = [
        f"Matching each treated unit to a similar untreated unit estimates an average effect on the treated of {snum(est)} "
        f"({ci_level(alpha)} CI {snum(lo)} to {snum(hi)}).",
        f"The raw difference between the groups is {snum(naive)}; matching changes it by {snum(est - naive)}, "
        + (f"so about {abs(naive - est) / abs(naive):.0%} of the raw gap reflected who received the treatment rather than what it did."
           if abs(naive) > 1e-12 and abs(naive - est) / abs(naive) > 0.05 else "so the groups were already fairly comparable."),
        f"{res['n_treated_matched']:,} of {res['n_treated']:,} treated units found a match"
        + (f" ({res['n_treated_unmatched']:,} dropped because no comparable control existed)." if res["n_treated_unmatched"] else "."),
    ]
    summary.append(
        f"Balance check: after matching the largest standardized difference between groups is {res['max_abs_smd_after']:.2f} "
        + ("(below the common 0.10 threshold, so the groups look comparable on these covariates)." if res["balance_ok"]
           else "(above the common 0.10 threshold, so matching did not fully equalise the groups; treat the estimate cautiously).")
    )
    cc = res.get("cross_checks", {})
    parts = []
    if "dowhy_psm" in cc:
        parts.append(f"DoWhy matching {snum(cc['dowhy_psm']['estimate'])}")
    if "econml_dr" in cc:
        e = cc["econml_dr"]
        parts.append(f"EconML doubly-robust {snum(e['estimate'])} (CI {snum(e['ci_low'])} to {snum(e['ci_high'])})")
    if parts:
        summary.append("Independent cross-checks: " + "; ".join(parts) + ". Estimates that agree make the finding more credible; large disagreements signal model sensitivity.")
    if truth is not None:
        summary.append(f"This is simulated data, so we know the true effect is {snum(truth)}.")
    caveats = [
        "Matching can only account for the covariates you selected. If something unmeasured influences both who gets the treatment and the outcome, the estimate is still biased.",
        "Treat this as evidence of association adjusted for observed factors, not as a randomized-experiment result.",
        "The confidence interval comes from a bootstrap that re-fits the propensity model; it is approximate for matching estimators.",
    ]
    if res["n_treated_unmatched"] > 0.1 * res["n_treated"]:
        caveats.append("More than 10% of treated units had no comparable control, so the result applies only to the matched subset.")
    if res["n_dropped_missing"]:
        caveats.append(f"{res['n_dropped_missing']:,} rows with missing values in the selected columns were excluded.")
    return {"headline": headline, "verdict": verdict, "summary": summary, "caveats": caveats}


# --------------------------------------------------------------------------- DiD
def did(res: dict, outcome: str, alpha: float, group: str, truth: float | None = None) -> dict:
    est, lo, hi = res["estimate"], res["ci_low"], res["ci_high"]
    sig = lo > 0 or hi < 0
    m = res["means"]
    if sig:
        headline = f"The treated group's {outcome} moved {'up' if est > 0 else 'down'} by {num(abs(est))} more than the control group after the change."
        verdict = "positive" if est > 0 else "negative"
    else:
        headline = f"No clear effect: the treated group's change in {outcome} is not distinguishable from the control group's."
        verdict = "inconclusive"
    summary = [
        f"Treated group: {num(m['treated_pre'])} before, {num(m['treated_post'])} after (change {snum(m['treated_change'])}). "
        f"Control group: {num(m['control_pre'])} before, {num(m['control_post'])} after (change {snum(m['control_change'])}).",
        f"The difference-in-differences estimate is {snum(est)} ({ci_level(alpha)} CI {snum(lo)} to {snum(hi)}, {fp(res['p_value'])}): "
        "the extra change in the treated group beyond what the control group's trend would predict.",
    ]
    pt = res.get("pre_trend")
    if pt:
        ok = pt["p_value"] > 0.05
        summary.append(
            f"Parallel-trends check: before the change, the two groups' trends "
            + ("were not significantly different " if ok else "were significantly different ")
            + f"({fp(pt['p_value'])}). "
            + ("That supports the key assumption, although a non-significant test cannot prove it." if ok
               else "That undermines the key assumption, so the estimate may be biased.")
        )
    cc = res.get("cross_check", {})
    if "estimate" in cc:
        summary.append(f"DoWhy's regression estimate of the same effect is {snum(cc['estimate'])}.")
    if truth is not None:
        summary.append(f"This is simulated data, so we know the true effect is {snum(truth)}.")
    caveats = list(res["caveats"]) + [
        "The estimate is only causal if, without the change, the treated group would have followed the control group's trend (parallel trends) and nothing else changed for one group at the same time.",
        f"Standard errors are {res['se_type']}.",
    ]
    if res["n_dropped_missing"]:
        caveats.append(f"{res['n_dropped_missing']:,} rows with missing values were excluded.")
    return {"headline": headline, "verdict": verdict, "summary": summary, "caveats": caveats}


# --------------------------------------------------------------------------- synthetic control
def synthetic(res: dict, outcome: str, truth: float | None = None) -> dict:
    est, p = res["estimate"], res["p_value"]
    units = ", ".join(res["treated_units"][:3]) + ("..." if len(res["treated_units"]) > 3 else "")
    rel = res["relative_effect"]
    sig = p is not None and p <= 0.05
    if sig:
        headline = f"After the intervention, {units} ended up {num(abs(est))} {'above' if est > 0 else 'below'} its synthetic twin on average" + (f" ({rel * 100:+.1f}%)." if rel is not None else ".")
        verdict = "positive" if est > 0 else "negative"
    else:
        headline = f"No convincing effect: the gap between {units} and its synthetic twin is not unusual compared with placebo units."
        verdict = "inconclusive"
    summary = [
        f"A synthetic version of {units} was built from {len(res['weights'])} weighted donor unit(s) so that it tracks the real series before the intervention "
        f"(typical pre-period error {num(res['pre_rmspe'])}).",
        f"After the intervention the real series averages {snum(est)} relative to the synthetic one"
        + (f" ({rel * 100:+.1f}%)" if rel is not None else "") + f", a cumulative gap of {snum(res['cumulative_effect'])}.",
    ]
    if p is not None:
        summary.append(
            f"Placebo test: applying the same method to each of the {res['n_placebos']} untreated units, "
            f"{max(0, round(p * (res['n_placebos'] + 1) - 1))} of them showed a post/pre error ratio as large as the treated unit's, giving {fp(p)}. "
            "A small p-value means the treated unit's divergence is rare among units that were not treated."
        )
    if truth is not None:
        summary.append(f"This is simulated data, so we know the true effect is {snum(truth)}.")
    caveats = list(res["caveats"]) + [
        "Synthetic control assumes no other change affected the treated unit at the same time and that donors were not themselves affected by the intervention.",
        "Inference is by permutation across units, so it has limited resolution when there are few donors.",
    ]
    return {"headline": headline, "verdict": verdict, "summary": summary, "caveats": caveats}
