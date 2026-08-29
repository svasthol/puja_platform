"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
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
import { SectionHeader } from "@/components/ui/section-header";
import { Textarea } from "@/components/ui/textarea";
import {
  createCategory,
  createPuja,
  fetchCategories,
  fetchMedia,
  fetchPujas,
  reorderCategories,
  reorderPujas,
  updateCategory,
} from "@/lib/api/catalog";
import { categoryEntityUuid } from "@/lib/catalog/entity-id";
import { canEditCatalog } from "@/lib/auth/roles";
import { useAdminMe } from "@/lib/hooks/use-admin-me";

export default function CatalogPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const selectedCatId = Number(searchParams.get("cat") || "0") || null;

  const { data: me } = useAdminMe();
  const canEdit = canEditCatalog(me);
  const qc = useQueryClient();

  const [catName, setCatName] = useState("");
  const [catDesc, setCatDesc] = useState("");
  const [pujaName, setPujaName] = useState("");
  const [pujaPrice, setPujaPrice] = useState("1500");
  const [pujaPriceMax, setPujaPriceMax] = useState("2000");
  const [pujaDuration, setPujaDuration] = useState("90");
  const [message, setMessage] = useState<string | null>(null);

  const { data: catData, isLoading: catsLoading } = useQuery({
    queryKey: ["admin", "catalog", "categories"],
    queryFn: fetchCategories,
  });

  const categories = catData?.categories ?? [];
  const categoryIds = categories.map((c) => c.id).join(",");
  const activeCat = selectedCatId ?? categories[0]?.id ?? null;

  useEffect(() => {
    if (!selectedCatId && categories[0]) {
      router.replace(`/console/catalog?cat=${categories[0].id}`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- categoryIds tracks list changes
  }, [categoryIds, selectedCatId, router]);

  const { data: pujaData, isLoading: pujasLoading } = useQuery({
    queryKey: ["admin", "catalog", "pujas", activeCat],
    queryFn: () => fetchPujas(activeCat!),
    enabled: activeCat != null,
  });

  const selectedCategory = categories.find((c) => c.id === activeCat);

  const { data: catMedia } = useQuery({
    queryKey: ["admin", "catalog", "media", "category", activeCat],
    queryFn: () => fetchMedia("category", categoryEntityUuid(activeCat!)),
    enabled: activeCat != null,
  });

  const categoryPreviewUrl =
    catMedia?.items.find((m) => m.upload_status === "ready" && m.id === selectedCategory?.image_media_id)
      ?.public_url ??
    catMedia?.items.find((m) => m.upload_status === "ready")?.public_url ??
    null;

  const [editDesc, setEditDesc] = useState("");

  useEffect(() => {
    setEditDesc(selectedCategory?.description ?? "");
  }, [selectedCategory?.id, selectedCategory?.description]);

  const createCatMutation = useMutation({
    mutationFn: () =>
      createCategory({
        name: catName.trim(),
        description: catDesc.trim() || undefined,
        change_reason: "admin-ui",
      }),
    onSuccess: async (cat) => {
      setCatName("");
      setCatDesc("");
      setMessage("Category created.");
      await qc.invalidateQueries({ queryKey: ["admin", "catalog", "categories"] });
      router.replace(`/console/catalog?cat=${cat.id}`);
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const createPujaMutation = useMutation({
    mutationFn: () =>
      createPuja({
        category_id: activeCat!,
        name: pujaName.trim(),
        default_price: pujaPrice,
        price_max: pujaPriceMax || String(Number(pujaPrice) + 500),
        duration_minutes: Number(pujaDuration) || 90,
        change_reason: "admin-ui",
      }),
    onSuccess: async (puja) => {
      setPujaName("");
      await qc.invalidateQueries({ queryKey: ["admin", "catalog", "pujas"] });
      router.push(`/console/catalog/pujas/${puja.id}`);
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const toggleCatMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      updateCategory(id, { is_active, change_reason: is_active ? "re-enabled" : "disabled" }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["admin", "catalog", "categories"] });
    },
  });

  const activePujasInCategory = (pujaData?.pujas ?? []).filter((p) => p.is_active).length;

  const pujaThumbKey = (pujaData?.pujas ?? []).map((p) => `${p.id}:${p.hero_media_id ?? ""}`).join(",");
  const { data: pujaThumbUrls } = useQuery({
    queryKey: ["admin", "catalog", "puja-thumbs", pujaThumbKey],
    queryFn: async () => {
      const pujas = pujaData?.pujas ?? [];
      const entries = await Promise.all(
        pujas
          .filter((p) => p.hero_media_id)
          .map(async (p) => {
            const media = await fetchMedia("puja", p.id);
            const url =
              media.items.find(
                (m) => m.id === p.hero_media_id && m.upload_status === "ready",
              )?.public_url ?? null;
            return [p.id, url] as const;
          }),
      );
      return Object.fromEntries(entries) as Record<string, string | null>;
    },
    enabled: (pujaData?.pujas?.length ?? 0) > 0,
    staleTime: 60_000,
  });

  const reorderCatMutation = useMutation({
    mutationFn: (ordered_ids: number[]) =>
      reorderCategories({ ordered_ids, change_reason: "admin-ui" }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["admin", "catalog", "categories"] });
    },
  });

  const reorderPujaMutation = useMutation({
    mutationFn: (ordered_ids: string[]) =>
      reorderPujas({
        category_id: activeCat!,
        ordered_ids,
        change_reason: "admin-ui",
      }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["admin", "catalog", "pujas"] });
    },
  });

  const moveCategory = (catId: number, direction: "up" | "down") => {
    const ids = categories.map((c) => c.id);
    const idx = ids.indexOf(catId);
    if (idx < 0) return;
    const swap = direction === "up" ? idx - 1 : idx + 1;
    if (swap < 0 || swap >= ids.length) return;
    const next = [...ids];
    [next[idx], next[swap]] = [next[swap], next[idx]];
    reorderCatMutation.mutate(next);
  };

  const movePuja = (pujaId: string, direction: "up" | "down") => {
    const pujas = pujaData?.pujas ?? [];
    const ids = pujas.map((p) => p.id);
    const idx = ids.indexOf(pujaId);
    if (idx < 0) return;
    const swap = direction === "up" ? idx - 1 : idx + 1;
    if (swap < 0 || swap >= ids.length) return;
    const next = [...ids];
    [next[idx], next[swap]] = [next[swap], next[idx]];
    reorderPujaMutation.mutate(next);
  };

  const requestDisableCategory = () => {
    if (!selectedCategory) return;
    if (!selectedCategory.is_active) {
      toggleCatMutation.mutate({ id: selectedCategory.id, is_active: true });
      return;
    }
    if (activePujasInCategory > 0) {
      const ok = window.confirm(
        `Hide category "${selectedCategory.name}" from the customer app?\n\n` +
          `${activePujasInCategory} active puja(s) in this category will also disappear from GET /v1/pujas until you re-enable them.\n\n` +
          "This is a soft off (is_active=false) — not a hard delete. Booking history is preserved.",
      );
      if (!ok) return;
    }
    toggleCatMutation.mutate({ id: selectedCategory.id, is_active: false });
  };

  const saveCatMutation = useMutation({
    mutationFn: () =>
      updateCategory(activeCat!, {
        description: editDesc.trim() || null,
        change_reason: "admin-ui",
      }),
    onSuccess: async () => {
      setMessage("Category updated.");
      await qc.invalidateQueries({ queryKey: ["admin", "catalog", "categories"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  return (
    <>
      <Header
        title="Catalogue builder"
        description="Manage categories, pujas, content, addons, and media."
      />
      <PageContent>
        <CatalogReadOnlyBanner me={me} />
        <Alert tone="info" className="mb-4">
          <strong>Catalogue policy:</strong> there is no hard delete. &quot;Off&quot; / &quot;Disable&quot; sets{" "}
          <code className="text-xs">is_active=false</code> — the row stays in Postgres for bookings and
          history. Customer app reads <code className="text-xs">GET /v1/pujas</code> (active only).
          Re-enable anytime from this screen.
        </Alert>

        <div className="grid items-start gap-6 lg:grid-cols-[minmax(280px,300px)_1fr]">
          <aside className="space-y-4">
            <Card className="overflow-hidden !p-0">
              <div className="border-b border-surface-border px-5 py-4">
                <CardTitle className="text-base">Categories</CardTitle>
                <CardDescription className="!mt-0.5">{categories.length} total</CardDescription>
              </div>
              {catsLoading && <p className="p-5 text-sm text-ink-muted">Loading…</p>}
              <ul className="max-h-[min(420px,50vh)] divide-y divide-surface-border overflow-y-auto">
                {categories.map((cat) => (
                  <li key={cat.id} className="flex items-stretch">
                    <button
                      type="button"
                      onClick={() => router.push(`/console/catalog?cat=${cat.id}`)}
                      className={`flex min-w-0 flex-1 items-start justify-between gap-2 px-5 py-3 text-left transition hover:bg-surface ${
                        activeCat === cat.id
                          ? "border-l-2 border-brand bg-brand/5"
                          : "border-l-2 border-transparent"
                      }`}
                    >
                      <div className="min-w-0">
                        <p className="truncate font-medium text-ink">{cat.name}</p>
                        <p className="truncate text-xs text-ink-faint">{cat.slug}</p>
                      </div>
                      <Badge tone={cat.is_active ? "success" : "warning"}>
                        {cat.is_active ? "On" : "Off"}
                      </Badge>
                    </button>
                    {canEdit && (
                      <div className="flex flex-col border-l border-surface-border">
                        <button
                          type="button"
                          className="px-2 text-xs text-ink-muted hover:bg-surface"
                          onClick={() => moveCategory(cat.id, "up")}
                          aria-label="Move category up"
                        >
                          ↑
                        </button>
                        <button
                          type="button"
                          className="px-2 text-xs text-ink-muted hover:bg-surface"
                          onClick={() => moveCategory(cat.id, "down")}
                          aria-label="Move category down"
                        >
                          ↓
                        </button>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </Card>

            {canEdit && (
              <Card>
                <CardTitle className="text-base">New category</CardTitle>
                <form
                  className="mt-4 space-y-3"
                  onSubmit={(e) => {
                    e.preventDefault();
                    createCatMutation.mutate();
                  }}
                >
                  <div>
                    <Label htmlFor="cat-name">Name</Label>
                    <Input
                      id="cat-name"
                      value={catName}
                      onChange={(e) => setCatName(e.target.value)}
                      placeholder="Housewarming"
                      maxLength={100}
                      required
                      className="mt-1.5"
                    />
                  </div>
                  <div>
                    <Label htmlFor="cat-desc">Description</Label>
                    <Textarea
                      id="cat-desc"
                      value={catDesc}
                      onChange={(e) => setCatDesc(e.target.value)}
                      rows={2}
                      className="mt-1.5"
                    />
                  </div>
                  <Button type="submit" className="w-full" disabled={createCatMutation.isPending}>
                    Add category
                  </Button>
                </form>
              </Card>
            )}
          </aside>

          <main className="min-w-0 space-y-5">
            {!activeCat ? (
              <Card>
                <p className="text-sm text-ink-muted">Create a category to start adding pujas.</p>
              </Card>
            ) : (
              <>
                <SectionHeader
                  title={selectedCategory?.name ?? "Category"}
                  description={`${pujaData?.pujas.length ?? 0} pujas · slug ${selectedCategory?.slug ?? "—"}`}
                  actions={
                    canEdit && selectedCategory ? (
                      <Button
                        variant="secondary"
                        className="text-xs"
                        onClick={requestDisableCategory}
                      >
                        {selectedCategory.is_active
                          ? "Hide from customer app"
                          : "Show in customer app"}
                      </Button>
                    ) : undefined
                  }
                />

                {canEdit && selectedCategory && (
                  <div className="grid gap-5 lg:grid-cols-2">
                    <Card>
                      <CardTitle className="text-base">Details</CardTitle>
                      <form
                        className="mt-4 space-y-3"
                        onSubmit={(e) => {
                          e.preventDefault();
                          saveCatMutation.mutate();
                        }}
                      >
                        <div>
                          <Label htmlFor="edit-cat-desc">Description</Label>
                          <Textarea
                            id="edit-cat-desc"
                            value={editDesc}
                            onChange={(e) => setEditDesc(e.target.value)}
                            rows={3}
                            className="mt-1.5"
                          />
                        </div>
                        <Button type="submit" disabled={saveCatMutation.isPending}>
                          Save details
                        </Button>
                      </form>
                    </Card>

                    <Card>
                      <CardTitle className="text-base">Category image</CardTitle>
                      <div className="mt-4">
                        <MediaUploader
                          entityType="category"
                          entityId={categoryEntityUuid(selectedCategory.id)}
                          disabled={!canEdit}
                          previewUrl={categoryPreviewUrl}
                          onUploaded={async (media) => {
                            await updateCategory(selectedCategory.id, {
                              image_media_id: media.id,
                              change_reason: "hero image",
                            });
                            await qc.invalidateQueries({ queryKey: ["admin", "catalog", "categories"] });
                            await qc.invalidateQueries({
                              queryKey: ["admin", "catalog", "media", "category", activeCat],
                            });
                            setMessage("Category image updated.");
                          }}
                        />
                      </div>
                    </Card>
                  </div>
                )}

                {canEdit && (
                  <Card>
                    <CardTitle className="text-base">New puja</CardTitle>
                    <form
                      className="mt-4 grid gap-4 sm:grid-cols-2"
                      onSubmit={(e) => {
                        e.preventDefault();
                        createPujaMutation.mutate();
                      }}
                    >
                      <div className="sm:col-span-2">
                        <Label htmlFor="puja-name">Name</Label>
                        <Input
                          id="puja-name"
                          value={pujaName}
                          onChange={(e) => setPujaName(e.target.value)}
                          required
                          className="mt-1.5"
                        />
                      </div>
                      <div>
                        <Label htmlFor="puja-price">Default price (₹)</Label>
                        <Input
                          id="puja-price"
                          type="number"
                          min={1}
                          value={pujaPrice}
                          onChange={(e) => setPujaPrice(e.target.value)}
                          className="mt-1.5"
                        />
                      </div>
                      <div>
                        <Label htmlFor="puja-price-max">Price max (₹)</Label>
                        <Input
                          id="puja-price-max"
                          type="number"
                          min={1}
                          value={pujaPriceMax}
                          onChange={(e) => setPujaPriceMax(e.target.value)}
                          className="mt-1.5"
                        />
                      </div>
                      <div>
                        <Label htmlFor="puja-duration">Duration (minutes)</Label>
                        <Input
                          id="puja-duration"
                          type="number"
                          min={1}
                          value={pujaDuration}
                          onChange={(e) => setPujaDuration(e.target.value)}
                          className="mt-1.5"
                        />
                      </div>
                      <div className="flex items-end sm:col-span-2">
                        <Button type="submit" className="w-full sm:w-auto" disabled={createPujaMutation.isPending}>
                          Create & edit
                        </Button>
                      </div>
                    </form>
                  </Card>
                )}

                <Card className="overflow-hidden !p-0">
                  <div className="border-b border-surface-border px-5 py-4">
                    <CardTitle className="text-base">Pujas in this category</CardTitle>
                  </div>
                  {pujasLoading && <p className="p-5 text-sm text-ink-muted">Loading…</p>}
                  <ul className="divide-y divide-surface-border">
                    {(pujaData?.pujas ?? []).length === 0 && !pujasLoading && (
                      <li className="px-5 py-10 text-center text-sm text-ink-muted">
                        No pujas yet — create one above.
                      </li>
                    )}
                    {(pujaData?.pujas ?? []).map((puja, idx) => (
                      <li key={puja.id} className="flex items-stretch">
                        <Link
                          href={`/console/catalog/pujas/${puja.id}`}
                          className="flex min-w-0 flex-1 items-center gap-4 px-5 py-4 transition hover:bg-surface"
                        >
                          <div className="h-12 w-12 shrink-0 overflow-hidden rounded-lg border border-surface-border bg-gradient-to-br from-brand/20 to-brand/5">
                            {pujaThumbUrls?.[puja.id] ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img
                                src={pujaThumbUrls[puja.id]!}
                                alt=""
                                className="h-full w-full object-cover"
                              />
                            ) : (
                              <div className="flex h-full w-full items-center justify-center text-xs text-ink-faint">
                                —
                              </div>
                            )}
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="font-medium text-ink">{puja.name}</p>
                            <p className="text-xs text-ink-faint">
                              ₹{puja.default_price}
                              {puja.price_max ? ` – ₹${puja.price_max}` : ""}
                              {puja.duration_minutes ? ` · ${puja.duration_minutes} min` : ""}
                            </p>
                          </div>
                          <div className="flex shrink-0 items-center gap-3">
                            <Badge tone={puja.is_active ? "success" : "warning"}>
                              {puja.is_active ? "Active" : "Off"}
                            </Badge>
                            <span className="text-sm text-brand-glow">Edit →</span>
                          </div>
                        </Link>
                        {canEdit && (
                          <div className="flex flex-col border-l border-surface-border">
                            <button
                              type="button"
                              className="px-2 text-xs text-ink-muted hover:bg-surface disabled:opacity-30"
                              disabled={idx === 0}
                              onClick={() => movePuja(puja.id, "up")}
                              aria-label="Move puja up"
                            >
                              ↑
                            </button>
                            <button
                              type="button"
                              className="px-2 text-xs text-ink-muted hover:bg-surface disabled:opacity-30"
                              disabled={idx === (pujaData?.pujas.length ?? 0) - 1}
                              onClick={() => movePuja(puja.id, "down")}
                              aria-label="Move puja down"
                            >
                              ↓
                            </button>
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                </Card>
              </>
            )}
          </main>
        </div>

        {message && <Alert tone="success">{message}</Alert>}
      </PageContent>
    </>
  );
}
