import React, { useEffect, useState } from "react";
import { post } from "../api.js";
import { BoundaryChart, COLORS, RateBars } from "./charts.jsx";
import { Chart, ErrorBox, Field, Spinner } from "./ui.jsx";
import { pct } from "../format.js";

export default function Explore() {
  return (
    <div className="grid" style={{ gap: 18 }}>
      <Peeking />
      <Multiple />
    </div>
  );
}

function useStudy() {
  const [out, setOut] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async (path, body) => {
    setBusy(true);
    setError("");
    try {
      setOut(await post(path, body));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  return { out, error, busy, run };
}

const NAMES = { fixed_horizon: "Test once at the end", naive_peeking: "Peek, stop at first p < 0.05", group_sequential: "Group-sequential", msprt: "Always-valid (mSPRT)" };
const COLOR = { fixed_horizon: COLORS.mute, naive_peeking: COLORS.variant, group_sequential: COLORS.control, msprt: "#7a4fd1" };

function Peeking() {
  const [looks, setLooks] = useState(10);
  const [lift, setLift] = useState(0);
  const { out, error, busy, run } = useStudy();
  const [bounds, setBounds] = useState(null);

  useEffect(() => {
    const n = Number(looks);
    if (!(n >= 2 && n <= 50)) return;
    Promise.all([post("/api/sequential/boundaries", { n_looks: n, spending: "obf" }), post("/api/sequential/boundaries", { n_looks: n, spending: "pocock" })])
      .then(([o, p]) => setBounds({ info: o.info_fractions, obf: o.z_bounds, pocock: p.z_bounds }))
      .catch(() => setBounds(null));
  }, [looks]);

  const go = () => run("/api/sequential/peeking-simulation", { n_looks: Number(looks), rel_lift: Number(lift), n_max: 5000, sims: 2000, baseline: 0.1 });
  const rows = out && Object.entries(out.methods).map(([k, v]) => ({ name: NAMES[k], value: v.reject_rate, color: COLOR[k], samples: v.avg_sample_fraction }));
  const null_ = out?.is_null;
  return (
    <div className="card">
      <h2>Why peeking breaks A/B tests</h2>
      <p className="sub">Simulate thousands of experiments and count how often each stopping rule declares a winner. With no real effect, a trustworthy rule should say “winner” only 5% of the time.</p>
      <div className="grid cols-3" style={{ alignItems: "end" }}>
        <Field label="Number of looks"><input type="number" min="2" max="50" value={looks} onChange={(e) => setLooks(e.target.value)} /></Field>
        <Field label="True relative lift" help="0 = no real effect"><input type="number" step="0.05" value={lift} onChange={(e) => setLift(e.target.value)} /></Field>
        <button className="btn" onClick={go} disabled={busy}>{busy ? "Simulating…" : "Run simulation"}</button>
      </div>
      {busy && <p><Spinner>2,000 simulated experiments…</Spinner></p>}
      <ErrorBox error={error} />
      {rows && (
        <Chart title={null_ ? "False-positive rate by stopping rule" : "Power by stopping rule"}
          caption={null_ ? "The dashed line is the 5% error rate we promised. Peeking pushes the real rate far above it; both sequential methods stay at or below it." : "Share of experiments that found the real effect. Sequential methods give up a little power for the right to peek."}>
          <RateBars data={rows} refLine={null_ ? 0.05 : undefined} />
          <div className="table-wrap" style={{ marginTop: 10 }}>
            <table>
              <thead><tr><th>Rule</th><th className="n">{null_ ? "False positives" : "Detected effect"}</th><th className="n">Average share of sample used</th></tr></thead>
              <tbody>{rows.map((r) => <tr key={r.name}><td>{r.name}</td><td className="n">{pct(r.value, 1)}</td><td className="n">{pct(r.samples, 0)}</td></tr>)}</tbody>
            </table>
          </div>
        </Chart>
      )}
      {bounds && (
        <Chart title="How the stopping boundaries behave" caption="Critical |z| at each look. O'Brien-Fleming demands overwhelming evidence early; Pocock is flat. The grey dashed line (1.96) is the naive threshold."
          >
          <BoundaryChart info={bounds.info} series={[{ key: "obf", name: "O'Brien-Fleming", values: bounds.obf, color: COLORS.control }, { key: "pocock", name: "Pocock", values: bounds.pocock, color: "#7a4fd1" }]} />
        </Chart>
      )}
    </div>
  );
}

const M_NAMES = { none: "No correction", bonferroni: "Bonferroni", holm: "Holm", bh: "Benjamini-Hochberg" };

function Multiple() {
  const [m, setM] = useState(20);
  const [mTrue, setMTrue] = useState(5);
  const { out, error, busy, run } = useStudy();
  const go = () => run("/api/multiple-testing/simulation", { m: Number(m), m_true: Number(mTrue), effect_z: 3, sims: 4000 });
  const rows = out && Object.entries(out.methods).map(([k, v]) => ({ key: k, name: M_NAMES[k], ...v }));
  return (
    <div className="card">
      <h2>Testing many things at once</h2>
      <p className="sub">Look at 20 metrics and one will usually look “significant” by luck. Corrections trade a little power for protection. FWER is the chance of any false positive; FDR is the share of discoveries that are false.</p>
      <div className="grid cols-3" style={{ alignItems: "end" }}>
        <Field label="Metrics tested"><input type="number" min="2" max="500" value={m} onChange={(e) => setM(e.target.value)} /></Field>
        <Field label="Of which truly affected"><input type="number" min="0" max="500" value={mTrue} onChange={(e) => setMTrue(e.target.value)} /></Field>
        <button className="btn" onClick={go} disabled={busy}>{busy ? "Simulating…" : "Run simulation"}</button>
      </div>
      {busy && <p><Spinner>4,000 simulated experiments…</Spinner></p>}
      <ErrorBox error={error} />
      {rows && (
        <>
          <Chart title="Chance of at least one false positive (FWER)" caption="The dashed line marks 5%. Bonferroni and Holm hold the family-wise error there; Benjamini-Hochberg intentionally tolerates more false positives to find more real effects.">
            <RateBars data={rows.map((r) => ({ name: r.name, value: r.fwer, color: r.key === "none" ? COLORS.variant : COLORS.control }))} refLine={0.05} />
          </Chart>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Method</th><th className="n">FWER</th><th className="n">FDR</th><th className="n">Power (real effects found)</th></tr></thead>
              <tbody>{rows.map((r) => <tr key={r.key}><td>{r.name}</td><td className="n">{pct(r.fwer, 1)}</td><td className="n">{pct(r.fdr, 1)}</td><td className="n">{pct(r.power, 1)}</td></tr>)}</tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
