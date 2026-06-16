"use client";

import { useCallback, useState } from "react";
import { api } from "@/lib/api";

export default function UploadPage() {
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const handleFiles = useCallback(async (files: FileList | File[]) => {
    const list = Array.from(files);
    if (!list.length) return;
    setUploading(true);
    setError(null);
    try {
      const res = await api.uploadArtifacts(list);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }, []);

  return (
    <div>
      <header className="page-header">
        <p className="eyebrow">Artifact ingestion</p>
        <h1>Upload Artifacts</h1>
        <p className="muted">Excel, SQL, DAX, Python, and CSV metric definitions.</p>
      </header>

      <div
        className={`dropzone panel${dragging ? " dropzone-active" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); void handleFiles(e.dataTransfer.files); }}
      >
        <p>Drop files here or choose files</p>
        <label className="btn" style={{ display: "inline-block", marginTop: "1rem" }}>
          Choose files
          <input
            type="file"
            multiple
            hidden
            accept=".xlsx,.xlsm,.sql,.dax,.py,.csv"
            onChange={(e) => e.target.files && void handleFiles(e.target.files)}
          />
        </label>
        {uploading && <p className="muted">Uploading and queuing parse jobs…</p>}
      </div>

      {error && <p className="error">{error}</p>}

      {result && (
        <div className="panel" style={{ marginTop: "1rem" }}>
          <h2>Uploaded</h2>
          <div className="list">
            {result.artifacts?.map((a: any) => (
              <div className="card" key={a.id}>
                <span className="pill">{a.artifact_type}</span>
                <h3>{a.filename}</h3>
                <p className="muted">Status: {a.status} · Job queued</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
