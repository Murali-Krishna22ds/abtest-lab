// End-to-end smoke test: drives the real UI in headless Chromium against a running server.
// Usage: BASE_URL=http://127.0.0.1:8000 SHOTS=/tmp/shots node e2e/smoke.mjs
import { chromium } from "playwright";

const BASE = process.env.BASE_URL || "http://127.0.0.1:8000";
const SHOTS = process.env.SHOTS || "";
const errors = [];
let failures = 0;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
// Web-font requests fail in offline environments; the CSS falls back to system fonts, so ignore those.
page.on("console", (m) => m.type() === "error" && !/ERR_NAME_NOT_RESOLVED|ERR_INTERNET_DISCONNECTED/.test(m.text()) && errors.push(`console: ${m.text()}`));

const shot = (name) => SHOTS && page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
const ok = (cond, msg) => { console.log(`${cond ? "PASS" : "FAIL"}  ${msg}`); if (!cond) failures++; };

async function fresh() {
  await page.goto(BASE);
  await page.getByRole("tab", { name: "Analyze data" }).click();
}
async function runMethod(name, { before } = {}) {
  await page.locator(".method", { hasText: name }).click();
  if (before) await before();
  await page.getByRole("button", { name: "Run analysis" }).click();
  await page.getByText("What the data say").waitFor({ timeout: 120000 });
  const headline = await page.locator(".headline").innerText();
  return headline;
}
async function simulate(scenario) {
  await page.locator("details", { hasText: "Generate simulated data" }).first().evaluate((d) => (d.open = true));
  await page.getByLabel("Scenario").selectOption(scenario);
  await page.getByRole("button", { name: "Generate" }).click();
  await page.getByText("simulated, true effect is known").waitFor();
}

await fresh();
await shot("01-landing");
ok(await page.getByRole("heading", { name: /Experiment/ }).isVisible(), "landing page renders");

// 1. Bundled sample -> frequentist with four concurrent tests
await page.getByRole("button", { name: "ab test sessions" }).click();
await page.getByText("15,000 rows").waitFor();
let h = await runMethod("Compare variants");
await shot("02-frequentist");
ok(/comparisons|significant/i.test(h), `frequentist headline: ${h}`);
ok((await page.locator("svg[role=img]").count()) >= 1, "forest plot rendered");

// 2. Sequential
h = await runMethod("Peek safely");
await shot("03-sequential");
ok(/safe to stop|keep collecting|borderline/i.test(h), `sequential headline: ${h}`);

// 3. Bayesian (instant engine, then PyMC)
h = await runMethod("Probability B beats A", { before: () => page.locator("select").filter({ hasText: "Closed-form" }).selectOption("conjugate") });
await shot("04-bayesian");
ok(/probability/i.test(h), `bayesian headline: ${h}`);
h = await runMethod("Probability B beats A", { before: () => page.locator("select").filter({ hasText: "PyMC sampler" }).selectOption("pymc") });
ok(/probability/i.test(h), "bayesian (PyMC engine) completes");

// 4. Observational: PSM on simulated confounded data
await simulate("observational");
h = await runMethod("Observational: matching", {
  before: async () => ok((await page.getByRole("button", { name: "treated", exact: true }).count()) === 0, "treatment column is not offered as a matching covariate"),
});
await shot("05-psm");
ok(/matching|effect/i.test(h), `psm headline: ${h}`);
ok(await page.getByText("simulated data, so the real answer is known").isVisible(), "simulated truth is surfaced");

// 5. Panel: DiD and synthetic control
await simulate("panel");
h = await runMethod("Before/after vs control");
await shot("06-did");
ok(/moved|No clear/i.test(h), `did headline: ${h}`);
h = await runMethod("One treated unit");
await shot("07-synthetic");
ok(/synthetic|No convincing/i.test(h), `synthetic headline: ${h}`);

// 6. Error path: required field cleared disables the button
await page.locator(".method", { hasText: "Compare variants" }).click();
await page.getByRole("button", { name: "group", exact: true }).click(); // deselect the only variant column
ok(await page.getByRole("button", { name: "Run analysis" }).isDisabled(), "incomplete form disables Run");

// 7. Planner
await page.getByRole("tab", { name: "Plan an experiment" }).click();
await page.getByText(/users in control/).waitFor();
await shot("08-planner");
const planText = await page.locator(".card").nth(1).innerText();
ok(/\d[\d,]* users in control/.test(planText), "planner reports required sample size");

// 8. Explore: peeking simulation
await page.getByRole("tab", { name: "Explore the pitfalls" }).click();
await page.getByRole("button", { name: "Run simulation" }).first().click();
await page.getByText("False-positive rate by stopping rule").waitFor({ timeout: 60000 });
await shot("09-explore");
ok(true, "peeking simulation renders");

ok(errors.length === 0, `no browser errors${errors.length ? ": " + errors.slice(0, 3).join(" | ") : ""}`);
await browser.close();
console.log(failures ? `\n${failures} check(s) failed` : "\nAll UI checks passed");
process.exit(failures ? 1 : 0);
