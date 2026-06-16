import Link from "next/link";
import type { Metric } from "@/lib/types";
import { DigestChip } from "./DigestChip";

export function RepoCard({ metric }: { metric: Metric }) {
  const statusClass =
    metric.status === "approved"
      ? "pill-success"
      : metric.status === "candidate"
        ? "pill-warning"
        : "pill-muted";

  return (
    <Link href={`/metrics/${metric.id}`} className="repo-card">
      <div className="repo-card-header">
        <div>
          <span className={`pill ${statusClass}`}>{metric.status}</span>
          <h3>{metric.canonical_name}</h3>
        </div>
        {metric.latest_digest && (
          <DigestChip digest={metric.latest_digest} />
        )}
      </div>
      <p className="muted" style={{ margin: "0.375rem 0", fontSize: "0.8125rem" }}>
        {metric.description?.slice(0, 120)}
        {(metric.description?.length ?? 0) > 120 ? "…" : ""}
      </p>
      <div className="repo-card-meta">
        <span>{metric.domain}</span>
        <span>{metric.tag_count} tag{metric.tag_count !== 1 ? "s" : ""}</span>
        {metric.latest_tag && <span>latest: {metric.latest_tag}</span>}
        {metric.owner && <span>{metric.owner}</span>}
      </div>
    </Link>
  );
}
