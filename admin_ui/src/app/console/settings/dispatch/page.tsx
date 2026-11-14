"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { fetchDispatchPolicy, updateDispatchPolicy } from "@/lib/api/admin";
import { canEditDispatchPolicy } from "@/lib/auth/roles";
import { useAdminMe } from "@/lib/hooks/use-admin-me";

function BoolRow({
  label,
  help,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  help: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled: boolean;
}) {
  return (
    <label className="flex items-start gap-3 rounded-lg border border-surface-border p-3">
      <input
        type="checkbox"
        className="mt-1"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>
        <span className="block text-sm font-medium text-ink">{label}</span>
        <span className="block text-xs text-ink-muted">{help}</span>
      </span>
    </label>
  );
}

function NumRow({
  label,
  value,
  onChange,
  disabled,
  min,
  max,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  disabled: boolean;
  min: number;
  max: number;
}) {
  return (
    <label className="block text-sm text-ink-muted">
      {label}
      <Input
        className="mt-1"
        type="number"
        min={min}
        max={max}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

export default function DispatchPolicySettingsPage() {
  const { data: me } = useAdminMe();
  const qc = useQueryClient();
  const canEdit = canEditDispatchPolicy(me);

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "dispatch-policy"],
    queryFn: fetchDispatchPolicy,
  });

  const [form, setForm] = useState<Record<string, string>>({});
  const [immediate, setImmediate] = useState(true);
  const [night, setNight] = useState(false);
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!data) return;
    setImmediate(data.immediate_dispatch_on_payment);
    setNight(data.night_bookings_enabled);
    setForm({
      instant_lead_hours: String(data.instant_lead_hours),
      instant_dispatch_minutes: String(data.instant_dispatch_minutes),
      advance_dispatch_start_hours: String(data.advance_dispatch_start_hours),
      advance_dispatch_fail_hours: String(data.advance_dispatch_fail_hours),
      reoffer_cooldown_minutes: String(data.reoffer_cooldown_minutes),
      dispatch_buffer_minutes: String(data.dispatch_buffer_minutes),
      instant_offer_ttl_seconds: String(data.instant_offer_ttl_seconds),
      advance_offer_ttl_hours: String(data.advance_offer_ttl_hours),
      max_live_advance_offers_per_pujari: String(data.max_live_advance_offers_per_pujari),
      rm_escalation_hours_no_accept: String(data.rm_escalation_hours_no_accept),
      rm_escalation_t24_hours: String(data.rm_escalation_t24_hours),
      reconfirm_quiet_hours_start: data.reconfirm_quiet_hours_start,
      reconfirm_quiet_hours_end: data.reconfirm_quiet_hours_end,
    });
  }, [data]);

  const mutation = useMutation({
    mutationFn: () =>
      updateDispatchPolicy({
        instant_lead_hours: Number(form.instant_lead_hours),
        instant_dispatch_minutes: Number(form.instant_dispatch_minutes),
        advance_dispatch_start_hours: Number(form.advance_dispatch_start_hours),
        advance_dispatch_fail_hours: Number(form.advance_dispatch_fail_hours),
        reoffer_cooldown_minutes: Number(form.reoffer_cooldown_minutes),
        dispatch_buffer_minutes: Number(form.dispatch_buffer_minutes),
        immediate_dispatch_on_payment: immediate,
        instant_offer_ttl_seconds: Number(form.instant_offer_ttl_seconds),
        advance_offer_ttl_hours: Number(form.advance_offer_ttl_hours),
        max_live_advance_offers_per_pujari: Number(form.max_live_advance_offers_per_pujari),
        rm_escalation_hours_no_accept: Number(form.rm_escalation_hours_no_accept),
        rm_escalation_t24_hours: Number(form.rm_escalation_t24_hours),
        night_bookings_enabled: night,
        reconfirm_quiet_hours_start: form.reconfirm_quiet_hours_start,
        reconfirm_quiet_hours_end: form.reconfirm_quiet_hours_end,
        change_reason: reason.trim() || undefined,
      }),
    onSuccess: async () => {
      setMessage(
        "Saved — new bookings use this policy. Existing dispatch_starts_at on active bookings is unchanged.",
      );
      await qc.invalidateQueries({ queryKey: ["admin", "dispatch-policy"] });
    },
    onError: (err: Error) => setMessage(err.message),
  });

  const setNum = (key: string, val: string) => setForm((f) => ({ ...f, [key]: val }));

  return (
    <>
      <Header
        title="Dispatch policy"
        description="Launch matching windows, offer TTLs, and booking gates — stored in platform_settings."
      />
      <div className="max-w-2xl p-8">
        <Card>
          <CardTitle>Current policy</CardTitle>
          <CardDescription>
            Workers read these keys on every sweep and dispatch round. Keep{" "}
            <strong>Immediate dispatch on payment</strong> enabled for production launch.
          </CardDescription>

          {isLoading && <p className="mt-4 text-sm text-ink-muted">Loading…</p>}
          {error && (
            <p className="mt-4 text-sm text-red-300">{(error as Error).message}</p>
          )}

          {data && (
            <form
              className="mt-6 space-y-6"
              onSubmit={(e) => {
                e.preventDefault();
                setMessage(null);
                mutation.mutate();
              }}
            >
              <section className="space-y-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-ink-faint">
                  Launch dispatch (v2)
                </p>
                <BoolRow
                  label="Immediate dispatch on payment"
                  help="When on, advance bookings broadcast from payment time. When off, deferred start = slot − advance start hours (rollback only)."
                  checked={immediate}
                  onChange={setImmediate}
                  disabled={!canEdit}
                />
                <BoolRow
                  label="Night bookings (00:00–05:59 IST)"
                  help="When off, POST /bookings rejects night slots at launch."
                  checked={night}
                  onChange={setNight}
                  disabled={!canEdit}
                />
              </section>

              <section className="grid gap-4 sm:grid-cols-2">
                <NumRow
                  label="Instant lead (hours)"
                  value={form.instant_lead_hours ?? ""}
                  onChange={(v) => setNum("instant_lead_hours", v)}
                  disabled={!canEdit}
                  min={1}
                  max={48}
                />
                <NumRow
                  label="Instant dispatch window (minutes)"
                  value={form.instant_dispatch_minutes ?? ""}
                  onChange={(v) => setNum("instant_dispatch_minutes", v)}
                  disabled={!canEdit}
                  min={5}
                  max={180}
                />
                <NumRow
                  label="Advance dispatch start (hours before slot, rollback)"
                  value={form.advance_dispatch_start_hours ?? ""}
                  onChange={(v) => setNum("advance_dispatch_start_hours", v)}
                  disabled={!canEdit}
                  min={1}
                  max={48}
                />
                <NumRow
                  label="Advance fail (hours before slot)"
                  value={form.advance_dispatch_fail_hours ?? ""}
                  onChange={(v) => setNum("advance_dispatch_fail_hours", v)}
                  disabled={!canEdit}
                  min={1}
                  max={24}
                />
                <NumRow
                  label="Dispatch buffer after prior puja (minutes)"
                  value={form.dispatch_buffer_minutes ?? ""}
                  onChange={(v) => setNum("dispatch_buffer_minutes", v)}
                  disabled={!canEdit}
                  min={0}
                  max={180}
                />
                <NumRow
                  label="Re-offer cooldown after expired (minutes)"
                  value={form.reoffer_cooldown_minutes ?? ""}
                  onChange={(v) => setNum("reoffer_cooldown_minutes", v)}
                  disabled={!canEdit}
                  min={0}
                  max={240}
                />
              </section>

              <section className="grid gap-4 sm:grid-cols-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-ink-faint sm:col-span-2">
                  Offer TTL &amp; RM
                </p>
                <NumRow
                  label="Instant offer TTL (seconds)"
                  value={form.instant_offer_ttl_seconds ?? ""}
                  onChange={(v) => setNum("instant_offer_ttl_seconds", v)}
                  disabled={!canEdit}
                  min={30}
                  max={900}
                />
                <NumRow
                  label="Advance offer TTL (hours)"
                  value={form.advance_offer_ttl_hours ?? ""}
                  onChange={(v) => setNum("advance_offer_ttl_hours", v)}
                  disabled={!canEdit}
                  min={1}
                  max={72}
                />
                <NumRow
                  label="Max live advance offers per pujari"
                  value={form.max_live_advance_offers_per_pujari ?? ""}
                  onChange={(v) => setNum("max_live_advance_offers_per_pujari", v)}
                  disabled={!canEdit}
                  min={1}
                  max={50}
                />
                <NumRow
                  label="RM escalation if no accept (hours)"
                  value={form.rm_escalation_hours_no_accept ?? ""}
                  onChange={(v) => setNum("rm_escalation_hours_no_accept", v)}
                  disabled={!canEdit}
                  min={1}
                  max={72}
                />
                <NumRow
                  label="RM T−24 escalation (hours)"
                  value={form.rm_escalation_t24_hours ?? ""}
                  onChange={(v) => setNum("rm_escalation_t24_hours", v)}
                  disabled={!canEdit}
                  min={1}
                  max={72}
                />
              </section>

              <section className="grid gap-4 sm:grid-cols-2">
                <label className="block text-sm text-ink-muted">
                  Reconfirm quiet start (HH:MM)
                  <Input
                    className="mt-1 font-mono"
                    value={form.reconfirm_quiet_hours_start ?? ""}
                    disabled={!canEdit}
                    onChange={(e) => setNum("reconfirm_quiet_hours_start", e.target.value)}
                  />
                </label>
                <label className="block text-sm text-ink-muted">
                  Reconfirm quiet end (HH:MM)
                  <Input
                    className="mt-1 font-mono"
                    value={form.reconfirm_quiet_hours_end ?? ""}
                    disabled={!canEdit}
                    onChange={(e) => setNum("reconfirm_quiet_hours_end", e.target.value)}
                  />
                </label>
              </section>

              {canEdit && (
                <label className="block text-sm text-ink-muted">
                  Change reason (audit)
                  <Input
                    className="mt-1"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder="e.g. production launch posture"
                    maxLength={300}
                  />
                </label>
              )}

              {message && (
                <p
                  className={`text-sm ${message.includes("Saved") ? "text-green-300" : "text-red-300"}`}
                >
                  {message}
                </p>
              )}

              {data.updated_at && (
                <p className="text-xs text-ink-faint">Last change: {data.updated_at}</p>
              )}

              {canEdit && (
                <Button type="submit" disabled={mutation.isPending}>
                  {mutation.isPending ? "Saving…" : "Save dispatch policy"}
                </Button>
              )}
              {!canEdit && (
                <p className="text-sm text-ink-muted">Support role: read-only.</p>
              )}
            </form>
          )}
        </Card>
      </div>
    </>
  );
}