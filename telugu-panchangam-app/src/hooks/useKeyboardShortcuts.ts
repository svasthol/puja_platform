"use client";

import { useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";

interface ShortcutOptions {
  year?: number;
  month?: number;
  day?: number;
  view?: "day" | "month";
  onPrint?: () => void;
  onShare?: () => void;
  onLearnModal?: () => void;
}

export function useKeyboardShortcuts(options: ShortcutOptions = {}) {
  const router = useRouter();
  const { year, month, day, view, onPrint, onShare, onLearnModal } = options;

  const isTyping = useCallback(() => {
    const el = document.activeElement;
    if (!el) return false;
    const tag = el.tagName.toLowerCase();
    return (
      tag === "input" ||
      tag === "textarea" ||
      tag === "select" ||
      (el as HTMLElement).isContentEditable
    );
  }, []);

  const isModalOpen = useCallback(() => {
    return document.querySelector('[role="dialog"]:not([hidden])') !== null;
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape" && isTyping()) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      const goToToday = () => {
        const now = new Date();
        const y = now.getFullYear();
        const m = now.getMonth() + 1;
        const d = now.getDate();
        router.push(view === "month" ? `/${y}/${m}` : `/${y}/${m}/${d}`);
      };

      const stepDay = (delta: number) => {
        if (!year || !month || !day) return;
        const date = new Date(year, month - 1, day + delta);
        router.push(`/${date.getFullYear()}/${date.getMonth() + 1}/${date.getDate()}`);
      };

      const stepMonth = (delta: number) => {
        if (!year || !month) return;
        const date = new Date(year, month - 1 + delta, 1);
        router.push(`/${date.getFullYear()}/${date.getMonth() + 1}`);
      };

      switch (e.key) {
        case "ArrowLeft":
          if (isModalOpen()) return;
          e.preventDefault();
          if (view === "day") stepDay(-1);
          else stepMonth(-1);
          break;
        case "ArrowRight":
          if (isModalOpen()) return;
          e.preventDefault();
          if (view === "day") stepDay(1);
          else stepMonth(1);
          break;
        case "t":
        case "T":
          if (isModalOpen()) return;
          e.preventDefault();
          goToToday();
          break;
        case "m":
        case "M":
          if (isModalOpen() || !year || !month) return;
          e.preventDefault();
          router.push(`/${year}/${month}`);
          break;
        case "d":
        case "D": {
          if (isModalOpen() || !year || !month) return;
          e.preventDefault();
          const d = day ?? new Date().getDate();
          router.push(`/${year}/${month}/${d}`);
          break;
        }
        case "f":
        case "F":
          if (isModalOpen()) return;
          e.preventDefault();
          router.push("/festivals");
          break;
        case "u":
        case "U":
          if (isModalOpen()) return;
          e.preventDefault();
          router.push("/muhurtam");
          break;
        case "n":
        case "N":
          if (isModalOpen()) return;
          e.preventDefault();
          router.push("/nakshatra");
          break;
        case "r":
        case "R":
          if (isModalOpen()) return;
          e.preventDefault();
          router.push("/reminders");
          break;
        case "/":
          if (isModalOpen()) return;
          e.preventDefault();
          router.push("/about");
          break;
        case "?":
          e.preventDefault();
          if (onLearnModal) onLearnModal();
          break;
        case "p":
        case "P":
          if (isModalOpen()) return;
          if (view === "month" && onPrint) {
            e.preventDefault();
            onPrint();
          }
          break;
        case "s":
        case "S":
          if (isModalOpen()) return;
          e.preventDefault();
          if (onShare) onShare();
          else navigator.clipboard.writeText(window.location.href).catch(() => {});
          break;
        default:
          break;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isTyping, isModalOpen, router, year, month, day, view, onPrint, onShare, onLearnModal]);
}
