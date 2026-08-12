import type { Metadata } from "next";
import AboutPage from "@/components/AboutPage";

export const runtime = "edge";

export const metadata: Metadata = {
  title: "How it works — తెలుగు పంచాంగం",
  description:
    "An interactive walkthrough of the Telugu Panchangam engine: how the Sun and Moon's positions become Tithi, Nakshatra, Yoga, Karana and Vara — for any city, any date.",
  openGraph: {
    title: "How it works — Telugu Panchangam",
    description:
      "Interactive explainer of the Panchangam calculation engine: the math, the astronomy, and a live calculator.",
    url: "https://telugupanchangam.app/about",
  },
};

export default function AboutRoute() {
  return <AboutPage />;
}
