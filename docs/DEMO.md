# Demo guide

The recorded walkthrough is `docs/demo/demo.webm` (1:55). To re-record it: `cd frontend && npx playwright install chromium`, then
`SCRIPT=e2e/record_demo.mjs OUT=../docs/demo scripts/e2e.sh` from the repository root.

## Live demo script (about 5 minutes)

1. **Plan** (30 s). *Plan an experiment*: 10% baseline, 10% relative lift gives 14,751 users per arm. Lower the lift to 5% and watch the sample roughly quadruple. Switch to *What can I detect?*.
2. **Compare variants** (60 s). Load the `ab test sessions` sample, run *Compare variants*. Point out: six comparisons across four concurrent tests, corrected together; the pricing variants are significantly *worse*; the forest plot; the "before you act on this" box.
3. **Peek safely** (60 s). Run *Peek safely* on the icon test: the z-line leaves the O'Brien-Fleming corridor at look 6. Read the bullet that says naive peeking would give a 19% false-positive rate.
4. **Probability B beats A** (45 s). Run it with the PyMC engine. Show posteriors, "99.9% probability" and the expected loss.
5. **Observational** (75 s). Generate the simulated observational study (true effect 2). The raw difference is about 5.9; matching gives 1.9, with DoWhy 1.5 and EconML 2.0 as cross-checks. Show the balance plot.
6. **Panel** (45 s). Generate the panel (true effect 5), run difference-in-differences, then synthetic control and its placebo chart.
7. **Explore** (30 s). Peeking simulation: 20% vs 5% false positives.

Tips: load the page once beforehand with `ABLAB_WARMUP_PYMC=true` so the PyMC step is instant; the first PyMC model otherwise takes a few seconds to compile.
