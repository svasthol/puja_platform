"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { CatalogReadOnlyBanner } from "@/components/catalog/read-only-banner";
import { MediaUploader } from "@/components/catalog/media-uploader";
import { Header } from "@/components/layout/header";
import { PageContent } from "@/components/layout/page-content";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Tabs } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  createAddon,
  fetchAddons,
  fetchContent,
  fetchMedia,
  fetchPujaImpact,
  fetchPujas,
  replaceContent,
  updateAddon,
  updatePuja,
} from "@/lib/api/catalog";
import { canEditCatalog } from "@/lib/auth/roles";
import { useAdminMe } from "@/lib/hooks/use-admin-me";
import {
  CONTENT_KIND_LABELS,
  type ContentKind,
  type Puja,
} from "@/lib/schemas/catalog";

type TabId = "details" | "content" | "addons" | "media";

export default function PujaBuilderPage() {
  const params = useParams();
  const pujaId = String(params.id);
  const qc = useQueryClient();
  const { data: me } = useAdminMe();
  const canEdit = canEditCatalog(me);

  const [tab, setTab] = useState<TabId>("details");
  const [message, setMessage] = useState<string | null>(null);
  const [contentKind, setContentKind] = useState<ContentKind>("inclusion");
  const [contentLines, setContentLines] = useState("");

  const { data: allPujas, isLoading: pujaLoading } = useQuery({
    queryKey: ["admin", "catalog", "pujas", "all"],
    queryFn: () => fetchPujas(),
  });
  const puja = allPujas?.pujas.find((p) => p.id === pujaId);

  const { data: impact } = useQuery({
    queryKey: ["admin", "catalog", "puja-impact", pujaId],
    queryFn: () => fetchPujaImpact(pujaId),
    enabled: !!puja,
  });

  const { data: contentData, refetch: refetchContent } = useQuery({
    queryKey: ["admin", "catalog", "content", pujaId, contentKind],
    queryFn: () => fetchContent(pujaId, contentKind),
    enabled: tab === "content" && !!puja,
  });

  const { data: addonsData, refetch: refetchAddons } = useQuery({
    queryKey: ["admin", "catalog", "addons", pujaId],
    queryFn: () => fetchAddons(pujaId),
    enabled: tab === "addons" && !!puja,
  });

  const { data: mediaData, refetch: refetchMedia } = useQuery({
    queryKey: ["admin", "catalog", "media", "puja", pujaId],
    queryFn: () => fetchMedia("puja", pujaId),
    enabled: !!puja,
  });

  const heroUrl =
    mediaData?.items.find((m) => m.upload_status === "ready" && m.id === puja?.hero_media_id)
      ?.public_url ??
    mediaData?.items.find((m) => m.upload_status === "ready" && m.entity_type === "puja")
      ?.public_url ??
    null;

  const galleryItems =
    mediaData?.items.filter((m) => m.upload_status === "ready" && m.entity_type === "gallery") ??
    [];

  const [form, setForm] = useState<Partial<Puja>>({});

  useEffect(() => {
    if (puja) {
      setForm({
        name: puja.name,
        tagline: puja.tagline ?? "",
        description: puja.description ?? "",
        duration_minutes: puja.duration_minutes ?? undefined,
        default_price: puja.default_price,
        price_max: puja.price_max ?? "",
        is_active: puja.is_active,
      });
    }
  }, [puja]);

  useEffect(() => {
    if (contentData) {
      setContentLines(contentData.items.map((i) => i.text).join("\n"));
    }
  }, [contentData, contentKind]);

  const savePujaMutation = useMutation({
    mutationFn: () =>
      updatePuja(pujaId, {
        name: form.name,
        tagline: form.tagline || null,
        description: form.description || null,
        duration_minutes: form.duration_minutes ?? null,
        default_price: form.default_price,
        price_max: form.price_max || null,
        is_active: form.is_active,
        change_reason: "admin-ui",
      }),
    onSuccess: async () => {
      setMessage("Puja saved.");
      await qc.invalidateQueries({ queryKey: ["admin", "catalog", "pujas"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const requestSavePuja = () => {
    if (!puja || !canEdit) return;
    const disabling = puja.is_active && form.is_active === false;
    const hasImpact =
      impact != null &&
      (impact.active_future_bookings > 0 || impact.active_holds_unscoped > 0);
    if (disabling && hasImpact) {
      const ok = window.confirm(
        `Hide "${puja.name}" from the customer app?\n\n` +
          `${impact!.active_future_bookings} future booking(s) and ${impact!.active_holds_unscoped} active hold(s) may be affected.\n\n` +
          "This sets is_active=false (soft off) — not a hard delete. Existing bookings stay in the database.",
      );
      if (!ok) return;
    }
    savePujaMutation.mutate();
  };

  const saveContentMutation = useMutation({
    mutationFn: () => {
      const items = contentLines
        .split("\n")
        .map((t) => t.trim())
        .filter(Boolean)
        .map((text, position) => ({ text, position }));
      return replaceContent(pujaId, {
        kind: contentKind,
        items,
        change_reason: "admin-ui",
      });
    },
    onSuccess: async () => {
      setMessage("Content saved.");
      await refetchContent();
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const [addonName, setAddonName] = useState("");
  const [addonPrice, setAddonPrice] = useState("99");

  const createAddonMutation = useMutation({
    mutationFn: () =>
      createAddon(pujaId, {
        name: addonName.trim(),
        price: addonPrice,
        change_reason: "admin-ui",
      }),
    onSuccess: async () => {
      setAddonName("");
      await refetchAddons();
      setMessage("Addon created.");
    },
    onError: (e: Error) => setMessage(e.message),
  });

  if (pujaLoading) {
    return (
      <>
        <Header title="Puja" description="Loading…" />
        <PageContent>
          <p className="text-sm text-ink-muted">Loading…</p>
        </PageContent>
      </>
    );
  }

  if (!puja) {
    return (
      <>
        <Header title="Puja not found" description="This puja may have been removed." />
        <PageContent>
          <Link href="/console/catalog" className="text-sm text-brand-glow hover:underline">
            ← Back to catalogue
          </Link>
        </PageContent>
      </>
    );
  }

  const showImpact =
    impact && (impact.active_future_bookings > 0 || impact.active_holds_unscoped > 0);

  return (
    <>
      <Header title={puja.name} description={`Slug ${puja.slug}`} />
      <PageContent>
        <div className="flex flex-wrap items-center gap-3">
          <Link
            href={`/console/catalog?cat=${puja.category_id}`}
            className="text-sm text-brand-glow hover:underline"
          >
            ← Back to catalogue
          </Link>
          <Badge tone={puja.is_active ? "success" : "warning"}>
            {puja.is_active ? "Active" : "Disabled"}
          </Badge>
        </div>

        <CatalogReadOnlyBanner me={me} />

        {showImpact && (
          <Alert tone="warning">
            <strong>Impact warning:</strong> {impact!.active_future_bookings} future booking(s) and{" "}
            {impact!.active_holds_unscoped} active hold(s). Price or duration changes may affect
            live quotes.
          </Alert>
        )}

        <Tabs
          tabs={[
            { id: "details", label: "Details" },
            { id: "content", label: "Content" },
            { id: "addons", label: "Addons" },
            { id: "media", label: "Media" },
          ]}
          active={tab}
          onChange={(id) => setTab(id as TabId)}
        />

        {tab === "details" && (
          <Card>
            <CardTitle>Puja details</CardTitle>
            <CardDescription>Core fields shown to customers via GET /v1/pujas.</CardDescription>
            <form
              className="mt-6 grid gap-4 sm:grid-cols-2"
              onSubmit={(e) => {
                e.preventDefault();
                requestSavePuja();
              }}
            >
              <div className="sm:col-span-2">
                <Label htmlFor="puja-name">Name</Label>
                <Input
                  id="puja-name"
                  value={form.name ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  disabled={!canEdit}
                  className="mt-1.5"
                />
              </div>
              <div className="sm:col-span-2">
                <Label htmlFor="puja-tagline">Tagline</Label>
                <Input
                  id="puja-tagline"
                  value={form.tagline ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, tagline: e.target.value }))}
                  disabled={!canEdit}
                  className="mt-1.5"
                />
              </div>
              <div className="sm:col-span-2">
                <Label htmlFor="puja-desc">Description</Label>
                <Textarea
                  id="puja-desc"
                  value={form.description ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                  disabled={!canEdit}
                  rows={4}
                  className="mt-1.5"
                />
              </div>
              <div>
                <Label htmlFor="puja-duration">Duration (minutes)</Label>
                <Input
                  id="puja-duration"
                  type="number"
                  min={1}
                  value={form.duration_minutes ?? ""}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      duration_minutes: e.target.value ? Number(e.target.value) : undefined,
                    }))
                  }
                  disabled={!canEdit}
                  className="mt-1.5"
                />
              </div>
              <div>
                <Label htmlFor="puja-status">Customer app visibility</Label>
                <Select
                  id="puja-status"
                  value={form.is_active ? "1" : "0"}
                  disabled={!canEdit}
                  onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.value === "1" }))}
                  className="mt-1.5"
                >
                  <option value="1">Active (visible in GET /v1/pujas)</option>
                  <option value="0">Off (hidden — soft delete)</option>
                </Select>
              </div>
              <div>
                <Label htmlFor="puja-price">Default price (₹)</Label>
                <Input
                  id="puja-price"
                  value={form.default_price ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, default_price: e.target.value }))}
                  disabled={!canEdit}
                  className="mt-1.5"
                />
              </div>
              <div>
                <Label htmlFor="puja-price-max">Price max (₹)</Label>
                <Input
                  id="puja-price-max"
                  value={form.price_max ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, price_max: e.target.value }))}
                  disabled={!canEdit}
                  className="mt-1.5"
                />
              </div>
              {canEdit && (
                <div className="sm:col-span-2 pt-2">
                  <Button type="submit" disabled={savePujaMutation.isPending}>
                    {savePujaMutation.isPending ? "Saving…" : "Save changes"}
                  </Button>
                </div>
              )}
            </form>
          </Card>
        )}

        {tab === "content" && (
          <Card>
            <CardTitle>Content items</CardTitle>
            <CardDescription>One line per item — replace-all per kind.</CardDescription>
            <div className="mt-6 space-y-4">
              <div className="max-w-xs">
                <Label htmlFor="content-kind">Kind</Label>
                <Select
                  id="content-kind"
                  value={contentKind}
                  onChange={(e) => setContentKind(e.target.value as ContentKind)}
                  className="mt-1.5"
                >
                  {(Object.keys(CONTENT_KIND_LABELS) as ContentKind[]).map((k) => (
                    <option key={k} value={k}>
                      {CONTENT_KIND_LABELS[k]}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="content-lines">Items (one per line)</Label>
                <Textarea
                  id="content-lines"
                  value={contentLines}
                  onChange={(e) => setContentLines(e.target.value)}
                  disabled={!canEdit}
                  rows={12}
                  className="mt-1.5 font-mono text-sm"
                  placeholder={"Flowers and fruits\nPrasad for family"}
                />
              </div>
              {canEdit && (
                <Button
                  type="button"
                  onClick={() => saveContentMutation.mutate()}
                  disabled={saveContentMutation.isPending}
                >
                  Save {CONTENT_KIND_LABELS[contentKind].toLowerCase()}
                </Button>
              )}
            </div>
          </Card>
        )}

        {tab === "addons" && (
          <div className="space-y-5">
            {canEdit && (
              <Card>
                <CardTitle>New addon</CardTitle>
                <form
                  className="mt-4 grid gap-4 sm:grid-cols-[1fr_140px_auto]"
                  onSubmit={(e) => {
                    e.preventDefault();
                    createAddonMutation.mutate();
                  }}
                >
                  <div>
                    <Label htmlFor="addon-name">Name</Label>
                    <Input
                      id="addon-name"
                      value={addonName}
                      onChange={(e) => setAddonName(e.target.value)}
                      required
                      className="mt-1.5"
                    />
                  </div>
                  <div>
                    <Label htmlFor="addon-price">Price (₹)</Label>
                    <Input
                      id="addon-price"
                      type="number"
                      value={addonPrice}
                      onChange={(e) => setAddonPrice(e.target.value)}
                      min={0}
                      className="mt-1.5"
                    />
                  </div>
                  <div className="flex items-end">
                    <Button type="submit" disabled={createAddonMutation.isPending}>
                      Add addon
                    </Button>
                  </div>
                </form>
              </Card>
            )}
            <Card className="overflow-hidden !p-0">
              <div className="border-b border-surface-border px-5 py-4">
                <CardTitle className="text-base">Addons</CardTitle>
                <CardDescription className="!mt-0.5">
                  {(addonsData?.addons ?? []).length} configured
                </CardDescription>
              </div>
              <ul className="divide-y divide-surface-border">
                {(addonsData?.addons ?? []).map((addon) => (
                  <li
                    key={addon.id}
                    className="flex items-center justify-between gap-4 px-5 py-4"
                  >
                    <div>
                      <p className="font-medium text-ink">{addon.name}</p>
                      <p className="text-sm text-ink-muted">₹{addon.price}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge tone={addon.is_active ? "success" : "warning"}>
                        {addon.is_active ? "On" : "Off"}
                      </Badge>
                      {canEdit && (
                        <Button
                          variant="secondary"
                          className="text-xs"
                          onClick={() =>
                            updateAddon(addon.id, {
                              is_active: !addon.is_active,
                              change_reason: "toggle",
                            }).then(() => refetchAddons())
                          }
                        >
                          {addon.is_active ? "Disable" : "Enable"}
                        </Button>
                      )}
                    </div>
                  </li>
                ))}
                {(addonsData?.addons ?? []).length === 0 && (
                  <li className="px-5 py-10 text-center text-sm text-ink-muted">No addons yet.</li>
                )}
              </ul>
            </Card>
          </div>
        )}

        {tab === "media" && (
          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <CardTitle>Hero image</CardTitle>
              <CardDescription>Sets puja hero_media_id after upload.</CardDescription>
              {canEdit && (
                <div className="mt-4">
                  <MediaUploader
                    entityType="puja"
                    entityId={pujaId}
                    previewUrl={heroUrl}
                    onUploaded={async (media) => {
                      await updatePuja(pujaId, {
                        hero_media_id: media.id,
                        change_reason: "hero image",
                      });
                      await qc.invalidateQueries({ queryKey: ["admin", "catalog", "pujas"] });
                      await refetchMedia();
                      setMessage("Hero image set.");
                    }}
                  />
                </div>
              )}
            </Card>
            <Card>
              <CardTitle>Gallery</CardTitle>
              <CardDescription>Additional images for this puja.</CardDescription>
              {canEdit && (
                <div className="mt-4">
                  <MediaUploader
                    entityType="gallery"
                    entityId={pujaId}
                    label="Upload gallery image"
                    onUploaded={async () => {
                      await refetchMedia();
                      setMessage("Gallery image uploaded.");
                    }}
                  />
                </div>
              )}
              {galleryItems.length > 0 && (
                <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {galleryItems.map((m) => (
                    <div
                      key={m.id}
                      className="overflow-hidden rounded-lg border border-surface-border bg-surface"
                    >
                      {m.public_url && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={m.public_url}
                          alt={m.alt_text ?? ""}
                          className="aspect-square w-full object-cover"
                        />
                      )}
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        )}

        {message && (
          <Alert tone={message.toLowerCase().includes("fail") ? "error" : "success"}>
            {message}
          </Alert>
        )}
      </PageContent>
    </>
  );
}
