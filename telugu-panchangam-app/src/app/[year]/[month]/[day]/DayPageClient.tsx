"use client";

import { usePanchangam } from "@/hooks/usePanchangam";
import DayDetail from "@/components/DayDetail";
import LoadingState from "@/components/LoadingState";
import ErrorState from "@/components/ErrorState";

interface DayPageClientProps {
  year: string;
  month: string;
  day: string;
}

export default function DayPageClient({ year, month, day }: DayPageClientProps) {
  const dateStr = `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
  const { data, loading, error } = usePanchangam(dateStr);

  if (loading) {
    return (
      <div className="py-6 px-4">
        <LoadingState variant="skeleton" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="py-6 px-4">
        <ErrorState
          message={error ?? "Failed to load Panchangam data."}
          messageTe={error ?? "పంచాంగం డేటా లోడ్ చేయడం విఫలమైంది."}
          onRetry={() => window.location.reload()}
        />
      </div>
    );
  }

  return (
    <div className="py-6 px-4">
      <DayDetail data={data} />
    </div>
  );
}
