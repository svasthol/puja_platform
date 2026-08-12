"use client";

import { useEffect } from "react";
import Link from "next/link";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Unhandled error:", error);
  }, [error]);

  return (
    <div className="min-h-[70vh] flex items-center justify-center p-8">
      <div className="text-center max-w-md">
        <div className="h-2 bg-header-grad rounded-t-lg mb-6" />
        <div className="text-4xl mb-4">&#x1F305;</div>
        <h1 className="font-noto-telugu text-2xl text-text-primary mb-1">
          అనూహ్యమైన లోపం
        </h1>
        <p className="font-playfair italic text-text-secondary mb-4">
          Something went wrong
        </p>
        <p className="font-lora text-text-secondary text-sm mb-6 leading-relaxed">
          An unexpected error occurred. Please try again or return to today.
        </p>
        <div className="flex gap-3 justify-center flex-wrap">
          <button
            onClick={reset}
            className="px-6 py-3 rounded-lg bg-accent text-white font-lora text-sm font-semibold hover:opacity-90 transition-opacity min-h-[44px]"
          >
            Try Again
          </button>
          <Link
            href="/"
            className="px-6 py-3 rounded-lg border border-accent text-accent font-lora text-sm font-semibold hover:bg-accent/5 transition-colors min-h-[44px] flex items-center"
          >
            Go to Today
          </Link>
        </div>
      </div>
    </div>
  );
}
