const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { ...(options?.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  discoverySummary: () => request<any>("/api/discovery/summary"),
  discoveryCandidates: (family?: string) =>
    request<any[]>(`/api/discovery/candidates${family ? `?family=${family}` : ""}`),
  discoveryCandidate: (id: string) => request<any>(`/api/discovery/candidates/${id}`),
  issues: (type?: string) => request<any[]>(`/api/issues${type ? `?issue_type=${type}` : ""}`),
  artifacts: () => request<any[]>("/api/artifacts"),
  uploadArtifacts: async (files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    const res = await fetch(`${API_URL}/api/artifacts/upload`, { method: "POST", body: form });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  search: (q: string) => request<any>(`/api/search?q=${encodeURIComponent(q)}`),
  metrics: () => request<any[]>("/api/metrics"),
  metric: (id: string) => request<any>(`/api/metrics/${id}`),
  approveMetric: (id: string, approvedBy: string) =>
    request<any>(`/api/metrics/${id}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved_by: approvedBy }),
    }),
  functions: () => request<any[]>("/api/functions"),
  function: (id: string) => request<any>(`/api/functions/${id}`),
  clusters: (family?: string) =>
    request<any[]>(`/api/clusters${family ? `?family=${family}` : ""}`),
  cluster: (id: string) => request<any>(`/api/clusters/${id}`),
  datasets: () => request<any[]>("/api/datasets"),
  uploadDataset: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_URL}/api/datasets/upload`, { method: "POST", body: form });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  runMetric: (metricId: string, datasetId: string, navDatasetId?: string) =>
    request<any>(`/api/metrics/${metricId}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dataset_id: datasetId, nav_dataset_id: navDatasetId }),
    }),
  runResults: (runId: string) => request<any>(`/api/runs/${runId}/results`),
  formulaDiff: (a: string, b: string) =>
    request<any>(`/api/formulas/diff?impl_a_id=${a}&impl_b_id=${b}`),
  job: (id: string) => request<any>(`/api/jobs/${id}`),
};
