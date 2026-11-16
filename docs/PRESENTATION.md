# Final presentation (10 minutes)

Deck: [`Experiment_Lab_Final_Presentation.pptx`](Experiment_Lab_Final_Presentation.pptx), 9 slides with speaker notes and timings on each.
Plan for about 1 to 1.5 minutes a slide, leaving a minute for questions.

| # | Slide | Time | Message |
|---|---|---|---|
| 1 | Experiment Lab | 0:30 | A tool that turns experiment data into a verdict a product manager can act on |
| 2 | Teams ship on shaky evidence | 1:00 | Three measured failure modes: 52% (uncorrected multiple tests), 21% (peeking), 7.19 vs a true 2.0 (confounding) |
| 3 | Design | 1:00 | Pure statistics library, thin API, plain-English layer; heavy libraries load lazily |
| 4 | From a CSV to a verdict | 1:30 | **Demo** (`docs/demo/demo.webm` or live, see `DEMO.md`) |
| 5 | Peeking safely | 1:30 | Same 5% promise: 21% false positives naive vs 5.2% group-sequential; the power trade-off |
| 6 | Bayesian and observational | 1:30 | Never trust one method: PyMC vs exact, matching vs DoWhy vs EconML |
| 7 | Results | 1:00 | Measured against known truth; 106 + 5 + 15 tests |
| 8 | Challenges | 1:00 | Bugs found by comparing with something independent (**each intern adds their own story here**) |
| 9 | Limits and next steps | 1:00 | Not deployed from the build environment; single worker; honest assumptions |

## Covering the required topics

* **Problem**: slide 2. **Design**: slide 3 (diagram in `architecture.svg`). **Challenges**: slide 8. **Results**: slides 5 to 7. **Next steps**: slide 9.

## Likely questions

* *Why not just use one library?* DoWhy and EconML do not provide synthetic control, and their matching has no balance diagnostics or fast bootstrap, so we wrote the core ourselves and used the libraries as independent cross-checks.
* *Why is the always-valid test so weak?* It is valid at any stopping time with no planned schedule; that flexibility costs power. When the maximum sample size is known, group-sequential is better (66.6% vs 26.7% power in our simulation).
* *How do you know the sequential boundaries are right?* A million-path Monte Carlo reproduces the 5% error rate (0.0501); see `TEST_RESULTS.md`.
* *Is the Bayesian answer the same as the frequentist one?* With this much data and a flat prior they agree closely; the Bayesian view answers "how likely is B better, and what do I lose if wrong" directly.
* *Can it scale?* Statistics are fast (roughly 10 to 100 ms); the limit is in-memory dataset storage, which is a small interface to swap for Redis.
