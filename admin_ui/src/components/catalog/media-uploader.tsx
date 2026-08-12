"use client";

import { useRef, useState } from "react";

import { uploadCatalogImage } from "@/lib/api/catalog";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils/cn";
import type { MediaItem } from "@/lib/schemas/catalog";

export function MediaUploader({
  entityType,
  entityId,
  disabled,
  label = "Upload image",
  previewUrl,
  onUploaded,
}: {
  entityType: "puja" | "category" | "gallery";
  entityId: string;
  disabled?: boolean;
  label?: string;
  previewUrl?: string | null;
  onUploaded: (media: MediaItem) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  async function handleFile(file: File) {
    setError(null);
    setBusy(true);
    try {
      const media = await uploadCatalogImage(entityType, entityId, file);
      onUploaded(media);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  const blocked = disabled || busy;

  return (
    <div className="space-y-3">
      <p className="text-sm font-medium text-ink">{label}</p>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        {previewUrl && (
          <div className="shrink-0 overflow-hidden rounded-lg border border-surface-border bg-surface">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={previewUrl} alt="" className="h-28 w-28 object-cover" />
          </div>
        )}
        <div
          className={cn(
            "flex min-h-[7rem] flex-1 flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-6 text-center transition",
            dragOver && !blocked
              ? "border-brand bg-brand/10"
              : "border-surface-border bg-surface/40",
            blocked ? "opacity-60" : "cursor-pointer hover:border-brand/60 hover:bg-surface",
          )}
          onDragOver={(e) => {
            e.preventDefault();
            if (!blocked) setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            if (blocked) return;
            const f = e.dataTransfer.files?.[0];
            if (f) void handleFile(f);
          }}
          onClick={() => !blocked && inputRef.current?.click()}
          onKeyDown={(e) => {
            if ((e.key === "Enter" || e.key === " ") && !blocked) {
              e.preventDefault();
              inputRef.current?.click();
            }
          }}
          role="button"
          tabIndex={blocked ? -1 : 0}
        >
          <input
            ref={inputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            className="hidden"
            disabled={blocked}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void handleFile(f);
              e.target.value = "";
            }}
          />
          <p className="text-sm text-ink">
            {busy ? "Uploading…" : "Drop an image here or browse"}
          </p>
          <p className="mt-1 text-xs text-ink-faint">JPEG, PNG, WebP · max 5 MB</p>
          <Button
            type="button"
            variant="secondary"
            className="mt-3 px-3 py-1.5 text-xs"
            disabled={blocked}
            onClick={(e) => {
              e.stopPropagation();
              inputRef.current?.click();
            }}
          >
            Choose file
          </Button>
        </div>
      </div>
      {error && <p className="text-sm text-red-300">{error}</p>}
    </div>
  );
}
