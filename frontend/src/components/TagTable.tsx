"use client";

import Link from "next/link";
import type { MetricTag } from "@/lib/types";
import { DigestChip } from "./DigestChip";

interface TagTableProps {
  metricId: string;
  tags: MetricTag[];
  onDeprecate?: (tag: string) => void;
}

export function TagTable({ metricId, tags, onDeprecate }: TagTableProps) {
  if (!tags.length) {
    return <p className="muted">No tags published yet. Publish a tag to create an immutable manifest.</p>;
  }

  return (
    <table className="registry-table">
      <thead>
        <tr>
          <th>Tag</th>
          <th>Digest</th>
          <th>Published</th>
          <th>Status</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {tags.map((t) => (
          <tr key={t.id}>
            <td>
              <Link href={`/metrics/${metricId}/tags/${encodeURIComponent(t.tag)}`} className="tag-name">
                {t.tag}
              </Link>
            </td>
            <td><DigestChip digest={t.digest} /></td>
            <td className="muted">
              {new Date(t.published_at).toLocaleDateString()}
              {t.published_by && ` · ${t.published_by}`}
            </td>
            <td>
              <span className={`pill ${t.status === "published" ? "pill-success" : t.status === "deprecated" ? "pill-muted" : "pill-warning"}`}>
                {t.status}
              </span>
            </td>
            <td>
              <div className="registry-table-actions">
                <Link href={`/metrics/${metricId}/tags/${encodeURIComponent(t.tag)}`} className="btn btn-secondary btn-sm">
                  View
                </Link>
                <Link href={`/apply?metric=${metricId}&tag=${encodeURIComponent(t.tag)}`} className="btn btn-secondary btn-sm">
                  Pull
                </Link>
                {t.status === "published" && onDeprecate && (
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => onDeprecate(t.tag)}>
                    Deprecate
                  </button>
                )}
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
