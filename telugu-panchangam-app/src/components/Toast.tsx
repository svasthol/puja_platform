"use client";

import { useEffect } from "react";

interface ToastProps {
  message: string;
  duration?: number;
  visible: boolean;
  onHide: () => void;
}

export default function Toast({ message, duration = 2000, visible, onHide }: ToastProps) {
  useEffect(() => {
    if (visible) {
      const timer = setTimeout(onHide, duration);
      return () => clearTimeout(timer);
    }
  }, [visible, duration, onHide]);

  if (!visible) return null;

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[300] bg-text-primary text-cream px-4 py-2 rounded-lg font-lora text-sm shadow-lg animate-fade-up no-print">
      {message}
    </div>
  );
}
