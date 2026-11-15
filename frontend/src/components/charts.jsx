import React from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, ComposedChart, Line, LineChart, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis, Legend as RLegend,
} from "recharts";
import { Chart, Tip } from "./ui.jsx";
import { isNum, num, pct } from "../format.js";

export const COLORS = { control: "#1f9a9a", variant: "#e0552f", alt: ["#e0552f", "#c77d0a", "#7a4fd1", "#2a7fd1", "#b04a8f"], mute: "#8b92a1", ink: "#8b92a1" };
const H = 300;
const shortDate = (s) => (typeof s === "string" && /^\d{4}-\d{2}-\d{2}/.test(s) ? s.slice(0, 10) : s);

/* ---------------------------------------------------------------- forest plot (custom SVG) */
export function ForestPlot({ rows, fmt = (v) => num(v), unit = "", zeroLabel = "no difference" }) {
  const valid = rows.filter((r) => isNum(r.est));
  if (!valid.length) return null;
  const W = 760, left = 250, right = 30, rowH = 36, top = 14, bottom = 38;
  const lo = Math.min(0, ...valid.map((r) => (isNum(r.lo) ? r.lo : r.est)));
  const hi = Math.max(0, ...valid.map((r) => (isNum(r.hi) ? r.hi : r.est)));
  const pad = (hi - lo || 1) * 0.08;
  const a = lo - pad, b = hi + pad;
  const x = (v) => left + ((v - a) / (b - a)) * (W - left - right);
  const height = top + valid.length * rowH + bottom;
  const ticks = Array.from({ length: 5 }, (_, i) => a + ((b - a) * i) / 4);
  return (
    <svg viewBox={`0 0 ${W} ${height}`} width="100%" role="img" aria-label={`Effect estimates with confidence intervals: ${valid.map((r) => `${r.label} ${fmt(r.est)}`).join("; ")}`}>
      {ticks.map((t, i) => (
        <g key={i}>
          <line x1={x(t)} x2={x(t)} y1={top} y2={height - bottom} stroke="var(--grid)" />
          <text x={x(t)} y={height - bottom + 16} textAnchor="middle">{fmt(t)}</text>
        </g>
      ))}
      <line x1={x(0)} x2={x(0)} y1={top - 4} y2={height - bottom} stroke="var(--ink)" strokeWidth="1.5" strokeDasharray="4 3" />
      <text x={x(0)} y={height - 8} textAnchor="middle" style={{ fill: "var(--ink)" }}>0 = {zeroLabel}</text>
      {valid.map((r, i) => {
        const y = top + i * rowH + rowH / 2;
        const color = r.sig === false ? COLORS.mute : r.est >= 0 ? COLORS.control : COLORS.variant;
        return (
          <g key={r.label + i}>
            <text x={left - 12} y={y + 4} textAnchor="end" style={{ fill: "var(--ink)", fontFamily: "var(--sans)", fontSize: 12.5 }}>
              {r.label.length > 36 ? r.label.slice(0, 35) + "…" : r.label}
            </text>
            {isNum(r.lo) && isNum(r.hi) && (
              <>
                <line x1={x(r.lo)} x2={x(r.hi)} y1={y} y2={y} stroke={color} strokeWidth="2.5" strokeLinecap="round" />
                <line x1={x(r.lo)} x2={x(r.lo)} y1={y - 5} y2={y + 5} stroke={color} strokeWidth="2" />
                <line x1={x(r.hi)} x2={x(r.hi)} y1={y - 5} y2={y + 5} stroke={color} strokeWidth="2" />
              </>
            )}
            <rect x={x(r.est) - 5} y={y - 5} width="10" height="10" fill={color} transform={`rotate(45 ${x(r.est)} ${y})`} />
            <title>{`${r.label}: ${fmt(r.est)}${unit}${isNum(r.lo) ? ` (${fmt(r.lo)} to ${fmt(r.hi)})` : ""}`}</title>
          </g>
        );
      })}
    </svg>
  );
}

/* ---------------------------------------------------------------- covariate balance ("love plot") */
export function LovePlot({ rows, threshold = 0.1 }) {
  if (!rows?.length) return null;
  const items = [...rows].sort((p, q) => Math.abs(q.smd_before) - Math.abs(p.smd_before));
  const maxV = Math.max(0.25, ...items.map((r) => Math.max(Math.abs(r.smd_before), Math.abs(r.smd_after)))) * 1.1;
  const W = 760, left = 200, right = 30, rowH = 30, top = 12, bottom = 36;
  const x = (v) => left + (Math.abs(v) / maxV) * (W - left - right);
  const height = top + items.length * rowH + bottom;
  return (
    <svg viewBox={`0 0 ${W} ${height}`} width="100%" role="img" aria-label="Standardized mean differences before and after matching">
      <line x1={x(threshold)} x2={x(threshold)} y1={top} y2={height - bottom} stroke={COLORS.variant} strokeDasharray="4 3" />
      <text x={x(threshold)} y={height - 8} textAnchor="middle">0.10 threshold</text>
      <line x1={left} x2={left} y1={top} y2={height - bottom} stroke="var(--ink)" />
      {[0, maxV / 2, maxV].map((t) => (
        <text key={t} x={x(t)} y={height - bottom + 16} textAnchor="middle">{t.toFixed(2)}</text>
      ))}
      {items.map((r, i) => {
        const y = top + i * rowH + rowH / 2;
        return (
          <g key={r.covariate}>
            <text x={left - 10} y={y + 4} textAnchor="end" style={{ fill: "var(--ink)", fontFamily: "var(--sans)", fontSize: 12.5 }}>{r.covariate.length > 26 ? r.covariate.slice(0, 25) + "…" : r.covariate}</text>
            <line x1={x(r.smd_before)} x2={x(r.smd_after)} y1={y} y2={y} stroke="var(--rule)" strokeWidth="2" />
            <circle cx={x(r.smd_before)} cy={y} r="5.5" fill="none" stroke={COLORS.variant} strokeWidth="2" />
            <circle cx={x(r.smd_after)} cy={y} r="5.5" fill={COLORS.control} />
            <title>{`${r.covariate}: ${Math.abs(r.smd_before).toFixed(3)} before, ${Math.abs(r.smd_after).toFixed(3)} after`}</title>
          </g>
        );
      })}
    </svg>
  );
}

const xAxisDate = (extra = {}) => <XAxis dataKey="x" tickFormatter={shortDate} minTickGap={36} tick={{ fontSize: 11 }} {...extra} />;

/* ---------------------------------------------------------------- frequentist */
export function FrequentistCharts({ result }) {
  const byExp = {};
  result.comparisons.forEach((c) => (byExp[c.experiment] ||= []).push(c));
  return (
    <>
      {Object.entries(byExp).map(([name, comps]) => {
        const binary = comps[0].metric === "binary";
        const e = result.experiments.find((x) => x.name === name);
        const scale = binary ? 100 : 1;
        const rows = comps.map((c) => ({
          label: `${c.variant_label} vs ${c.control_label}`,
          est: c.diff * scale, lo: c.ci_low * scale, hi: c.ci_high * scale, sig: c.significant,
        }));
        const arms = e.arms.map((a) => ({ name: a.label, value: binary ? a.rate : a.mean, control: a.key === e.control }));
        return (
          <React.Fragment key={name}>
            <Chart
              title={`${comps[0].title}: difference vs control`}
              caption={`Each marker is the estimated difference${binary ? " in conversion rate (percentage points)" : ` in average ${comps[0].outcome}`}; the line is the ${pct(1 - result.alpha, 0)} confidence interval. Grey = not significant after correction.`}
            >
              <ForestPlot rows={rows} fmt={(v) => num(v, binary ? 1 : undefined)} unit={binary ? " pts" : ""} />
            </Chart>
            <Chart title={`${comps[0].title}: ${binary ? "conversion rate" : "average " + comps[0].outcome} by variant`}>
              <ResponsiveContainer width="100%" height={Math.max(190, arms.length * 46 + 40)}>
                <BarChart data={arms} layout="vertical" margin={{ left: 20, right: 30 }}>
                  <CartesianGrid horizontal={false} />
                  <XAxis type="number" tickFormatter={(v) => (binary ? pct(v, 0) : num(v))} tick={{ fontSize: 11 }} />
                  <YAxis type="category" dataKey="name" width={150} tick={{ fontSize: 12 }} />
                  <Tooltip content={<Tip fmt={(v) => (binary ? pct(v, 2) : num(v))} />} />
                  <Bar isAnimationActive={false} dataKey="value" name={binary ? "Conversion rate" : "Average"} radius={[0, 4, 4, 0]} fill={COLORS.variant}
                    shape={(p) => <rect {...p} fill={arms[p.index]?.control ? COLORS.control : COLORS.variant} rx="3" />} />
                </BarChart>
              </ResponsiveContainer>
            </Chart>
          </React.Fragment>
        );
      })}
    </>
  );
}

/* ---------------------------------------------------------------- sequential */
export function SequentialCharts({ result }) {
  const k = result.metric === "binary" ? 100 : 1;
  const unit = result.metric === "binary" ? " pts" : "";
  const data = result.looks.map((l) => ({
    look: l.look, n: l.n_control + l.n_variant, z: l.z, bound: l.gs_bound, negBound: -l.gs_bound,
    theta: l.theta * k, band: [l.cs_low * k, l.cs_high * k], naive: Math.max(l.naive_p, 1e-4), valid: Math.max(l.always_valid_p, 1e-4),
  }));
  // Symmetric axis with even bounds; early boundaries can be very wide, so clip them rather than squash the data.
  const maxAbsZ = Math.max(...data.map((d) => Math.abs(d.z)));
  const zMax = Math.min(8, 2 * Math.ceil((Math.max(maxAbsZ, 2.5) + 1) / 2));
  const zTicks = Array.from({ length: zMax + 1 }, (_, i) => -zMax + 2 * i);
  return (
    <>
      <Chart
        title="Test statistic against the stopping boundaries"
        caption="Stop and declare a winner only if the line leaves the corridor. The corridor starts wide (strict) and narrows as data accumulates. The dashed grey lines mark the naive ±1.96 threshold, which is only valid for a single look."
        legend={[[COLORS.variant, "z-statistic"], [COLORS.control, "sequential boundary"], [COLORS.mute, "naive ±1.96"]]}
      >
        <ResponsiveContainer width="100%" height={H}>
          <LineChart data={data} margin={{ left: 0, right: 20, top: 10, bottom: 18 }}>
            <CartesianGrid />
            <XAxis dataKey="look" label={{ value: "look", position: "insideBottom", offset: -2, fontSize: 11 }} tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} domain={[-zMax, zMax]} ticks={zTicks} allowDataOverflow width={40} />
            <Tooltip content={<Tip fmt={(v) => v.toFixed(2)} />} />
            <ReferenceLine y={1.96} stroke={COLORS.mute} strokeDasharray="5 4" />
            <ReferenceLine y={-1.96} stroke={COLORS.mute} strokeDasharray="5 4" />
            <ReferenceLine y={0} stroke="var(--rule)" />
            <Line isAnimationActive={false} dataKey="bound" name="upper boundary" stroke={COLORS.control} strokeWidth={2} dot={false} />
            <Line isAnimationActive={false} dataKey="negBound" name="lower boundary" stroke={COLORS.control} strokeWidth={2} dot={false} />
            <Line isAnimationActive={false} dataKey="z" name="z-statistic" stroke={COLORS.variant} strokeWidth={2.5} dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </Chart>
      <Chart title={`Estimated difference${result.metric === "binary" ? " (percentage points)" : ""} with always-valid confidence band`} caption="The shaded band stays valid however often you look. When it excludes zero the effect is established.">
        <ResponsiveContainer width="100%" height={H}>
          <ComposedChart data={data} margin={{ left: 0, right: 20, top: 10, bottom: 18 }}>
            <CartesianGrid />
            <XAxis dataKey="n" tickFormatter={(v) => v.toLocaleString()} tick={{ fontSize: 11 }} label={{ value: "users observed", position: "insideBottom", offset: -2, fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => v.toFixed(Math.abs(v) < 10 ? 1 : 0)} width={44} />
            <Tooltip content={<Tip fmt={(v) => num(v, 3) + unit} />} />
            <ReferenceLine y={0} stroke="var(--ink)" strokeDasharray="4 3" />
            <Area isAnimationActive={false} dataKey="band" name="always-valid interval" stroke="none" fill={COLORS.control} fillOpacity={0.22} />
            <Line isAnimationActive={false} dataKey="theta" name="estimate" stroke={COLORS.variant} strokeWidth={2.5} dot={{ r: 3 }} />
          </ComposedChart>
        </ResponsiveContainer>
      </Chart>
      <Chart title="p-values over time: naive vs always-valid" caption="The naive p-value dips below the line by chance; the always-valid one only falls when the evidence is real." legend={[[COLORS.mute, "naive p-value"], [COLORS.variant, "always-valid p-value"]]}>
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={data} margin={{ left: 0, right: 20, top: 10, bottom: 18 }}>
            <CartesianGrid />
            <XAxis dataKey="look" tick={{ fontSize: 11 }} />
            <YAxis scale="log" domain={[1e-4, 1]} allowDataOverflow ticks={[1e-4, 1e-3, 1e-2, 0.05, 0.1, 1]} tickFormatter={(v) => (v === 0.05 ? "α" : v < 0.01 ? v.toExponential(0) : String(v))} tick={{ fontSize: 11 }} />
            <Tooltip content={<Tip fmt={(v) => v.toFixed(4)} />} />
            <ReferenceLine y={result.alpha} stroke={COLORS.variant} strokeDasharray="4 3" />
            <Line isAnimationActive={false} dataKey="naive" name="naive p" stroke={COLORS.mute} strokeWidth={2} dot={{ r: 2 }} />
            <Line isAnimationActive={false} dataKey="valid" name="always-valid p" stroke={COLORS.variant} strokeWidth={2.5} dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </Chart>
    </>
  );
}

/* ---------------------------------------------------------------- bayesian */
export function BayesCharts({ result }) {
  const all = result.experiments.flatMap((e) => e.comparisons.map((c) => ({ e, c })));
  const [sel, setSel] = React.useState(0);
  const idx = Math.min(sel, all.length - 1);
  const { e, c } = all[idx];
  const keys = Object.keys(e.posterior_density[0]).filter((k) => k !== "x");
  const shown = keys.filter((k) => k === c.control || k === c.variant);
  const dens = e.posterior_density;
  const hist = c.diff_histogram.map((h) => ({ x: h.x * 100, density: h.density, good: h.x > 0 }));
  const label = (k) => e.labels[k] || k;
  return (
    <>
      {all.length > 1 && (
        <div className="row" style={{ marginTop: 16 }}>
          <label className="field" style={{ minWidth: 280 }}>
            <span className="lbl">Comparison shown in charts</span>
            <select value={idx} onChange={(ev) => setSel(Number(ev.target.value))}>
              {all.map((o, i) => <option key={i} value={i}>{o.c.title}: {o.c.variant_label} vs {o.c.control_label}</option>)}
            </select>
          </label>
        </div>
      )}
      <Chart title="What we believe each conversion rate is" caption="Wider curves mean more uncertainty. The less the curves overlap, the more confident we are that they differ."
        legend={shown.map((k, i) => [k === c.control ? COLORS.control : COLORS.variant, label(k)])}>
        <ResponsiveContainer width="100%" height={H}>
          <AreaChart data={dens} margin={{ left: 0, right: 20, top: 10, bottom: 18 }}>
            <CartesianGrid />
            <XAxis dataKey="x" type="number" domain={["dataMin", "dataMax"]} tickFormatter={(v) => pct(v, 1)} tick={{ fontSize: 11 }} />
            <YAxis hide />
            <Tooltip content={<Tip fmt={(v) => v.toFixed(1)} />} labelFormatter={(v) => pct(v, 2)} />
            {shown.map((k) => (
              <Area isAnimationActive={false} key={k} dataKey={k} name={label(k)} stroke={k === c.control ? COLORS.control : COLORS.variant} fill={k === c.control ? COLORS.control : COLORS.variant} fillOpacity={0.3} strokeWidth={2} />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </Chart>
      <Chart title="Plausible size of the improvement" caption={`Everything right of zero is a world where ${c.variant_label} is better. ${pct(c.prob_beats_control, 1)} of the probability mass lies there.`}>
        <ResponsiveContainer width="100%" height={H - 40}>
          <BarChart data={hist} margin={{ left: 0, right: 20, top: 10, bottom: 18 }} barCategoryGap={0}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="x" type="number" domain={["dataMin", "dataMax"]} tickFormatter={(v) => `${v.toFixed(1)}`} tick={{ fontSize: 11 }} label={{ value: "difference in conversion rate (percentage points)", position: "insideBottom", offset: -2, fontSize: 11 }} />
            <YAxis hide />
            <ReferenceLine x={0} stroke="var(--ink)" strokeDasharray="4 3" />
            <Bar isAnimationActive={false} dataKey="density" name="density" shape={(p) => <rect {...p} fill={hist[p.index]?.good ? COLORS.control : COLORS.variant} opacity="0.8" />} />
          </BarChart>
        </ResponsiveContainer>
      </Chart>
    </>
  );
}

/* ---------------------------------------------------------------- PSM */
export function PsmCharts({ result, alpha }) {
  const rows = [
    { label: "Raw difference (not adjusted)", est: result.naive_difference, sig: false },
    { label: "Matched estimate", est: result.estimate, lo: result.ci_low, hi: result.ci_high, sig: result.ci_low > 0 || result.ci_high < 0 },
  ];
  const cc = result.cross_checks || {};
  if (cc.dowhy_psm) rows.push({ label: "DoWhy matching", est: cc.dowhy_psm.estimate, sig: true });
  if (cc.econml_dr) rows.push({ label: "EconML doubly robust", est: cc.econml_dr.estimate, lo: cc.econml_dr.ci_low, hi: cc.econml_dr.ci_high, sig: cc.econml_dr.ci_low > 0 || cc.econml_dr.ci_high < 0 });
  return (
    <>
      <Chart title="Effect estimates" caption="The raw gap mixes the treatment effect with differences between who got treated. Matching and the cross-checks aim to remove that bias; agreement between them builds confidence.">
        <ForestPlot rows={rows} />
      </Chart>
      <Chart title="Covariate balance" caption="Hollow = before matching, solid = after. Dots left of the dashed line are balanced (difference below 0.10 standard deviations)." legend={[[COLORS.variant, "before"], [COLORS.control, "after"]]}>
        <LovePlot rows={result.balance} />
      </Chart>
      <Chart title="Do treated and untreated units overlap?" caption="Matching only works where both groups have similar units. Little overlap means the estimate rests on few comparable units." legend={[[COLORS.variant, "treated"], [COLORS.control, "untreated"]]}>
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={result.overlap} margin={{ left: 0, right: 20, bottom: 18 }}>
            <CartesianGrid />
            <XAxis dataKey="x" tickFormatter={(v) => v.toFixed(2)} tick={{ fontSize: 11 }} label={{ value: "propensity score", position: "insideBottom", offset: -2, fontSize: 11 }} />
            <YAxis hide />
            <Tooltip content={<Tip fmt={(v) => v.toFixed(3)} />} />
            <Area isAnimationActive={false} dataKey="control" name="untreated" stroke={COLORS.control} fill={COLORS.control} fillOpacity={0.3} />
            <Area isAnimationActive={false} dataKey="treated" name="treated" stroke={COLORS.variant} fill={COLORS.variant} fillOpacity={0.3} />
          </AreaChart>
        </ResponsiveContainer>
      </Chart>
    </>
  );
}

/* ---------------------------------------------------------------- DiD */
export function DidChart({ result, outcome }) {
  const hasCf = result.series.some((s) => isNum(s.counterfactual));
  return (
    <Chart title={`${outcome} over time`} caption="Solid lines are observed averages. The dashed line shows where the treated group would have been if it had followed the control group's trend. The vertical line marks the change."
      legend={[[COLORS.variant, "treated"], [COLORS.control, "control"], ...(hasCf ? [[COLORS.mute, "treated, no-change counterfactual"]] : [])]}>
      <ResponsiveContainer width="100%" height={H + 20}>
        <LineChart data={result.series} margin={{ left: 0, right: 20, top: 10, bottom: 18 }}>
          <CartesianGrid />
          {xAxisDate()}
          <YAxis tick={{ fontSize: 11 }} domain={["auto", "auto"]} tickFormatter={(v) => num(v)} />
          <Tooltip content={<Tip fmt={(v) => num(v)} />} labelFormatter={shortDate} />
          <ReferenceLine x={result.ref_x} stroke="var(--ink)" strokeDasharray="4 3" />
          <Line isAnimationActive={false} dataKey="control" name="control" stroke={COLORS.control} strokeWidth={2.5} dot={false} />
          <Line isAnimationActive={false} dataKey="treated" name="treated" stroke={COLORS.variant} strokeWidth={2.5} dot={false} />
          {hasCf && <Line isAnimationActive={false} dataKey="counterfactual" name="counterfactual" stroke={COLORS.mute} strokeWidth={2} strokeDasharray="6 4" dot={false} connectNulls />}
        </LineChart>
      </ResponsiveContainer>
    </Chart>
  );
}

/* ---------------------------------------------------------------- synthetic control */
export function SyntheticCharts({ result, outcome }) {
  const placeboKeys = Object.keys(result.placebo_gaps?.[0] || {}).filter((k) => /^p\d+$/.test(k));
  return (
    <>
      <Chart title={`${outcome}: treated vs its synthetic twin`} caption="The synthetic twin is a weighted blend of untreated units chosen to match the treated series before the change. After the vertical line, the gap is the estimated effect."
        legend={[[COLORS.variant, "treated"], [COLORS.control, "synthetic"]]}>
        <ResponsiveContainer width="100%" height={H + 20}>
          <LineChart data={result.series} margin={{ left: 0, right: 20, top: 10, bottom: 18 }}>
            <CartesianGrid />
            {xAxisDate()}
            <YAxis tick={{ fontSize: 11 }} domain={["auto", "auto"]} tickFormatter={(v) => num(v)} />
            <Tooltip content={<Tip fmt={(v) => num(v)} />} labelFormatter={shortDate} />
            <ReferenceLine x={result.ref_x} stroke="var(--ink)" strokeDasharray="4 3" />
            <Line isAnimationActive={false} dataKey="synthetic" name="synthetic" stroke={COLORS.control} strokeWidth={2.5} dot={false} />
            <Line isAnimationActive={false} dataKey="treated" name="treated" stroke={COLORS.variant} strokeWidth={2.5} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </Chart>
      <Chart title="Is the gap unusual? Placebo test" caption="Grey lines are the gaps we would see if each untreated unit had been 'treated'. A real effect makes the red line stand out from the grey crowd."
        legend={[[COLORS.variant, "treated unit"], [COLORS.mute, "placebo units"]]}>
        <ResponsiveContainer width="100%" height={H}>
          <LineChart data={result.placebo_gaps} margin={{ left: 0, right: 20, top: 10, bottom: 18 }}>
            <CartesianGrid />
            {xAxisDate()}
            <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => num(v)} />
            <ReferenceLine x={result.ref_x} stroke="var(--ink)" strokeDasharray="4 3" />
            <ReferenceLine y={0} stroke="var(--rule)" />
            {placeboKeys.map((k) => <Line isAnimationActive={false} key={k} dataKey={k} stroke={COLORS.mute} strokeWidth={1} strokeOpacity={0.45} dot={false} />)}
            <Line isAnimationActive={false} dataKey="treated_gap" name="treated gap" stroke={COLORS.variant} strokeWidth={3} dot={false} />
            <Tooltip content={<Tip fmt={(v) => num(v)} />} labelFormatter={shortDate} />
          </LineChart>
        </ResponsiveContainer>
      </Chart>
    </>
  );
}

/* ---------------------------------------------------------------- planner / explore */
export function PowerCurve({ curve, target, nRequired }) {
  return (
    <ResponsiveContainer width="100%" height={H - 40}>
      <LineChart data={curve} margin={{ left: 0, right: 20, top: 10, bottom: 18 }}>
        <CartesianGrid />
        <XAxis dataKey="n_per_arm" tickFormatter={(v) => v.toLocaleString()} tick={{ fontSize: 11 }} label={{ value: "users per arm", position: "insideBottom", offset: -2, fontSize: 11 }} />
        <YAxis domain={[0, 1]} tickFormatter={(v) => pct(v, 0)} tick={{ fontSize: 11 }} />
        <Tooltip content={<Tip fmt={(v) => pct(v, 1)} />} labelFormatter={(v) => `${Number(v).toLocaleString()} per arm`} />
        <ReferenceLine y={target} stroke={COLORS.variant} strokeDasharray="4 3" label={{ value: `${pct(target, 0)} power`, fontSize: 11, fill: "var(--muted)", position: "insideBottomRight" }} />
        <ReferenceLine x={curve.reduce((b, p) => (Math.abs(p.n_per_arm - nRequired) < Math.abs(b.n_per_arm - nRequired) ? p : b)).n_per_arm} stroke="var(--ink)" strokeDasharray="4 3" />
        <Line isAnimationActive={false} dataKey="power" name="power" stroke={COLORS.control} strokeWidth={3} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function RateBars({ data, refLine, fmt = (v) => pct(v, 1), yLabel }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ left: 0, right: 20, top: 10, bottom: 18 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="name" tick={{ fontSize: 12 }} />
        <YAxis tickFormatter={(v) => pct(v, 0)} tick={{ fontSize: 11 }} domain={[0, 1]} label={yLabel && { value: yLabel, angle: -90, position: "insideLeft", fontSize: 11 }} />
        <Tooltip content={<Tip fmt={fmt} />} />
        {refLine !== undefined && <ReferenceLine y={refLine} stroke={COLORS.variant} strokeDasharray="5 4" label={{ value: `α = ${refLine}`, fontSize: 11, fill: "var(--muted)", position: "insideTopRight" }} />}
        <Bar isAnimationActive={false} dataKey="value" name="rate" radius={[4, 4, 0, 0]} shape={(p) => <rect {...p} fill={data[p.index]?.color || COLORS.control} rx="3" />} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function BoundaryChart({ info, series }) {
  const data = info.map((t, i) => ({ t, ...Object.fromEntries(series.map((s) => [s.key, s.values[i]])) }));
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ left: 0, right: 20, top: 10, bottom: 18 }}>
        <CartesianGrid />
        <XAxis dataKey="t" tickFormatter={(v) => pct(v, 0)} tick={{ fontSize: 11 }} label={{ value: "share of planned sample collected", position: "insideBottom", offset: -2, fontSize: 11 }} />
        <YAxis domain={[1.5, "auto"]} tick={{ fontSize: 11 }} tickFormatter={(v) => v.toFixed(1)} allowDataOverflow />
        <Tooltip content={<Tip fmt={(v) => v.toFixed(2)} />} labelFormatter={(v) => pct(v, 0)} />
        <RLegend />
        <ReferenceLine y={1.96} stroke={COLORS.mute} strokeDasharray="5 4" />
        {series.map((s) => <Line isAnimationActive={false} key={s.key} dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={2.5} dot={{ r: 3 }} />)}
      </LineChart>
    </ResponsiveContainer>
  );
}
