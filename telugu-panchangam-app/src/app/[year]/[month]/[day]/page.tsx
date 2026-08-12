import type { Metadata } from "next";
import DayPageClient from "./DayPageClient";

export const runtime = "edge";

interface DayPageProps {
  params: { year: string; month: string; day: string };
}

export async function generateMetadata({ params }: DayPageProps): Promise<Metadata> {
  const { year, month, day } = params;
  const date = new Date(`${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`);
  const dateStr = date.toLocaleDateString("en-AU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return {
    title: `పంచాంగం ${dateStr} — Telugu Panchangam`,
    description: `Telugu Panchangam for ${dateStr}. Tithi, Nakshatra, Yoga, Karana, Vara, Rahukalam and sky timings.`,
    openGraph: {
      title: `పంచాంగం ${dateStr}`,
      description: `Telugu Panchangam for ${dateStr}`,
      url: `https://telugupanchangam.app/${year}/${month}/${day}`,
    },
  };
}

export default function DayPage({ params }: DayPageProps) {
  return <DayPageClient year={params.year} month={params.month} day={params.day} />;
}
