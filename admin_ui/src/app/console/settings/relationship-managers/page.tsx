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
import {
  createRelationshipManager,
  fetchDefaultRelationshipManager,
  fetchRelationshipManagers,
  setDefaultRelationshipManager,
  updateRelationshipManager,
} from "@/lib/api/relationship-managers";
import { canEditRelationshipManagers } from "@/lib/auth/roles";
import { useAdminMe } from "@/lib/hooks/use-admin-me";

export default function RelationshipManagersPage() {
  const { data: me } = useAdminMe();
  const qc = useQueryClient();
  const canEdit = canEditRelationshipManagers(me);

  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [city, setCity] = useState("Hyderabad");
  const [setAsDefault, setSetAsDefault] = useState(true);
  const [message, setMessage] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["admin", "relationship-managers"],
    queryFn: fetchRelationshipManagers,
  });

  const { data: defaultRm } = useQuery({
    queryKey: ["admin", "relationship-managers", "default"],
    queryFn: fetchDefaultRelationshipManager,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createRelationshipManager({
        name: name.trim(),
        phone: phone.trim(),
        city: city.trim() || undefined,
        set_as_default: setAsDefault,
      }),
    onSuccess: async () => {
      setName("");
      setPhone("");
      setMessage("RM created — assigned to new confirmed bookings.");
      await qc.invalidateQueries({ queryKey: ["admin", "relationship-managers"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const toggleMutation = useMutation({
    mutationFn: (rm: { id: string; is_active: boolean }) =>
      updateRelationshipManager(rm.id, {
        is_active: !rm.is_active,
        change_reason: "admin-ui",
      }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["admin", "relationship-managers"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const defaultMutation = useMutation({
    mutationFn: (rmId: string) =>
      setDefaultRelationshipManager({
        relationship_manager_id: rmId,
        change_reason: "admin-ui",
      }),
    onSuccess: async () => {
      setMessage("Default RM updated.");
      await qc.invalidateQueries({ queryKey: ["admin", "relationship-managers"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  return (
    <>
      <Header
        title="Relationship managers"
        description="Platform mediators shown to customer and pujari after booking confirm (§21.4). No direct phone exchange."
      />
      <PageContent>
        {!canEdit && (
          <Alert tone="warning">Support role: read-only. Admin required to manage RMs.</Alert>
        )}

        {defaultRm?.relationship_manager_id && (
          <Card className="mb-6 max-w-xl">
            <CardTitle>Default RM</CardTitle>
            <CardDescription>Used when a booking is confirmed unless a city-specific RM exists.</CardDescription>
            <p className="mt-3 text-sm text-ink">
              {defaultRm.name} · <span className="font-mono">{defaultRm.phone}</span>
            </p>
          </Card>
        )}

        {canEdit && (
          <Card className="mb-8 max-w-xl">
            <CardTitle>Add relationship manager</CardTitle>
            <form
              className="mt-4 space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                setMessage(null);
                createMutation.mutate();
              }}
            >
              <div>
                <Label htmlFor="rm-name">Name</Label>
                <Input id="rm-name" value={name} onChange={(e) => setName(e.target.value)} required />
              </div>
              <div>
                <Label htmlFor="rm-phone">Phone</Label>
                <Input
                  id="rm-phone"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="+919876543210"
                  required
                />
              </div>
              <div>
                <Label htmlFor="rm-city">City (optional — city-specific fallback)</Label>
                <Input id="rm-city" value={city} onChange={(e) => setCity(e.target.value)} />
              </div>
              <label className="flex items-center gap-2 text-sm text-ink-muted">
                <input
                  type="checkbox"
                  checked={setAsDefault}
                  onChange={(e) => setSetAsDefault(e.target.checked)}
                />
                Set as platform default
              </label>
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? "Creating…" : "Create RM"}
              </Button>
            </form>
          </Card>
        )}

        {message && (
          <p className="mb-4 rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-ink-muted">
            {message}
          </p>
        )}

        {isLoading && <p className="text-sm text-ink-muted">Loading…</p>}

        {data && (
          <div className="overflow-x-auto rounded-xl border border-surface-border">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-surface-border bg-surface-raised/80 text-ink-faint">
                <tr>
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Phone</th>
                  <th className="px-4 py-3 font-medium">City</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  {canEdit && <th className="px-4 py-3 font-medium" />}
                </tr>
              </thead>
              <tbody>
                {data.items.map((rm) => (
                  <tr key={rm.id} className="border-b border-surface-border/60">
                    <td className="px-4 py-3 font-medium text-ink">
                      {rm.name}
                      {rm.is_default && (
                        <Badge tone="success" className="ml-2">
                          Default
                        </Badge>
                      )}
                    </td>
                    <td className="px-4 py-3 font-mono text-ink-muted">{rm.phone}</td>
                    <td className="px-4 py-3 text-ink-muted">{rm.city ?? "—"}</td>
                    <td className="px-4 py-3">
                      <Badge tone={rm.is_active ? "success" : "warning"}>
                        {rm.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </td>
                    {canEdit && (
                      <td className="space-x-2 px-4 py-3 text-right">
                        {!rm.is_default && rm.is_active && (
                          <Button
                            type="button"
                            variant="ghost"
                            onClick={() => defaultMutation.mutate(rm.id)}
                          >
                            Make default
                          </Button>
                        )}
                        <Button
                          type="button"
                          variant="ghost"
                          onClick={() => toggleMutation.mutate(rm)}
                        >
                          {rm.is_active ? "Deactivate" : "Activate"}
                        </Button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            {data.items.length === 0 && (
              <p className="px-4 py-8 text-center text-sm text-ink-muted">
                No RMs yet. Create at least one before launch — confirmed bookings need a mediator.
              </p>
            )}
          </div>
        )}
      </PageContent>
    </>
  );
}
