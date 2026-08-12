"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Header } from "@/components/layout/header";
import { PageContent } from "@/components/layout/page-content";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createServiceArea, fetchServiceAreas, updateServiceArea } from "@/lib/api/areas";
import { canEditServiceAreas } from "@/lib/auth/roles";
import { useAdminMe } from "@/lib/hooks/use-admin-me";

export default function ServiceAreasPage() {
  const { data: me } = useAdminMe();
  const qc = useQueryClient();
  const canEdit = canEditServiceAreas(me);

  const [city, setCity] = useState("Hyderabad");
  const [zoneName, setZoneName] = useState("");
  const [pincode, setPincode] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "service-areas"],
    queryFn: () => fetchServiceAreas(),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createServiceArea({
        city: city.trim(),
        zone_name: zoneName.trim(),
        pincode: pincode.trim() || undefined,
      }),
    onSuccess: async () => {
      setZoneName("");
      setPincode("");
      setMessage("Service area created — customers can pick it in the address dropdown.");
      await qc.invalidateQueries({ queryKey: ["admin", "service-areas"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const toggleMutation = useMutation({
    mutationFn: (area: { id: number; is_active: boolean; active_booking_count: number }) =>
      updateServiceArea(area.id, {
        is_active: !area.is_active,
        force_deactivate: area.active_booking_count > 0,
        change_reason: "admin-ui",
      }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["admin", "service-areas"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  return (
    <>
      <Header
        title="Service areas"
        description="Customer address dropdown zones (Kukatpally, LB Nagar, …). Display label at launch — dispatch stays citywide."
      />
      <PageContent>
        {!canEdit && (
          <Alert tone="warning">Support role: read-only. Admin required to create or deactivate areas.</Alert>
        )}

        {canEdit && (
          <Card className="mb-8 max-w-xl">
            <CardTitle>Add area</CardTitle>
            <CardDescription>Zones appear in the customer app address picker when active.</CardDescription>
            <form
              className="mt-4 space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                setMessage(null);
                createMutation.mutate();
              }}
            >
              <div>
                <Label htmlFor="city">City</Label>
                <Input id="city" value={city} onChange={(e) => setCity(e.target.value)} required />
              </div>
              <div>
                <Label htmlFor="zone">Zone name</Label>
                <Input
                  id="zone"
                  value={zoneName}
                  onChange={(e) => setZoneName(e.target.value)}
                  placeholder="e.g. Kukatpally"
                  required
                />
              </div>
              <div>
                <Label htmlFor="pincode">Pincode (optional)</Label>
                <Input id="pincode" value={pincode} onChange={(e) => setPincode(e.target.value)} />
              </div>
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? "Creating…" : "Create area"}
              </Button>
            </form>
          </Card>
        )}

        {message && (
          <p className="mb-4 rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-ink-muted">
            {message}
          </p>
        )}

        {isLoading && <p className="text-sm text-ink-muted">Loading areas…</p>}
        {error && <p className="text-sm text-red-300">{(error as Error).message}</p>}

        {data && (
          <div className="overflow-x-auto rounded-xl border border-surface-border">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-surface-border bg-surface-raised/80 text-ink-faint">
                <tr>
                  <th className="px-4 py-3 font-medium">Zone</th>
                  <th className="px-4 py-3 font-medium">City</th>
                  <th className="px-4 py-3 font-medium">Pujaris</th>
                  <th className="px-4 py-3 font-medium">Active bookings</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  {canEdit && <th className="px-4 py-3 font-medium" />}
                </tr>
              </thead>
              <tbody>
                {data.areas.map((area) => (
                  <tr key={area.id} className="border-b border-surface-border/60">
                    <td className="px-4 py-3 font-medium text-ink">{area.zone_name}</td>
                    <td className="px-4 py-3 text-ink-muted">{area.city}</td>
                    <td className="px-4 py-3 text-ink-muted">{area.pujari_count}</td>
                    <td className="px-4 py-3 text-ink-muted">{area.active_booking_count}</td>
                    <td className="px-4 py-3">
                      <Badge tone={area.is_active ? "success" : "warning"}>
                        {area.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </td>
                    {canEdit && (
                      <td className="px-4 py-3 text-right">
                        <Button
                          type="button"
                          variant="ghost"
                          disabled={toggleMutation.isPending}
                          onClick={() => {
                            setMessage(null);
                            toggleMutation.mutate(area);
                          }}
                        >
                          {area.is_active ? "Deactivate" : "Activate"}
                        </Button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            {data.areas.length === 0 && (
              <p className="px-4 py-8 text-center text-sm text-ink-muted">
                No service areas yet. Create zones for the customer dropdown.
              </p>
            )}
          </div>
        )}
      </PageContent>
    </>
  );
}
