const BASE = import.meta.env.VITE_API_URL || "";

function describe(detail, status) {
  if (Array.isArray(detail)) {
    return detail.map((e) => `${(e.loc || []).slice(1).join(".") || "input"}: ${e.msg}`).join("; ");
  }
  return detail || `Request failed (${status})`;
}

async function request(path, options) {
  let res;
  try {
    res = await fetch(BASE + path, options);
  } catch {
    throw new Error("Cannot reach the analysis server. Check that the backend is running.");
  }
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    /* non-JSON error body */
  }
  if (!res.ok) throw new Error(describe(data?.detail, res.status));
  return data;
}

export const get = (path) => request(path);
export const post = (path, body) =>
  request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const upload = (file) => {
  const form = new FormData();
  form.append("file", file);
  return request("/api/datasets", { method: "POST", body: form });
};
export const downloadUrl = (id) => `${BASE}/api/datasets/${id}/download`;
