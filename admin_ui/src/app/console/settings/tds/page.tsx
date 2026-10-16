"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { fetchTdsFacilitation, updateTdsFacilitation } from "@/lib/api/admin";
import { canEditTdsFacilitation } from "@/lib/auth/roles";
import { useAdminMe } from "@/lib/hooks/use-admin-me";

const ENTITY_TYPE_OPTIONS = ["firm", "trust", "company", "aop", "other"];

export default function TdsFacilitationSettingsPage() {
  const { data: me } = useAdminMe();
  const qc = useQueryClient();
  const canEdit = canEditTdsFacilitation(me);

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "tds-facilitation"],
    queryFn: fetchTdsFacilitation,
  });

  const [noPanRatePct, setNoPanRatePct] = useState("5");
  const [panEntityRatePct, setPanEntityRatePct] = useState("0.1");
  const [individualThreshold, setIndividualThreshold] = useState("500000");
  const [turnoverWarn, setTurnoverWarn] = useState("1800000");
  const [turnoverBlock, setTurnoverBlock] = useState("2000000");
  const [alwaysTaxedTypes, setAlwaysTaxedTypes] = useState<string[]>(ENTITY_TYPE_OPTIONS);
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!data) return;
    setNoPanRatePct(String(data.no_pan_rate_pct));
    setPanEntityRatePct(String(data.pan_entity_rate_pct));
    setIndividualThreshold(String(data.individual_fy_threshold_inr));
    setTurnoverWarn(String(data.fy_turnover_warn_inr));
    setTurnoverBlock(String(data.fy_turnover_block_inr));
    setAlwaysTaxedTypes(data.always_taxed_entity_types);
  }, [data]);

  const mutation = useMutation({
    mutationFn: () =>
      updateTdsFacilitation({
        no_pan_rate_pct: Number(noPanRatePct),
        pan_entity_rate_pct: Number(panEntityRatePct),
        individual_fy_threshold_inr: Number(individualThreshold),
        fy_turnover_warn_inr: Number(turnoverWarn),
        fy_turnover_block_inr: Number(turnoverBlock),
        always_taxed_entity_types: alwaysTaxedTypes,
        change_reason: reason.trim() || undefined,
      }),
    onSuccess: async () => {
      setMessage("Saved — TDS calculator and accrual will use the new slabs.");
      await qc.invalidateQueries({ queryKey: ["admin", "tds-facilitation"] });
    },
    onError: (err: Error) => setMessage(err.message),
  });

  function toggleEntityType(entityType: string) {
    setAlwaysTaxedTypes((prev) =>
      prev.includes(entityType)
        ? prev.filter((t) => t !== entityType)
        : [...prev, entityType],
    );
  }

  return (
    <>
      <Header
        title="TDS facilitation slabs"
        description="Admin-tunable thresholds and rates for Sprint 2 TDS accrual and G2 turnover monitor."
      />
      <div className="max-w-2xl p-8">
        <p className="mb-4 text-sm text-ink-muted">
          <a href="/console/tds" className="text-brand-glow hover:underline">
            ← TDS hub
          </a>
        </p>
        <Card>
          <CardTitle>Current policy</CardTitle>
          <CardDescription>
            Stored in <code className="text-xs">platform_settings.tds_facilitation</code>.
            Individual/HUF use the FY threshold; firm/trust/company types use the PAN rate always.
          </CardDescription>

          {isLoading && <p className="mt-4 text-sm text-ink-muted">Loading…</p>}
          {error && (
            <p className="mt-4 text-sm text-red-300">{(error as Error).message}</p>
          )}

          {data && (
            <div className="mt-6 space-y-4 text-sm text-ink-muted">
              <p>
                No-PAN rate: <strong className="text-ink">{data.no_pan_rate_pct}%</strong> ·
                PAN entity rate: <strong className="text-ink">{data.pan_entity_rate_pct}%</strong>
              </p>
              <p>
                Individual/HUF FY threshold:{" "}
                <strong className="text-ink">₹{data.individual_fy_threshold_inr}</strong>
              </p>
              <p>
                G2 turnover warn / block:{" "}
                <strong className="text-ink">
                  ₹{data.fy_turnover_warn_inr} / ₹{data.fy_turnover_block_inr}
                </strong>
              </p>
              <p>
                Always-taxed entity types:{" "}
                <code>{data.always_taxed_entity_types.join(", ")}</code>
              </p>
              {data.updated_at && (
                <p className="text-xs text-ink-faint">Last updated: {data.updated_at}</p>
              )}

              {canEdit && (
                <form
                  className="space-y-4 border-t border-surface-border pt-6"
                  onSubmit={(e) => {
                    e.preventDefault();
                    setMessage(null);
                    mutation.mutate();
                  }}
                >
                  <label className="block">
                    No-PAN TDS rate (%)
                    <Input
                      className="mt-1"
                      type="number"
                      min={0}
                      max={100}
                      step="0.01"
                      value={noPanRatePct}
                      onChange={(e) => setNoPanRatePct(e.target.value)}
                      required
                    />
                  </label>
                  <label className="block">
                    PAN entity TDS rate (%)
                    <Input
                      className="mt-1"
                      type="number"
                      min={0}
                      max={100}
                      step="0.01"
                      value={panEntityRatePct}
                      onChange={(e) => setPanEntityRatePct(e.target.value)}
                      required
                    />
                  </label>
                  <label className="block">
                    Individual/HUF FY gross threshold (INR)
                    <Input
                      className="mt-1"
                      type="number"
                      min={0}
                      step="1000"
                      value={individualThreshold}
                      onChange={(e) => setIndividualThreshold(e.target.value)}
                      required
                    />
                  </label>
                  <label className="block">
                    FY platform-fee turnover warn (INR)
                    <Input
                      className="mt-1"
                      type="number"
                      min={0}
                      step="10000"
                      value={turnoverWarn}
                      onChange={(e) => setTurnoverWarn(e.target.value)}
                      required
                    />
                  </label>
                  <label className="block">
                    FY platform-fee turnover block (INR)
                    <Input
                      className="mt-1"
                      type="number"
                      min={0}
                      step="10000"
                      value={turnoverBlock}
                      onChange={(e) => setTurnoverBlock(e.target.value)}
                      required
                    />
                  </label>
                  <div>
                    <p className="mb-2">Always-taxed entity types (0.1% TDS on full puja value)</p>
                    <div className="flex flex-wrap gap-2">
                      {ENTITY_TYPE_OPTIONS.map((entityType) => (
                        <label
                          key={entityType}
                          className="inline-flex items-center gap-2 rounded-lg border border-surface-border px-3 py-2"
                        >
                          <input
                            type="checkbox"
                            checked={alwaysTaxedTypes.includes(entityType)}
                            onChange={() => toggleEntityType(entityType)}
                          />
                          {entityType}
                        </label>
                      ))}
                    </div>
                  </div>
                  <label className="block">
                    Change reason (audit trail)
                    <Input
                      className="mt-1"
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      placeholder="e.g. FY26 budget update per CA memo"
                      maxLength={300}
                    />
                  </label>
                  <Button type="submit" disabled={mutation.isPending || alwaysTaxedTypes.length === 0}>
                    {mutation.isPending ? "Saving…" : "Save TDS slabs"}
                  </Button>
                </form>
              )}

              {message && (
                <p className="rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-ink-muted">
                  {message}
                </p>
              )}
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
