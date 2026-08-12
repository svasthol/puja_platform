import type { Metadata } from "next";
import "./globals.css";
import AppHeader from "@/components/AppHeader";
import NavBar from "@/components/NavBar";
import ServiceWorkerRegistration from "@/components/ServiceWorkerRegistration";
import CityWelcome from "@/components/CityWelcome";

export const runtime = "edge";

export const metadata: Metadata = {
  title: "తెలుగు పంచాంగం — Telugu Panchangam",
  description:
    "Free, open-source Telugu Panchangam for any city in the world, any date. Tithi, Nakshatra, Yoga, Karana, Vara, Rahukalam, festivals and more. The sky has no expiry date.",
  keywords: [
    "Telugu Panchangam",
    "తెలుగు పంచాంగం",
    "Tithi",
    "Nakshatra",
    "Telugu calendar",
    "Amavasya",
    "Purnima",
    "Ugadi",
    "Melbourne Telugu",
    "Telugu diaspora",
  ],
  authors: [{ name: "Suhas Atluri" }],
  creator: "Suhas Atluri",
  publisher: "Telugu Panchangam",
  metadataBase: new URL("https://telugupanchangam.app"),
  openGraph: {
    type: "website",
    locale: "te_IN",
    alternateLocale: "en_AU",
    url: "https://telugupanchangam.app",
    siteName: "తెలుగు పంచాంగం",
    title: "తెలుగు పంచాంగం — Telugu Panchangam",
    description:
      "Free Telugu Panchangam for any city, any date. Tithi, Nakshatra, festivals, ancestor reminders and more.",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "తెలుగు పంచాంగం — Telugu Panchangam",
        type: "image/png",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "తెలుగు పంచాంగం — Telugu Panchangam",
    description:
      "Free Telugu Panchangam for any city, any date. The sky has no expiry date.",
    images: ["/og-image.png"],
    creator: "@suhasatluri",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true },
  },
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/favicon.ico" },
    ],
    apple: [
      { url: "/apple-icon-180.png", sizes: "180x180" },
      { url: "/icon-192.png", sizes: "192x192" },
    ],
    shortcut: "/icon-192.png",
  },
  manifest: "/manifest.json",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <link rel="manifest" href="/manifest.json" />
        <meta name="theme-color" content="#D4603A" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="default" />
        <meta name="apple-mobile-web-app-title" content="పంచాంగం" />
        <link rel="apple-touch-icon" sizes="180x180" href="/apple-icon-180.png" />
        <link rel="apple-touch-icon" sizes="192x192" href="/icon-192.png" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,600;1,400;1,600&family=Noto+Sans+Telugu:wght@300;400;600;700&family=Playfair+Display:ital,wght@0,400;0,600;0,700;1,400;1,600;1,700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="antialiased bg-cream text-text-primary font-lora min-h-screen">
        <CityWelcome />
        <AppHeader />
        <NavBar />
        <main>{children}</main>
        <ServiceWorkerRegistration />
      </body>
    </html>
  );
}
