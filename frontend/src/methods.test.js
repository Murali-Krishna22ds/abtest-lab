import { describe, expect, it } from "vitest";
import { buildRequest, defaultConfig, optionsFor, method, validate, psmCovariates } from "./methods.js";

const profile = {
  id: "d1", kind: "rows", meta: { labels_id: "L1" },
  suggestions: { binary: ["converted"], numeric: ["revenue", "age"], variant_columns: ["variant"], categorical: ["variant"], datetime_columns: ["day"], unit_columns: [] },
  columns: [
    { name: "variant", role: "categorical", levels: ["control", "b"] }, { name: "converted", role: "binary" },
    { name: "revenue", role: "numeric" }, { name: "age", role: "numeric" }, { name: "day", role: "datetime" },
  ],
};

describe("method catalogue", () => {
  it("defaults the frequentist form from the profile", () => {
    const c = defaultConfig("frequentist", profile);
    expect(c.outcome).toBe("converted");
    expect(c.variant_columns).toEqual(["variant"]);
    expect(validate("frequentist", c, profile)).toBeNull();
  });
  it("blocks row-level methods on aggregated data and aggregated needs no columns", () => {
    const agg = { ...profile, kind: "aggregated" };
    expect(validate("sequential", {}, agg)).toMatch(/one row per user/);
    expect(validate("frequentist", {}, agg)).toBeNull();
  });
  it("requires choices before running", () => {
    expect(validate("did", defaultConfig("did", profile), profile)).toMatch(/Choose/);
  });
  it("never lets the treatment or outcome be a matching covariate", () => {
    const cfg = { treatment: "converted", outcome: "revenue", covariates: ["age", "converted", "revenue"] };
    expect(psmCovariates(cfg)).toEqual(["age"]);
    expect(optionsFor(profile, method("psm").fields.find((f) => f.key === "covariates"), cfg)).not.toContain("revenue");
    expect(buildRequest("psm", cfg, profile).covariates).toEqual(["age"]);
  });
  it("builds a request with the dataset, labels and numeric coercion", () => {
    const body = buildRequest("sequential", { variant_column: "variant", outcome: "converted", time_column: "day", n_looks: "8", spending: "obf", alpha: "0.05" }, profile);
    expect(body).toMatchObject({ dataset_id: "d1", labels_id: "L1", n_looks: 8, alpha: 0.05 });
  });
});
