"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Header } from "@/components/layout/header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { fetchKycVendor, updateKycVendor } from "@/lib/api/admin";
import { canEditKycVendor } from "@/lib/auth/roles";
import { useAdminMe } from "@/lib/hooks/use-admin-me";

export default function KycVendorSettingsPage() {
  const { data: me } = useAdminMe();
  const qc = useQueryClient();
  const canEdit = canEditKycVendor(me);

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "kyc-vendor"],
    queryFn: fetchKycVendor,
  });

  const [selected, setSelected] = useState("");
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (data?.active_vendor) setSelected(data.active_vendor);
  }, [data?.active_vendor]);

  const mutation = useMutation({
    mutationFn: () =>
      updateKycVendor({ vendor: selected, change_reason: reason.trim() || undefined }),
    onSuccess: async (res) => {
      const label = res.vendors.find((v) => v.name === res.active_vendor)?.label ?? res.active_vendor;
      setMessage(
        `Saved — new DigiLocker and PAN checks now use ${label}. Partners already mid-way finish on their original vendor.`,
      );
      setReason("");
      await qc.invalidateQueries({ queryKey: ["admin", "kyc-vendor"] });
    },
    onError: (err: Error) => setMessage(err.message),
  });

  const activeLabel =
    data?.vendors.find((v) => v.name === data.active_vendor)?.label ?? data?.active_vendor;

  return (
    <>
      <Header
        title="KYC vendor"
        description="Which provider runs partner Aadhaar (DigiLocker) and PAN verification for new requests."
      />
      <div className="max-w-xl p-8">
        <Card>
          <CardTitle>Active vendor</CardTitle>
          <CardDescription>
            {canEdit
              ? "Admin role required to switch. API keys stay in server env — this only chooses between configured vendors."
              : "You have read-only access (support role)."}
          </CardDescription>

          {isLoading && <p className="mt-4 text-sm text-ink-muted">Loading…</p>}
          {error && <p className="mt-4 text-sm text-red-300">{(error as Error).message}</p>}

          {data && (
            <div className="mt-6 space-y-4">
              <p className="text-3xl font-semibold text-brand-glow">{activeLabel}</p>
              <p className="text-sm text-ink-muted">
                {data.source === "console"
                  ? "Chosen in the admin console."
                  : "No console choice yet — using the server default (KYC_VENDOR)."}
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
                  <fieldset className="space-y-2">
                    <legend className="text-sm text-ink-muted">Use for new verifications</legend>
                    {data.vendors.map((v) => (
                      <label
                        key={v.name}
                        className={`flex items-center justify-between rounded-lg border border-surface-border px-3 py-2 text-sm ${
                          v.configured ? "cursor-pointer" : "cursor-not-allowed opacity-60"
                        }`}
                      >
                        <span className="flex items-center gap-2">
                          <input
                            type="radio"
                            name="kyc-vendor"
                            value={v.name}
                            checked={selected === v.name}
                            disabled={!v.configured}
                            onChange={() => setSelected(v.name)}
                          />
                          <span className="text-ink">{v.label}</span>
                          {v.name === data.env_default && (
                            <span className="text-xs text-ink-faint">(server default)</span>
                          )}
                        </span>
                        <Badge tone={v.configured ? "success" : "warning"}>
                          {v.configured ? "configured" : "not configured"}
                        </Badge>
                      </label>
                    ))}
                  </fieldset>
                  <label className="block text-sm text-ink-muted">
                    Change reason (audit trail)
                    <Input
                      className="mt-1"
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      placeholder="e.g. API Sathi outage — temporary switch to Setu"
                      maxLength={300}
                    />
                  </label>
                  <Button
                    type="submit"
                    disabled={
                      mutation.isPending || !selected || selected === data.active_vendor
                    }
                  >
                    {mutation.isPending ? "Saving…" : "Switch vendor"}
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
