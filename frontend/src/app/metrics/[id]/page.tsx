"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Metric, MetricTag } from "@/lib/types";
import { Breadcrumbs } from "@/components/Breadcrumbs";
import { TagTable } from "@/components/TagTable";
import { ManifestPanel } from "@/components/ManifestPanel";
import { PublishTagModal } from "@/components/PublishTagModal";
import { DigestChip } from "@/components/DigestChip";

type Tab = "tags" | "overview" | "manifest";

export default function MetricDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [metric, setMetric] = useState<Metric | null>(null);
  const [tags, setTags] = useState<MetricTag[]>([]);
  const [tab, setTab] = useState<Tab>("tags");
  const [approving, setApproving] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);
  const [latestManifest, setLatestManifest] = useState<Record<string, unknown> | null>(null);

  async function load() {
    const [m, t] = await Promise.all([api.metric(id), api.metricTags(id)]);
    setMetric(m);
    setTags(t);
    const latest = m.latest_tag ?? t.find((x) => x.tag === "latest")?.tag ?? t[0]?.tag;
    if (latest) {
      const detail = await api.metricTag(id, latest);
      setLatestManifest(detail.manifest);
    }
  }

  useEffect(() => {
    if (id) void load().catch(console.error);
  }, [id]);

  async function approve() {
    setApproving(true);
    try {
      await api.approveMetric(id, "Investment Operations");
      await load();
    } finally {
      setApproving(false);
    }
  }

  async function publish(tag: string) {
    await api.publishTag(id, tag);
    await load();
  }

  async function deprecate(tag: string) {
    if (!confirm(`Deprecate tag "${tag}"?`)) return;
    await api.deprecateTag(id, tag);
    await load();
  }

  if (!metric) return <p className="muted">Loading…</p>;

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Repositories", href: "/metrics" },
          { label: metric.canonical_name },
        ]}
      />
      <header className="page-header">
        <p className="eyebrow">{metric.domain}</p>
        <h1>{metric.canonical_name}</h1>
        <p className="muted">
          {metric.entity} · {metric.grain} · {metric.tag_count} tags
          {metric.latest_digest && (
            <> · latest <DigestChip digest={metric.latest_digest} /></>
          )}
        </p>
        <div className="page-header-actions">
          <button type="button" className="btn" onClick={() => setPublishOpen(true)}>
            Publish tag
          </button>
          {metric.status !== "approved" && (
            <button type="button" className="btn btn-secondary" onClick={() => void approve()} disabled={approving}>
              Approve repository
            </button>
          )}
          {metric.latest_tag && (
            <Link
              href={`/apply?metric=${id}&tag=${encodeURIComponent(metric.latest_tag)}`}
              className="btn btn-secondary"
            >
              Pull & run
            </Link>
          )}
          {process.env.NEXT_PUBLIC_CATALOG_URL && (
            <a
              href={`${process.env.NEXT_PUBLIC_CATALOG_URL}/assets/metric/${id}`}
              className="btn btn-secondary"
              target="_blank"
              rel="noreferrer"
            >
              View in Catalog
            </a>
          )}
        </div>
      </header>

      <div className="tabs">
        {(["tags", "overview", "manifest"] as Tab[]).map((t) => (
          <button key={t} type="button" className={`tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {tab === "tags" && (
        <TagTable metricId={id} tags={tags} onDeprecate={(tag) => void deprecate(tag)} />
      )}

      {tab === "overview" && (
        <div className="grid grid-2">
          <div className="panel">
            <h2 style={{ marginTop: 0 }}>Overview</h2>
            <p>{metric.description}</p>
            <p className="muted">Owner: {metric.owner ?? "none"} · Status: {metric.status}</p>
          </div>
          {metric.specs?.[0] && (
            <div className="panel">
              <h2 style={{ marginTop: 0 }}>Working spec</h2>
              <ol>
                {metric.specs[0].transformation_plan?.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            </div>
          )}
        </div>
      )}

      {tab === "manifest" && latestManifest && (
        <ManifestPanel manifest={latestManifest} title={`Latest manifest (${metric.latest_tag ?? "—"})`} />
      )}

      <PublishTagModal
        open={publishOpen}
        onClose={() => setPublishOpen(false)}
        onPublish={publish}
      />
    </div>
  );
}
