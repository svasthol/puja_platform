"use client";

import { useState } from "react";
import Link from "next/link";
import LanguageToggle from "./LanguageToggle";
import CitySearch from "./CitySearch";
import LearnModal from "./LearnModal";

export default function AppHeader() {
  const [showLearn, setShowLearn] = useState(false);

  return (
    <>
    <header className="bg-header-grad">
      <div className="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between">
        {/* Left: App title */}
        <Link href="/" className="flex flex-col justify-center min-h-[44px] py-1">
          <span className="font-noto-telugu text-white text-lg leading-tight">
            తెలుగు పంచాంగం
          </span>
          <span className="font-playfair italic text-white/80 text-xs">
            Telugu Panchangam
          </span>
        </Link>

        {/* Right: Controls */}
        <div className="flex items-center gap-2">
          <CitySearch />
          <LanguageToggle />
        </div>
      </div>

      {/* Quick links — scrollable on mobile, ? button pinned right */}
      <div className="max-w-4xl mx-auto pb-2 flex items-center">
        <div
          className="flex items-center gap-4 overflow-x-auto scrollbar-hide whitespace-nowrap px-4 flex-1"
          style={{ WebkitOverflowScrolling: "touch" }}
        >
          <Link
            href="/festivals"
            className="flex-shrink-0 inline-flex items-center min-h-[40px] py-2 text-white/70 hover:text-white text-xs font-lora transition-colors"
          >
            <span className="font-noto-telugu">పండుగలు</span>
            <span className="ml-1">Festivals</span>
          </Link>
          <Link
            href="/muhurtam"
            className="flex-shrink-0 inline-flex items-center min-h-[40px] py-2 text-white/70 hover:text-white text-xs font-lora transition-colors"
          >
            <span className="font-noto-telugu">ముహూర్తం</span>
            <span className="ml-1">Muhurtam</span>
          </Link>
          <Link
            href="/nakshatra"
            className="flex-shrink-0 inline-flex items-center min-h-[40px] py-2 text-white/70 hover:text-white text-xs font-lora transition-colors"
          >
            <span className="font-noto-telugu">నక్షత్రం</span>
            <span className="ml-1">Nakshatra</span>
          </Link>
          <Link
            href="/reminders"
            className="flex-shrink-0 inline-flex items-center min-h-[40px] py-2 text-white/70 hover:text-white text-xs font-lora transition-colors"
          >
            <span className="font-noto-telugu">పితృ స్మరణ</span>
            <span className="ml-1">Reminders</span>
          </Link>
          <Link
            href="/about"
            className="flex-shrink-0 inline-flex items-center min-h-[40px] py-2 text-white/70 hover:text-white text-xs font-lora italic transition-colors"
          >
            How it works?
          </Link>
          {/* Trailing spacer so the last link is fully scrollable into view */}
          <span className="flex-shrink-0 pr-2" aria-hidden="true" />
        </div>
        <button
          onClick={() => setShowLearn(true)}
          className="flex-shrink-0 px-4 text-white/50 hover:text-white text-xs font-lora transition-colors"
          aria-label="What is Panchangam?"
        >
          ?
        </button>
      </div>
    </header>
    {showLearn && <LearnModal onClose={() => setShowLearn(false)} />}
    </>
  );
}
