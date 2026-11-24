"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  fetchServiceBoundarySettings,
  fetchServiceBoundaryStatus,
  probeServiceBoundary,
  reloadServiceBoundary,
  updateServiceBoundarySettings,
} from "@/lib/api/admin";
import { canEditDispatchPolicy } from "@/lib/auth/roles";
import { useAdminMe } from "@/lib/hooks/use-admin-me";

export default function ServiceBoundarySettingsPage() {
  const { data: me } = useAdminMe();
  const qc = useQueryClient();
  const canEdit = canEditDispatchPolicy(me);

  const { data: settings, isLoading: settingsLoading } = useQuery({
    queryKey: ["admin", "service-boundary"],
    queryFn: fetchServiceBoundarySettings,
  });

  const { data: status, refetch: refetchStatus } = useQuery({
    queryKey: ["admin", "service-boundary-status"],
    queryFn: fetchServiceBoundaryStatus,
  });

  const [enabled, setEnabled] = useState(false);
  const [reason, setReason] = useState("");
  const [probeLat, setProbeLat] = useState("17.385");
  const [probeLng, setProbeLng] = useState("78.4867");
  const [probeResult, setProbeResult] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (settings) setEnabled(settings.service_boundary_enabled);
  }, [settings]);

  const saveMut = useMutation({
    mutationFn: () =>
      updateServiceBoundarySettings({
        service_boundary_enabled: enabled,
        change_reason: reason.trim() || "service boundary toggle",
      }),
    onSuccess: async () => {
      setMessage("Saved.");
      setReason("");
      await qc.invalidateQueries({ queryKey: ["admin", "service-boundary"] });
      await refetchStatus();
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const reloadMut = useMutation({
    mutationFn: reloadServiceBoundary,
    onSuccess: async () => {
      setMessage("Polygon reloaded from disk.");
      await refetchStatus();
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const probeMut = useMutation({
    mutationFn: () => probeServiceBoundary(Number(probeLat), Number(probeLng)),
    onSuccess: (res) => {
      setProbeResult(res.serviceable ? "Inside launch area" : "Outside launch area");
    },
    onError: (e: Error) => setProbeResult(e.message),
  });

  return (
    <div>
      <Header
        title="Service boundary"
        description="Customer map pin must fall inside the launch polygon before address save or checkout. Polygon file is on the API server; reload after deploy."
      />
      <div className="mx-auto max-w-3xl space-y-6 p-6">
        {message ? (
          <p className="rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm">{message}</p>
        ) : null}

        <Card className="p-5 space-y-4">
          <CardTitle>Enable gate</CardTitle>
          <CardDescription>
            When on, customers outside Hyderabad / Secunderabad launch polygon cannot save addresses or pay.
          </CardDescription>
          <label className="flex items-start gap-3 rounded-lg border border-surface-border p-3">
            <input
              type="checkbox"
              className="mt-1"
              checked={enabled}
              disabled={!canEdit || settingsLoading}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            <span className="text-sm font-medium text-ink">service_boundary_enabled</span>
          </label>
          {canEdit ? (
            <>
              <Input
                placeholder="Change reason (required for audit)"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
              <Button
                type="button"
                disabled={saveMut.isPending || !status?.loaded}
                onClick={() => saveMut.mutate()}
              >
                Save
              </Button>
            </>
          ) : (
            <p className="text-xs text-ink-muted">Admin role required to edit.</p>
          )}
        </Card>

        <Card className="p-5 space-y-2 text-sm">
          <CardTitle>Status</CardTitle>
          {status ? (
            <ul className="list-inside list-disc text-ink-muted">
              <li>Loaded: {String(status.loaded)}</li>
              <li>ETag: {status.etag ?? "—"}</li>
              <li>Version: {status.version ?? "—"}</li>
              <li>Vertices: {status.vertex_count}</li>
              <li>Path: {status.source_path ?? "—"}</li>
            </ul>
          ) : (
            <p>Loading…</p>
          )}
          {canEdit ? (
            <Button type="button" variant="outline" disabled={reloadMut.isPending} onClick={() => reloadMut.mutate()}>
              Reload polygon from disk
            </Button>
          ) : null}
        </Card>

        <Card className="p-5 space-y-3">
          <CardTitle>Pin probe</CardTitle>
          <div className="grid grid-cols-2 gap-3">
            <Input value={probeLat} onChange={(e) => setProbeLat(e.target.value)} placeholder="latitude" />
            <Input value={probeLng} onChange={(e) => setProbeLng(e.target.value)} placeholder="longitude" />
          </div>
          <Button type="button" variant="outline" onClick={() => probeMut.mutate()}>
            Check
          </Button>
          {probeResult ? <p className="text-sm text-ink">{probeResult}</p> : null}
        </Card>
      </div>
    </div>
  );
}