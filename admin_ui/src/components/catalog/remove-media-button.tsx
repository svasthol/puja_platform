"use client";

import { useState } from "react";

import { deactivateCatalogMedia } from "@/lib/api/catalog";
import { Button } from "@/components/ui/button";

export function RemoveMediaButton({
  mediaId,
  disabled,
  label = "Remove image",
  confirmMessage = "Remove this image from the catalogue? It will be hidden in the customer app.",
  onRemoved,
  onError,
}: {
  mediaId: string;
  disabled?: boolean;
  label?: string;
  confirmMessage?: string;
  onRemoved: () => void | Promise<void>;
  onError?: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);

  async function handleClick() {
    if (!window.confirm(confirmMessage)) return;
    setBusy(true);
    try {
      await deactivateCatalogMedia(mediaId);
      await onRemoved();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Could not remove image.";
      onError?.(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button
      type="button"
      variant="secondary"
      size="sm"
      disabled={disabled || busy}
      onClick={() => void handleClick()}
    >
      {busy ? "Removing…" : label}
    </Button>
  );
}
