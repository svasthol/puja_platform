"use client";

import { useState, useRef, useEffect } from "react";

interface TooltipProps {
  content: string;
  children: React.ReactNode;
  position?: "top" | "bottom";
}

export default function Tooltip({
  content,
  children,
  position = "top",
}: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const [actualPos, setActualPos] = useState(position);
  const triggerRef = useRef<HTMLSpanElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (visible && triggerRef.current && tooltipRef.current) {
      const triggerRect = triggerRef.current.getBoundingClientRect();
      const tooltipRect = tooltipRef.current.getBoundingClientRect();

      // Flip if tooltip goes off screen
      if (position === "top" && triggerRect.top - tooltipRect.height - 8 < 0) {
        setActualPos("bottom");
      } else if (
        position === "bottom" &&
        triggerRect.bottom + tooltipRect.height + 8 > window.innerHeight
      ) {
        setActualPos("top");
      } else {
        setActualPos(position);
      }
    }
  }, [visible, position]);

  // Close on outside tap (mobile)
  useEffect(() => {
    if (!visible) return;
    const handler = (e: MouseEvent) => {
      if (
        triggerRef.current &&
        !triggerRef.current.contains(e.target as Node) &&
        tooltipRef.current &&
        !tooltipRef.current.contains(e.target as Node)
      ) {
        setVisible(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [visible]);

  return (
    <span
      ref={triggerRef}
      className="relative inline-flex items-center"
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onClick={(e) => {
        e.stopPropagation();
        setVisible((v) => !v);
      }}
      onFocus={() => setVisible(true)}
      onBlur={() => setVisible(false)}
      tabIndex={0}
      role="button"
      aria-describedby={visible ? "tooltip-bubble" : undefined}
    >
      {children}
      {visible && (
        <div
          ref={tooltipRef}
          id="tooltip-bubble"
          role="tooltip"
          className={`absolute z-50 w-56 px-3 py-2 rounded-lg text-xs font-lora leading-relaxed
            bg-[#2C1A0A] text-[#FFF6EE] shadow-lg shadow-black/20
            animate-tooltip-fade
            ${actualPos === "top" ? "bottom-full mb-2" : "top-full mt-2"}
            left-1/2 -translate-x-1/2`}
        >
          {content}
          {/* Arrow */}
          <span
            className={`absolute left-1/2 -translate-x-1/2 w-0 h-0
              border-l-[5px] border-l-transparent
              border-r-[5px] border-r-transparent
              ${
                actualPos === "top"
                  ? "top-full border-t-[5px] border-t-[#2C1A0A]"
                  : "bottom-full border-b-[5px] border-b-[#2C1A0A]"
              }`}
          />
        </div>
      )}
    </span>
  );
}
