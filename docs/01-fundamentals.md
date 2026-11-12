# 1. Fundamentals: hypothesis tests, p-values, power, confidence intervals

Everything in this project rests on four ideas. Each claim below is checked by simulation in
[`scripts/fundamentals_demo.py`](../scripts/fundamentals_demo.py); the numbers quoted come from that script.

## Hypothesis test

An experiment compares a *control* (A) with a *treatment* (B). We start from a skeptical **null hypothesis**
H0: "B has the same true effect as A". The data either give enough evidence to reject H0 in favour of the
**alternative** H1 ("the effects differ"), or they do not. Not rejecting H0 is *absence of evidence*, not
evidence that the treatment does nothing.

Two ways to be wrong:

| | H0 true (no effect) | H1 true (real effect) |
|---|---|---|
| Reject H0 | **Type I error** (false positive), probability alpha | Correct, probability = **power** |
| Keep H0 | Correct | **Type II error** (missed effect), probability beta = 1 - power |

Alpha (conventionally 0.05) is chosen *before* the experiment and is the false-positive rate we accept.

## p-value

The p-value is the probability of seeing a result at least as extreme as the one observed **if H0 were true**.

* It is **not** the probability that H0 is true, nor the probability the result is a fluke.
* It is **not** the size or importance of the effect. A huge sample can make a trivial lift "significant".
* If H0 is true, p-values are uniformly distributed. Simulation: P(p < 0.05) = 0.052, P(p < 0.50) = 0.505.
  This is why "p < 0.05" produces false positives 5% of the time by construction.

## Confidence interval

A 95% confidence interval is produced by a procedure that covers the true effect in 95% of repeated experiments
(simulated coverage: 0.950). Prefer it to a bare p-value because it shows **how large** the effect plausibly is.
A CI that excludes 0 is equivalent to p < alpha for the matching two-sided test. It does **not** mean there is a
95% chance the true value lies in this particular interval; that statement belongs to Bayesian credible
intervals (Step 5).

## Power

Power is the probability of detecting an effect of a given size when it truly exists. It depends on four things:
the **effect size** (bigger is easier), the **noise** (less is easier), the **sample size** and **alpha**.

* Standard target: 80% power. Simulation agrees with theory (d = 0.5, n = 64/arm: simulated 0.798, formula 0.801).
* Required n scales with 1 / d^2: halving the effect quadruples the sample (n * d^2 stays near 15.7).
* **Underpowered tests mislead twice**: they miss real effects, and the effects they *do* flag are inflated
  (true d = 0.2, power 14%, average estimate among significant results 0.54: the "winner's curse").

## Effect size

Report effects in business units (absolute and relative lift) and as standardised sizes:
Cohen's d = (mean difference) / (pooled sd); roughly 0.2 small, 0.5 medium, 0.8 large.
The **minimum detectable effect (MDE)** is the smallest effect worth acting on and is the key input to planning.

## Multiple comparisons and peeking

Every extra metric, segment or interim look is another chance for a false positive: with 20 independent null
metrics the chance of at least one "significant" result is 64%. Step 3 (Bonferroni, Benjamini-Hochberg) and
Step 4 (sequential testing) are the two standard defences.

## A workable experiment checklist

1. Define one primary metric and a decision rule up front.
2. Pick the MDE and compute sample size (Step 2).
3. Randomise, run to the planned size (or use a sequential design if you must peek).
4. Report the effect with a confidence interval, not just a p-value.
5. Correct for multiple metrics; treat secondary findings as hypotheses.
