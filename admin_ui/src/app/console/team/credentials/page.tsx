"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { provisionCredential } from "@/lib/api/admin";
import type { CredentialProvision } from "@/lib/schemas/admin";
import { canProvisionCredentials } from "@/lib/auth/roles";
import { useAdminMe } from "@/lib/hooks/use-admin-me";

export default function CredentialsPage() {
  const { data: me } = useAdminMe();
  const canEdit = canProvisionCredentials(me);
  const [userId, setUserId] = useState("");
  const [result, setResult] = useState<CredentialProvision | null>(null);

  const mutation = useMutation({
    mutationFn: () => provisionCredential(userId.trim()),
    onSuccess: (data) => setResult(data),
  });

  return (
    <>
      <Header
        title="TOTP credentials"
        description="Provision or reset an admin/support staff member's authenticator. Secret shown once."
      />
      <div className="max-w-2xl space-y-6 p-8">
        {!canEdit && (
          <p className="rounded-lg border border-amber-800/40 bg-amber-950/30 px-4 py-3 text-sm text-amber-100">
            Admin role required to provision credentials.
          </p>
        )}

        <Card>
          <CardTitle>Provision / reset</CardTitle>
          <CardDescription>
            Target user must already have an admin or support role. They activate on first successful login.
          </CardDescription>
          <div className="mt-4 space-y-4">
            <label className="block text-sm text-ink-muted">
              User ID (UUID)
              <Input
                className="mt-1 font-mono text-xs"
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                placeholder="from Team → Roles lookup"
              />
            </label>
            {canEdit && (
              <Button
                onClick={() => {
                  setResult(null);
                  mutation.mutate();
                }}
                disabled={!userId.trim() || mutation.isPending}
              >
                {mutation.isPending ? "Provisioning…" : "Generate credential"}
              </Button>
            )}
            {mutation.isError && (
              <p className="text-sm text-red-300">{(mutation.error as Error).message}</p>
            )}
          </div>
        </Card>

        {result && (
          <Card className="border-brand/40">
            <CardTitle className="text-brand-glow">Save now — shown once</CardTitle>
            <CardDescription>{result.note}</CardDescription>
            <pre className="mt-4 overflow-x-auto rounded-lg bg-surface p-4 font-mono text-xs text-ink">
              {`Secret: ${result.secret}\n\nURI:\n${result.provisioning_uri}`}
            </pre>
            <p className="mt-3 text-xs text-ink-faint">
              Add to Google Authenticator / Authy, or paste the secret on the login page dev helper.
            </p>
          </Card>
        )}
      </div>
    </>
  );
}
