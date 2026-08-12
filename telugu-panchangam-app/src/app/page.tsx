"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth() + 1;
    const day = now.getDate();
    router.replace(`/${year}/${month}/${day}`);
  }, [router]);

  return (
    <div className="flex items-center justify-center min-h-[80vh]">
      <div className="text-center space-y-3">
        <h1 className="font-noto-telugu text-3xl text-accent">
          తెలుగు పంచాంగం
        </h1>
        <p className="text-label font-lora animate-pulse">Loading...</p>
      </div>
    </div>
  );
}
