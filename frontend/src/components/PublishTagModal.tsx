"use client";

import { useState } from "react";

interface PublishTagModalProps {
  open: boolean;
  onClose: () => void;
  onPublish: (tag: string) => Promise<void>;
}

export function PublishTagModal({ open, onClose, onPublish }: PublishTagModalProps) {
  const [tag, setTag] = useState("");
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!tag.trim()) return;
    setPublishing(true);
    setError(null);
    try {
      await onPublish(tag.trim());
      setTag("");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Publish failed");
    } finally {
      setPublishing(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal panel" onClick={(e) => e.stopPropagation()}>
        <h2 style={{ margin: "0 0 0.5rem" }}>Publish tag</h2>
        <p className="muted" style={{ margin: "0 0 1rem", fontSize: "0.875rem" }}>
          Creates an immutable manifest from the current spec. Same content produces the same digest.
        </p>
        <form onSubmit={(e) => void submit(e)}>
          <div className="form-field">
            <label htmlFor="tag-name">Tag name</label>
            <input
              id="tag-name"
              placeholder="e.g. 1.1, latest, staging"
              value={tag}
              onChange={(e) => setTag(e.target.value)}
              autoFocus
            />
          </div>
          {error && <p className="error" style={{ marginBottom: "0.75rem" }}>{error}</p>}
          <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn" disabled={publishing || !tag.trim()}>
              {publishing ? "Publishing…" : "Publish tag"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
