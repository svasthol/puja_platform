"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { PartnerReadOnlyBanner } from "@/components/partners/read-only-banner";
import { Header } from "@/components/layout/header";
import { PageContent } from "@/components/layout/page-content";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { fetchPujariPricing, replacePujariPricing } from "@/lib/api/partners";
import { canEditPartnerPricing } from "@/lib/auth/roles";
import { useAdminMe } from "@/lib/hooks/use-admin-me";

export default function PartnerPricingPage() {
  const params = useParams();
  const pujariId = String(params.id);
  const qc = useQueryClient();
  const { data: me } = useAdminMe();
  const canEdit = canEditPartnerPricing(me);

  const [prices, setPrices] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);

  const { data: pricing, isLoading } = useQuery({
    queryKey: ["admin", "pujaris", "pricing", pujariId],
    queryFn: () => fetchPujariPricing(pujariId),
  });

  useEffect(() => {
    if (pricing) {
      const next: Record<string, string> = {};
      for (const row of pricing.items) {
        if (row.base_price != null && row.base_price !== "") {
          next[row.puja_id] = row.base_price;
        }
      }
      setPrices(next);
    }
  }, [pricing]);

  const saveMutation = useMutation({
    mutationFn: () => {
      const items = Object.entries(prices)
        .filter(([, v]) => v.trim() !== "")
        .map(([puja_id, base_price]) => ({ puja_id, base_price: base_price.trim() }));
      return replacePujariPricing(pujariId, {
        items,
        change_reason: "admin-ui",
      });
    },
    onSuccess: async () => {
      setMessage("Pricing saved — dispatch and customer quotes use pricing_resolver.");
      await qc.invalidateQueries({ queryKey: ["admin", "pujaris"] });
      await qc.invalidateQueries({ queryKey: ["admin", "pujaris", "pricing", pujariId] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  return (
    <>
      <Header
        title={pricing?.full_name ?? "Partner pricing"}
        description={
          pricing
            ? `${pricing.phone} · ${pricing.verification_status}`
            : "Loading…"
        }
      />
      <PageContent>
        <Link href="/console/partners" className="text-sm text-brand-glow hover:underline">
          ← Back to partners
        </Link>

        <PartnerReadOnlyBanner me={me} />

        <Card>
          <CardTitle>Puja pricing matrix</CardTitle>
          <CardDescription>
            Set base_price per puja. Leave blank to omit from dispatch eligibility. Catalog default
            and price_max shown for reference.
          </CardDescription>

          {isLoading && <p className="mt-4 text-sm text-ink-muted">Loading…</p>}

          {!isLoading && pricing && (
            <div className="mt-6 overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-sm">
                <thead>
                  <tr className="border-b border-surface-border text-ink-muted">
                    <th className="pb-3 pr-4 font-medium">Puja</th>
                    <th className="pb-3 pr-4 font-medium">Default (₹)</th>
                    <th className="pb-3 pr-4 font-medium">Max (₹)</th>
                    <th className="pb-3 font-medium">Partner price (₹)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-border">
                  {pricing.items.map((row) => (
                    <tr key={row.puja_id}>
                      <td className="py-3 pr-4">
                        <p className="font-medium text-ink">{row.puja_name}</p>
                        <p className="text-xs text-ink-faint">{row.puja_slug}</p>
                      </td>
                      <td className="py-3 pr-4 text-ink-muted">{row.default_price}</td>
                      <td className="py-3 pr-4 text-ink-muted">{row.price_max ?? "—"}</td>
                      <td className="py-3">
                        <Label htmlFor={`price-${row.puja_id}`} className="sr-only">
                          Price for {row.puja_name}
                        </Label>
                        <Input
                          id={`price-${row.puja_id}`}
                          type="number"
                          min={0}
                          placeholder="—"
                          disabled={!canEdit}
                          value={prices[row.puja_id] ?? ""}
                          onChange={(e) =>
                            setPrices((prev) => ({ ...prev, [row.puja_id]: e.target.value }))
                          }
                          className="max-w-[140px]"
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {canEdit && (
            <div className="mt-6">
              <Button
                type="button"
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending || isLoading}
              >
                {saveMutation.isPending ? "Saving…" : "Save pricing"}
              </Button>
            </div>
          )}
        </Card>

        {message && (
          <Alert tone={message.toLowerCase().includes("fail") || message.includes("exceeds") ? "error" : "success"}>
            {message}
          </Alert>
        )}
      </PageContent>
    </>
  );
}
