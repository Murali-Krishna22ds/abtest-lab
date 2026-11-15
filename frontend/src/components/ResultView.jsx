import React from "react";
import { BayesCharts, DidChart, FrequentistCharts, PsmCharts, SequentialCharts, SyntheticCharts } from "./charts.jsx";
import { Fact } from "./ui.jsx";
import { fmtP, num, pct, pts, signed } from "../format.js";

const VERDICT = { positive: "Positive finding", negative: "Negative finding", mixed: "Mixed results", inconclusive: "Inconclusive", neutral: "Neutral" };

export default function ResultView({ out, config }) {
  const { method, result, narrative } = out;
  return (
    <div className="card" id="result" aria-live="polite">
      <h2>4 · What the data say</h2>
      <div style={{ marginTop: 10 }}>
        <span className={`verdict ${narrative.verdict}`}>{VERDICT[narrative.verdict] || narrative.verdict}</span>
        <h2 className="headline">{narrative.headline}</h2>
      </div>
      <Facts method={method} result={result} />
      <ul className="plain">{narrative.summary.map((s, i) => <li key={i}>{s}</li>)}</ul>
      {out.truth && <Truth truth={out.truth} />}
      {narrative.caveats?.length > 0 && (
        <div className="callout">
          <strong>Before you act on this</strong>
          <ul className="plain" style={{ marginTop: 6 }}>{narrative.caveats.map((c, i) => <li key={i}>{c}</li>)}</ul>
        </div>
      )}
      {method === "frequentist" && <><FrequentistCharts result={result} /><FreqTable result={result} /></>}
      {method === "sequential" && <><SequentialCharts result={result} /><LooksTable result={result} /></>}
      {method === "bayesian" && <><BayesCharts result={result} /><BayesTable result={result} /></>}
      {method === "psm" && <PsmCharts result={result} alpha={0.05} />}
      {method === "did" && <DidChart result={result} outcome={config.outcome} />}
      {method === "synthetic_control" && <><SyntheticCharts result={result} outcome={config.outcome} /><Weights result={result} /></>}
      <details>
        <summary>Technical details (raw JSON) · computed in {num(out.runtime_ms, 0)} ms</summary>
        <pre className="json">{JSON.stringify(slim(result), null, 2)}</pre>
      </details>
    </div>
  );
}

function slim(r) {
  return JSON.parse(JSON.stringify(r, (k, v) => (["posterior_density", "diff_histogram", "placebo_gaps", "overlap", "series"].includes(k) ? `[${v?.length ?? 0} points omitted]` : v)));
}

function Truth({ truth }) {
  const parts = Object.entries(truth).map(([k, v]) => `${k.replace("_", " ")} = ${v}`).join(", ");
  return <div className="callout info">This is simulated data, so the real answer is known: <span className="mono">{parts}</span>. Use it to judge whether the method recovered the truth.</div>;
}

function Facts({ method, result: r }) {
  const f = [];
  if (method === "frequentist") {
    const sig = r.comparisons.filter((c) => c.significant).length;
    f.push(<Fact key="a" k="Comparisons" v={r.comparisons.length} />, <Fact key="b" k="Significant" v={sig} s={`after ${r.correction.method === "none" ? "no" : r.correction.method} correction`} />);
    const best = [...r.comparisons].sort((a, b) => a.p_adjusted - b.p_adjusted)[0];
    if (best) f.push(<Fact key="c" k="Smallest adj. p" v={fmtP(best.p_adjusted)} s={`${best.variant_label}`} />);
  } else if (method === "sequential") {
    const last = r.looks[r.looks.length - 1];
    f.push(<Fact key="a" k="Looks" v={r.n_looks} />, <Fact key="b" k="Stopped at (sequential)" v={r.first_look.group_sequential ?? r.first_look.msprt ?? "never"} s={`naive test: look ${r.first_look.naive ?? "never"}`} />,
      <Fact key="c" k="Always-valid p" v={fmtP(r.final.always_valid_p)} />, <Fact key="d" k="Estimate" v={r.metric === "binary" ? pts(last.theta, 2) : signed(last.theta)} />);
  } else if (method === "bayesian") {
    const comps = r.experiments.flatMap((e) => e.comparisons);
    const best = [...comps].sort((a, b) => b.prob_beats_control - a.prob_beats_control)[0];
    f.push(<Fact key="a" k="P(variant beats control)" v={pct(best.prob_beats_control, 1)} s={best.variant_label} />,
      <Fact key="b" k="Expected lift" v={pts(best.expected_diff, 2)} s={`${(best.expected_rel_lift * 100).toFixed(1)}% relative`} />,
      <Fact key="c" k="Expected loss if wrong" v={`${(best.expected_loss_if_choose_variant * 100).toFixed(3)} pts`} />);
  } else if (method === "psm") {
    f.push(<Fact key="a" k="Matched effect" v={signed(r.estimate)} s={`CI ${signed(r.ci_low)} to ${signed(r.ci_high)}`} />, <Fact key="b" k="Raw difference" v={signed(r.naive_difference)} />,
      <Fact key="c" k="Matched treated" v={`${num(r.n_treated_matched, 0)} / ${num(r.n_treated, 0)}`} />, <Fact key="d" k="Max imbalance after" v={r.max_abs_smd_after.toFixed(3)} s={r.balance_ok ? "balanced" : "above 0.10"} />);
  } else if (method === "did") {
    f.push(<Fact key="a" k="DiD effect" v={signed(r.estimate)} s={`CI ${signed(r.ci_low)} to ${signed(r.ci_high)}`} />, <Fact key="b" k="p-value" v={fmtP(r.p_value)} />,
      r.pre_trend && <Fact key="c" k="Parallel-trends p" v={fmtP(r.pre_trend.p_value)} s={r.pre_trend.p_value > 0.05 ? "supports assumption" : "assumption doubtful"} />);
  } else if (method === "synthetic_control") {
    f.push(<Fact key="a" k="Average gap" v={signed(r.estimate)} s={r.relative_effect != null ? `${(r.relative_effect * 100).toFixed(1)}% relative` : ""} />, <Fact key="b" k="Placebo p-value" v={fmtP(r.p_value)} s={`${r.n_placebos} placebo units`} />,
      <Fact key="c" k="Pre-period fit (RMSPE)" v={num(r.pre_rmspe)} />);
  }
  return <div className="facts">{f}</div>;
}

function FreqTable({ result }) {
  return (
    <details open style={{ marginTop: 18 }}>
      <summary>All comparisons</summary>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Test</th><th>Variant vs control</th><th className="n">Control</th><th className="n">Variant</th><th className="n">Difference</th><th className="n">CI</th><th className="n">p</th><th className="n">Adj. p</th><th>Significant</th></tr></thead>
          <tbody>
            {result.comparisons.map((c, i) => {
              const b = c.metric === "binary";
              return (
                <tr key={i}>
                  <td>{c.title}</td><td>{c.variant_label} vs {c.control_label}</td>
                  <td className="n">{b ? pct(c.mean_control, 2) : num(c.mean_control)}</td><td className="n">{b ? pct(c.mean_variant, 2) : num(c.mean_variant)}</td>
                  <td className="n">{b ? pts(c.diff, 2) : signed(c.diff)}</td>
                  <td className="n">{b ? `${(c.ci_low * 100).toFixed(2)} to ${(c.ci_high * 100).toFixed(2)}` : `${num(c.ci_low)} to ${num(c.ci_high)}`}</td>
                  <td className="n">{fmtP(c.p_value)}</td><td className="n">{fmtP(c.p_adjusted)}</td><td>{c.significant ? "Yes" : "No"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function LooksTable({ result }) {
  return (
    <details style={{ marginTop: 18 }}>
      <summary>Look-by-look table</summary>
      <div className="table-wrap">
        <table>
          <thead><tr><th className="n">Look</th><th className="n">Users</th><th className="n">z</th><th className="n">Boundary</th><th className="n">Naive p</th><th className="n">Always-valid p</th><th>Naive says</th><th>Boundary says</th></tr></thead>
          <tbody>
            {result.looks.map((l) => (
              <tr key={l.look}>
                <td className="n">{l.look}</td><td className="n">{num(l.n_control + l.n_variant, 0)}</td><td className="n">{l.z.toFixed(2)}</td><td className="n">±{l.gs_bound.toFixed(2)}</td>
                <td className="n">{fmtP(l.naive_p)}</td><td className="n">{fmtP(l.always_valid_p)}</td><td>{l.naive_reject ? "significant" : "–"}</td><td>{l.gs_reject ? "stop" : "continue"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function BayesTable({ result }) {
  return (
    <details open style={{ marginTop: 18 }}>
      <summary>All comparisons</summary>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Test</th><th>Variant vs control</th><th className="n">P(beats control)</th><th className="n">Expected diff</th><th className="n">{pct(result.hdi_prob, 0)} interval</th><th className="n">Expected loss if shipped</th></tr></thead>
          <tbody>
            {result.experiments.flatMap((e) => e.comparisons).map((c, i) => (
              <tr key={i}>
                <td>{c.title}</td><td>{c.variant_label} vs {c.control_label}</td><td className="n">{pct(c.prob_beats_control, 1)}</td><td className="n">{pts(c.expected_diff, 2)}</td>
                <td className="n">{(c.diff_hdi_low * 100).toFixed(2)} to {(c.diff_hdi_high * 100).toFixed(2)}</td><td className="n">{(c.expected_loss_if_choose_variant * 100).toFixed(3)} pts</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function Weights({ result }) {
  const top = result.weights.filter((w) => w.weight > 0.005);
  return (
    <details style={{ marginTop: 18 }}>
      <summary>Donor weights ({top.length} units contribute)</summary>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Unit</th><th className="n">Weight</th></tr></thead>
          <tbody>{top.map((w) => <tr key={w.unit}><td>{w.unit}</td><td className="n">{(w.weight * 100).toFixed(1)}%</td></tr>)}</tbody>
        </table>
      </div>
    </details>
  );
}
