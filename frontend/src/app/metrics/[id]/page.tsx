"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";

export default function MetricDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [metric, setMetric] = useState<any>(null);
  const [approving, setApproving] = useState(false);

  useEffect(() => {
    if (id) api.metric(id).then(setMetric).catch(console.error);
  }, [id]);

  async function approve() {
    setApproving(true);
    try {
      const updated = await api.approveMetric(id, "Investment Operations");
      setMetric(updated);
    } finally {
      setApproving(false);
    }
  }

  if (!metric) return <p className="muted">Loading…</p>;
  const spec = metric.specs?.[0];

  return (
    <div>
      <header className="page-header">
        <p className="eyebrow">{metric.domain}</p>
        <h1>{metric.canonical_name}</h1>
        <p className="muted">Status: {metric.status} · Owner: {metric.owner} · Entity: {metric.entity} · Grain: {metric.grain}</p>
      </header>

      <div className="grid grid-2">
        <div className="panel">
          <h2>Definition</h2>
          <p>{metric.description}</p>
          {metric.status !== "approved" && (
            <button className="btn" onClick={() => void approve()} disabled={approving} style={{ marginTop: "1rem" }}>
              Approve as canonical
            </button>
          )}
        </div>

        {spec && (
          <div className="panel">
            <h2>Approved execution plan</h2>
            <ol>
              {spec.transformation_plan?.map((step: string) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
            <h3>Required inputs</h3>
            <pre>{JSON.stringify(spec.required_inputs, null, 2)}</pre>
          </div>
        )}
      </div>
    </div>
  );
}
