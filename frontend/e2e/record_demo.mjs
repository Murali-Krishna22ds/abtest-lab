// Records a ~2 minute walkthrough of the app as docs/demo/demo.webm.
// Usage: SCRIPT=e2e/record_demo.mjs OUT=../docs/demo scripts/e2e.sh   (from the repo root)
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = process.env.BASE_URL || "http://127.0.0.1:8000";
const OUT = process.env.OUT || "../docs/demo";
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, recordVideo: { dir: OUT, size: { width: 1280, height: 800 } } });
const page = await ctx.newPage();
const pause = (ms) => page.waitForTimeout(ms);
const scrollTo = async (sel) => { await page.locator(sel).first().scrollIntoViewIfNeeded(); await pause(1200); };
const glide = async (y) => { await page.mouse.wheel(0, y); await pause(900); };

await page.goto(BASE);
await pause(2500);

// 1. Plan an experiment
await page.getByRole("tab", { name: "Plan an experiment" }).click();
await page.getByText(/users in control/).waitFor();
await pause(3500);
await page.getByLabel("Smallest lift worth detecting (% relative)").fill("5");
await pause(3000);
await page.getByRole("button", { name: "What can I detect?" }).click();
await pause(3500);

// 2. Analyze a real multi-test dataset
await page.getByRole("tab", { name: "Analyze data" }).click();
await page.getByRole("button", { name: "ab test sessions" }).click();
await page.getByText("15,000 rows").waitFor();
await pause(2500);
await page.locator(".method", { hasText: "Compare variants" }).click();
await pause(2500);
await page.getByRole("button", { name: "Run analysis" }).click();
await page.getByText("What the data say").waitFor();
await pause(3500);
await glide(500); await glide(500); await glide(500); await pause(1500);

// 3. Peek safely
await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" })); await pause(1200);
await page.locator(".method", { hasText: "Peek safely" }).click();
await pause(1800);
await page.getByRole("button", { name: "Run analysis" }).click();
await page.getByText("Safe to stop").waitFor();
await pause(3000);
await glide(600); await glide(500); await pause(2500);

// 4. Probability B beats A
await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" })); await pause(1200);
await page.locator(".method", { hasText: "Probability B beats A" }).click();
await pause(1500);
await page.getByRole("button", { name: "Run analysis" }).click();
await page.getByText("probability of beating").first().waitFor({ timeout: 90000 });
await pause(3500);
await glide(600); await glide(600); await pause(2500);

// 5. Observational study with a known answer
await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" })); await pause(1000);
await page.locator("details", { hasText: "Generate simulated data" }).first().evaluate((d) => (d.open = true));
await page.getByLabel("Scenario").selectOption("observational");
await pause(1200);
await page.getByRole("button", { name: "Generate" }).click();
await page.getByText("simulated, true effect is known").waitFor();
await pause(1500);
await page.locator(".method", { hasText: "Observational: matching" }).click();
await pause(1500);
await page.getByRole("button", { name: "Run analysis" }).click();
await page.getByText("What the data say").waitFor({ timeout: 90000 });
await pause(3500);
await glide(700); await glide(600); await glide(500); await pause(3000);

// 6. Why peeking breaks tests
await page.getByRole("tab", { name: "Explore the pitfalls" }).click();
await pause(1500);
await page.getByRole("button", { name: "Run simulation" }).first().click();
await page.getByText("False-positive rate by stopping rule").waitFor({ timeout: 60000 });
await pause(4000);
await glide(500); await pause(2500);

await ctx.close(); // flushes the video
const file = fs.readdirSync(OUT).find((f) => f.endsWith(".webm"));
fs.renameSync(`${OUT}/${file}`, `${OUT}/demo.webm`);
console.log(`saved ${OUT}/demo.webm`);
await browser.close();
