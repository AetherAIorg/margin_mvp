"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Metric, MetricTagDetail } from "@/lib/types";
import { Breadcrumbs } from "@/components/Breadcrumbs";
import { DigestChip } from "@/components/DigestChip";
import { ManifestPanel } from "@/components/ManifestPanel";

export default function TagDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const tag = decodeURIComponent(params.tag as string);
  const [metric, setMetric] = useState<Metric | null>(null);
  const [detail, setDetail] = useState<MetricTagDetail | null>(null);
  const [deprecating, setDeprecating] = useState(false);

  useEffect(() => {
    if (!id || !tag) return;
    Promise.all([api.metric(id), api.metricTag(id, tag)])
      .then(([m, d]) => {
        setMetric(m);
        setDetail(d);
      })
      .catch(console.error);
  }, [id, tag]);

  async function deprecate() {
    if (!confirm(`Deprecate tag "${tag}"?`)) return;
    setDeprecating(true);
    try {
      await api.deprecateTag(id, tag);
      const d = await api.metricTag(id, tag);
      setDetail(d);
    } finally {
      setDeprecating(false);
    }
  }

  if (!metric || !detail) return <p className="muted">Loading…</p>;

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Repositories", href: "/metrics" },
          { label: metric.canonical_name, href: `/metrics/${id}` },
          { label: "Tags", href: `/metrics/${id}` },
          { label: tag },
        ]}
      />
      <header className="page-header">
        <p className="eyebrow">Tag manifest</p>
        <h1>{metric.canonical_name}:{tag}</h1>
        <p className="muted">
          Published {new Date(detail.published_at).toLocaleString()}
          {detail.published_by && ` by ${detail.published_by}`}
        </p>
        <div className="page-header-actions">
          <DigestChip digest={detail.digest} showFull />
          <span className={`pill ${detail.status === "published" ? "pill-success" : "pill-muted"}`}>
            {detail.status}
          </span>
          <Link
            href={`/apply?metric=${id}&tag=${encodeURIComponent(tag)}`}
            className="btn"
          >
            Pull & run
          </Link>
          {detail.status === "published" && (
            <button type="button" className="btn btn-secondary" onClick={() => void deprecate()} disabled={deprecating}>
              Deprecate tag
            </button>
          )}
        </div>
      </header>

      <ManifestPanel manifest={detail.manifest} />
    </div>
  );
}
