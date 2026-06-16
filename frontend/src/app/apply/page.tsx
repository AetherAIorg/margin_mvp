import { Suspense } from "react";
import ApplyPageClient from "./ApplyPageClient";

export default function ApplyPage() {
  return (
    <Suspense fallback={<p className="muted">Loading…</p>}>
      <ApplyPageClient />
    </Suspense>
  );
}
