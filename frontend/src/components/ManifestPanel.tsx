export function ManifestPanel({ manifest, title = "Manifest" }: { manifest: Record<string, unknown>; title?: string }) {
  return (
    <div className="panel manifest-panel">
      <h2 style={{ margin: "0 0 0.5rem", fontSize: "1rem" }}>{title}</h2>
      <p className="muted" style={{ margin: "0 0 0.75rem", fontSize: "0.8125rem" }}>
        Immutable snapshot referenced by tag digest.
      </p>
      <pre>{JSON.stringify(manifest, null, 2)}</pre>
    </div>
  );
}
