"use client";

import { useState } from "react";

export function DigestChip({ digest, showFull }: { digest: string; showFull?: boolean }) {
  const [copied, setCopied] = useState(false);
  const short = digest.replace("sha256:", "").slice(0, 12);

  async function copy() {
    try {
      await navigator.clipboard.writeText(digest);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  }

  return (
    <span className="digest-chip" title={digest}>
      {showFull ? digest : `sha256:${short}`}
      <button type="button" onClick={(e) => { e.preventDefault(); e.stopPropagation(); void copy(); }}>
        {copied ? "Copied" : "Copy"}
      </button>
    </span>
  );
}
