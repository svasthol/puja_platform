"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { KycReadOnlyBanner } from "@/components/partners/kyc-read-only-banner";
import { Header } from "@/components/layout/header";
import { PageContent } from "@/components/layout/page-content";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { approveKycDocument, fetchPendingKyc, rejectKycDocument } from "@/lib/api/kyc";
import { canApproveKyc } from "@/lib/auth/roles";
import { useAdminMe } from "@/lib/hooks/use-admin-me";
import type { KycPendingItem } from "@/lib/schemas/kyc";

const STATUS_TONE = {
  verified: "success",
  pending: "warning",
  rejected: "warning",
} as const;

function formatUploadedAt(iso: string) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function KycRow({
  item,
  canApprove,
  onDone,
}: {
  item: KycPendingItem;
  canApprove: boolean;
  onDone: (msg: string) => void;
}) {
  const qc = useQueryClient();
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reason, setReason] = useState("");

  const approveMutation = useMutation({
    mutationFn: () => approveKycDocument(item.id, { change_reason: "admin-ui approve" }),
    onSuccess: async (res) => {
      const msg = res.all_required_verified
        ? `${item.pujari_name} — all required docs verified. Pujari promoted.`
        : `Approved ${item.doc_type_label}.`;
      onDone(msg);
      await qc.invalidateQueries({ queryKey: ["admin", "kyc"] });
      await qc.invalidateQueries({ queryKey: ["admin", "pujaris"] });
    },
    onError: (e: Error) => onDone(e.message),
  });

  const rejectMutation = useMutation({
    mutationFn: () => rejectKycDocument(item.id, { change_reason: reason.trim() }),
    onSuccess: async () => {
      onDone(`Rejected ${item.doc_type_label} for ${item.pujari_name}.`);
      setRejectOpen(false);
      setReason("");
      await qc.invalidateQueries({ queryKey: ["admin", "kyc"] });
      await qc.invalidateQueries({ queryKey: ["admin", "pujaris"] });
    },
    onError: (e: Error) => onDone(e.message),
  });

  const busy = approveMutation.isPending || rejectMutation.isPending;

  return (
    <li className="px-5 py-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium text-ink">{item.pujari_name}</p>
            <Badge tone={STATUS_TONE[item.pujari_verification_status]}>
              {item.pujari_verification_status}
            </Badge>
          </div>
          <p className="text-sm text-ink-muted">{item.pujari_phone}</p>
          <p className="text-sm text-ink">
            <span className="font-medium">{item.doc_type_label}</span>
            <span className="text-ink-faint"> · v{item.version} · {formatUploadedAt(item.uploaded_at)}</span>
          </p>
          <div className="flex flex-wrap gap-3 pt-1 text-sm">
            <Link
              href={`/console/partners/${item.pujari_id}`}
              className="text-brand-glow hover:underline"
            >
              Partner profile →
            </Link>
            {item.view_url ? (
              <a
                href={item.view_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-brand-glow hover:underline"
              >
                View document
                {item.view_url_expires_in ? ` (${item.view_url_expires_in}s)` : ""}
              </a>
            ) : (
              <span className="text-ink-faint">Document preview unavailable (S3 not configured)</span>
            )}
          </div>
        </div>

        {canApprove && (
          <div className="flex shrink-0 flex-col gap-2 sm:flex-row lg:flex-col xl:flex-row">
            <Button
              type="button"
              disabled={busy}
              onClick={() => approveMutation.mutate()}
            >
              Approve
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={busy}
              onClick={() => setRejectOpen((v) => !v)}
            >
              Reject
            </Button>
          </div>
        )}
      </div>

      {rejectOpen && canApprove && (
        <div className="mt-4 rounded-lg border border-surface-border bg-surface/40 p-4">
          <Label htmlFor={`reject-${item.id}`}>Rejection reason (required)</Label>
          <Textarea
            id={`reject-${item.id}`}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
            className="mt-1.5"
            placeholder="e.g. ID photo blurry — please re-upload"
          />
          <div className="mt-3 flex gap-2">
            <Button
              type="button"
              variant="secondary"
              disabled={busy || !reason.trim()}
              onClick={() => rejectMutation.mutate()}
            >
              Confirm reject
            </Button>
            <Button type="button" variant="ghost" onClick={() => setRejectOpen(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}

export default function KycQueuePage() {
  const { data: me } = useAdminMe();
  const canApprove = canApproveKyc(me);
  const [message, setMessage] = useState<string | null>(null);
  const [cursor, setCursor] = useState<string | undefined>();

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["admin", "kyc", "pending", cursor],
    queryFn: () => fetchPendingKyc({ limit: 20, cursor }),
  });

  return (
    <>
      <Header
        title="KYC review"
        description="Pending partner documents — approve each doc; pujari verified only when identity, address, and photo are all approved."
      />
      <PageContent>
        <Link href="/console/partners" className="text-sm text-brand-glow hover:underline">
          ← Back to partners
        </Link>

        <KycReadOnlyBanner me={me} />

        {message && (
          <Alert className="mt-4" tone="success">
            {message}
          </Alert>
        )}

        <Card className="mt-4 overflow-hidden !p-0">
          <div className="border-b border-surface-border px-5 py-4">
            <CardTitle className="text-base">Pending queue</CardTitle>
            <CardDescription className="!mt-0.5">
              {data?.items.length ?? 0} awaiting review
              {data?.required_doc_types.length
                ? ` · required: ${data.required_doc_types.join(", ")}`
                : ""}
            </CardDescription>
          </div>

          {isLoading && <p className="p-5 text-sm text-ink-muted">Loading…</p>}

          <ul className="divide-y divide-surface-border">
            {(data?.items ?? []).length === 0 && !isLoading && (
              <li className="px-5 py-10 text-center text-sm text-ink-muted">
                No pending documents. Queue fills when partners upload via B-KYC.
              </li>
            )}
            {(data?.items ?? []).map((item) => (
              <KycRow
                key={item.id}
                item={item}
                canApprove={canApprove}
                onDone={setMessage}
              />
            ))}
          </ul>

          {data?.next_cursor && (
            <div className="border-t border-surface-border px-5 py-4">
              <Button
                type="button"
                variant="secondary"
                disabled={isFetching}
                onClick={() => setCursor(data.next_cursor ?? undefined)}
              >
                Load more
              </Button>
            </div>
          )}
        </Card>
      </PageContent>
    </>
  );
}
