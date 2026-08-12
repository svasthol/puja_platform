import { Suspense } from "react";

import CatalogPage from "./catalog-page-inner";

function CatalogFallback() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center p-8 text-sm text-ink-muted">
      Loading catalogue…
    </div>
  );
}

export default function CatalogRoutePage() {
  return (
    <Suspense fallback={<CatalogFallback />}>
      <CatalogPage />
    </Suspense>
  );
}
