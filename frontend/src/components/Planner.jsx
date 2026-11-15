import React, { useEffect, useState } from "react";
import { post } from "../api.js";
import { ErrorBox, Field, Fact, Chart, Spinner } from "./ui.jsx";
import { PowerCurve } from "./charts.jsx";
import { num, pct } from "../format.js";

export default function Planner() {
  const [kind, setKind] = useState("proportion");
  const [mode, setMode] = useState("size");
  const [f, setF] = useState({ baseline: 10, effect: 10, relative: true, delta: 2, sd: 10, power: 80, alpha: 5, ratio: 1, comparisons: 1, traffic: "", nControl: 5000 });
  const [out, setOut] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));

  useEffect(() => {
    let live = true;
    const t = setTimeout(async () => {
      const common = { alpha: f.alpha / 100, ratio: Number(f.ratio), n_comparisons: Number(f.comparisons) };
      const traffic = f.traffic ? { daily_traffic: Number(f.traffic) } : {};
      let path, body;
      if (kind === "proportion") {
        const base = Number(f.baseline) / 100;
        if (mode === "size") {
          path = "/api/power/proportions/sample-size";
          body = { ...common, ...traffic, baseline: base, mde: f.relative ? Number(f.effect) / 100 : Number(f.effect) / 100, relative: f.relative, power: f.power / 100 };
        } else {
          path = "/api/power/proportions/mde";
          body = { ...common, baseline: base, n_control: Number(f.nControl), power: f.power / 100 };
        }
      } else if (mode === "size") {
        path = "/api/power/means/sample-size";
        body = { ...common, ...traffic, delta: Number(f.delta), sd: Number(f.sd), power: f.power / 100 };
      } else {
        path = "/api/power/means/mde";
        body = { ...common, sd: Number(f.sd), n_control: Number(f.nControl), power: f.power / 100 };
      }
      setBusy(true);
      try {
        const r = await post(path, body);
        if (live) { setOut(r); setError(""); }
      } catch (e) {
        if (live) { setError(e.message); setOut(null); }
      } finally {
        if (live) setBusy(false);
      }
    }, 350);
    return () => { live = false; clearTimeout(t); };
  }, [kind, mode, f]);

  const prop = kind === "proportion";
  return (
    <div className="layout">
      <div className="card">
        <h2>Plan an experiment</h2>
        <p className="sub">Work out how many users you need, or what you can detect with the traffic you have.</p>
        <div className="row" style={{ marginBottom: 14 }}>
          <div className="seg" role="group" aria-label="Metric type">
            <button aria-pressed={prop} onClick={() => setKind("proportion")}>Conversion rate</button>
            <button aria-pressed={!prop} onClick={() => setKind("mean")}>Average value</button>
          </div>
          <div className="seg" role="group" aria-label="Question">
            <button aria-pressed={mode === "size"} onClick={() => setMode("size")}>How many users?</button>
            <button aria-pressed={mode === "mde"} onClick={() => setMode("mde")}>What can I detect?</button>
          </div>
        </div>
        <div className="grid cols-2">
          {prop ? (
            <Field label="Current conversion rate (%)"><input type="number" step="0.1" value={f.baseline} onChange={(e) => set("baseline", e.target.value)} /></Field>
          ) : (
            <Field label="Standard deviation of the metric" help="Estimate from past data."><input type="number" step="any" value={f.sd} onChange={(e) => set("sd", e.target.value)} /></Field>
          )}
          {mode === "size" ? (
            prop ? (
              <Field label={f.relative ? "Smallest lift worth detecting (% relative)" : "Smallest lift worth detecting (percentage points)"}>
                <input type="number" step="0.1" value={f.effect} onChange={(e) => set("effect", e.target.value)} />
              </Field>
            ) : (
              <Field label="Smallest difference worth detecting"><input type="number" step="any" value={f.delta} onChange={(e) => set("delta", e.target.value)} /></Field>
            )
          ) : (
            <Field label="Users per group you can afford"><input type="number" step="100" value={f.nControl} onChange={(e) => set("nControl", e.target.value)} /></Field>
          )}
          {prop && mode === "size" && (
            <label className="check" style={{ gridColumn: "1 / -1" }}>
              <input type="checkbox" checked={f.relative} onChange={(e) => set("relative", e.target.checked)} />
              <span>Express the lift as a relative change (10% of 10% = 1 point)</span>
            </label>
          )}
          <Field label="Power (%)" help="Chance of detecting the effect if it is real."><input type="number" value={f.power} min="50" max="99" onChange={(e) => set("power", e.target.value)} /></Field>
          <Field label="Significance level α (%)" help="Accepted false-positive rate."><input type="number" step="0.5" value={f.alpha} min="0.1" max="20" onChange={(e) => set("alpha", e.target.value)} /></Field>
          <Field label="Variants compared with control" help="Applies a Bonferroni correction."><input type="number" min="1" value={f.comparisons} onChange={(e) => set("comparisons", e.target.value)} /></Field>
          <Field label="Treatment : control split" help="1 = equal; 2 = twice as many in treatment."><input type="number" step="0.5" min="0.1" value={f.ratio} onChange={(e) => set("ratio", e.target.value)} /></Field>
          {mode === "size" && <Field label="Daily traffic (optional)" help="Users entering the test per day."><input type="number" value={f.traffic} onChange={(e) => set("traffic", e.target.value)} /></Field>}
        </div>
      </div>
      <div className="card">
        <h2>Result {busy && <Spinner />}</h2>
        <ErrorBox error={error} />
        {out && mode === "size" && <SizeResult out={out} prop={prop} f={f} />}
        {out && mode === "mde" && <MdeResult out={out} prop={prop} baseline={Number(f.baseline) / 100} />}
      </div>
    </div>
  );
}

function SizeResult({ out, prop, f }) {
  return (
    <>
      <p style={{ fontSize: 17 }}>
        {prop ? (
          <>To reliably detect a lift from <b className="num">{pct(out.baseline, 2)}</b> to <b className="num">{pct(out.target, 2)}</b>, </>
        ) : (
          <>To reliably detect a difference of <b className="num">{num(out.delta)}</b> (about <span className="num">{num(out.standardized_effect, 2)}</span> standard deviations), </>
        )}
        you need <b className="num">{num(out.n_control, 0)}</b> users in control and <b className="num">{num(out.n_treatment, 0)}</b> in treatment.
        {out.days_needed && <> At {num(Number(f.traffic), 0)} users a day, that is about <b>{out.days_needed} day{out.days_needed === 1 ? "" : "s"}</b>.</>}
      </p>
      <div className="facts">
        <Fact k="Total users" v={num(out.n_total, 0)} />
        <Fact k="Achieved power" v={pct(out.achieved_power, 1)} />
        <Fact k="α used" v={pct(out.alpha_adjusted, 2)} s={out.n_comparisons > 1 ? `Bonferroni for ${out.n_comparisons}` : "single comparison"} />
      </div>
      <Chart title="Power by sample size" caption="Power rises with sample size and levels off. The dark dashed line is the size you need.">
        <PowerCurve curve={out.curve} target={out.power} nRequired={out.n_control} />
      </Chart>
      <div className="callout info">Smaller effects need far more users: halving the detectable effect roughly quadruples the sample.</div>
    </>
  );
}

function MdeResult({ out, prop, baseline }) {
  return (
    <>
      <p style={{ fontSize: 17 }}>
        With <b className="num">{num(out.n_control, 0)}</b> users in control and <b className="num">{num(out.n_treatment, 0)}</b> in treatment you can reliably detect
        {prop ? (
          <> a change of <b className="num">{(out.absolute_mde * 100).toFixed(2)} percentage points</b> (from {pct(baseline, 1)} to {pct(baseline + out.absolute_mde, 2)}), a <b className="num">{(out.relative_mde * 100).toFixed(1)}%</b> relative lift.</>
        ) : (
          <> a difference of <b className="num">{num(out.absolute_mde)}</b> (<span className="num">{num(out.standardized_mde, 2)}</span> standard deviations).</>
        )}
      </p>
      <div className="callout info">Smaller true effects than this will usually be missed. If that effect is too big to be realistic, you need more users or a longer test.</div>
    </>
  );
}
