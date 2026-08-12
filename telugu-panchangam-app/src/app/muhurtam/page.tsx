import MuhurtamFinder from "@/components/MuhurtamFinder";

export const metadata = {
  title: "ముహూర్తం — Muhurtam Finder | Telugu Panchangam",
  description:
    "Find auspicious Muhurtam windows based on Nakshatra, Yoga, and Tithi. Excludes Rahukalam and Yamagandam.",
};

export default function MuhurtamPage() {
  return <MuhurtamFinder />;
}
