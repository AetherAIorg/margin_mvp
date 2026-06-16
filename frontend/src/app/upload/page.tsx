"use client";

import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { Breadcrumbs } from "@/components/Breadcrumbs";

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
      <Breadcrumbs items={[{ label: "Push sources" }]} />
      <header className="page-header">
        <p className="eyebrow">Source ingestion</p>
        <h1>Push sources</h1>
        <p className="muted">Upload Excel, SQL, DAX, Python, and CSV artifacts for discovery and indexing.</p>
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
          <h2 style={{ marginTop: 0 }}>Uploaded</h2>
          <table className="registry-table">
            <thead>
              <tr>
                <th>File</th>
                <th>Type</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {result.artifacts?.map((a: any) => (
                <tr key={a.id}>
                  <td>{a.filename}</td>
                  <td><span className="pill">{a.artifact_type}</span></td>
                  <td className="muted">{a.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
