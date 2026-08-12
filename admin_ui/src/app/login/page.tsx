"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { adminLogin } from "@/lib/api/admin";
import { ApiError } from "@/lib/api/client";
import { setTokens } from "@/lib/auth/tokens";

/** Dev-only RFC 6238 helper — matches backend + E2E UI (no pyotp). */
async function totpFromSecret(secret: string): Promise<string> {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  const s = secret.replace(/=+$/, "").replace(/\s/g, "").toUpperCase();
  for (const c of s) {
    const v = alphabet.indexOf(c);
    if (v >= 0) bits += v.toString(2).padStart(5, "0");
  }
  const bytes: number[] = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(parseInt(bits.slice(i, i + 8), 2));
  const key = new Uint8Array(bytes);
  const counter = Math.floor(Date.now() / 1000 / 30);
  const buf = new ArrayBuffer(8);
  const view = new DataView(buf);
  view.setUint32(0, 0);
  view.setUint32(4, counter);
  const cryptoKey = await crypto.subtle.importKey("raw", key, { name: "HMAC", hash: "SHA-1" }, false, [
    "sign",
  ]);
  const hs = await crypto.subtle.sign("HMAC", cryptoKey, buf);
  const h = new Uint8Array(hs);
  const offset = h[h.length - 1] & 0x0f;
  const binary =
    ((h[offset] & 0x7f) << 24) |
    ((h[offset + 1] & 0xff) << 16) |
    ((h[offset + 2] & 0xff) << 8) |
    (h[offset + 3] & 0xff);
  return String(binary % 1_000_000).padStart(6, "0");
}

export default function LoginPage() {
  const router = useRouter();
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [devSecret, setDevSecret] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const tokens = await adminLogin({ phone: phone.trim(), code: code.trim() });
      setTokens(tokens.access_token, tokens.refresh_token);
      router.replace("/console");
    } catch (err) {
      if (err instanceof ApiError) {
        let msg = err.message;
        if (err.status === 503) {
          msg =
            "TOTP_ENC_KEYS mismatch on the API server. Re-run bootstrap_admin.py --reset, then re-add your authenticator secret.";
        }
        setError(msg);
      } else {
        setError("Login failed. Check phone and TOTP code.");
      }
    } finally {
      setLoading(false);
    }
  }

  async function fillDevCode() {
    try {
      const c = await totpFromSecret(devSecret.trim());
      setCode(c);
    } catch {
      setError("Invalid bootstrap secret for dev code generation.");
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <span className="text-4xl">🪔</span>
          <h1 className="mt-3 text-2xl font-semibold text-ink">Mana Guruji Ops</h1>
          <p className="mt-1 text-sm text-ink-muted">Sign in with your authenticator app (TOTP)</p>
        </div>

        <Card>
          <CardTitle>Admin login</CardTitle>
          <CardDescription>
            SMS OTP is not used for staff. Use the 6-digit code from Google Authenticator / Authy.
          </CardDescription>

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            <label className="block text-sm text-ink-muted">
              Phone (E.164)
              <Input
                className="mt-1"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+919111111100"
                autoComplete="tel"
                required
              />
            </label>
            <label className="block text-sm text-ink-muted">
              TOTP code
              <Input
                className="mt-1 font-mono tracking-widest"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="123456"
                inputMode="numeric"
                maxLength={8}
                required
              />
            </label>

            <details className="rounded-lg border border-surface-border bg-surface/50 p-3 text-sm">
              <summary className="cursor-pointer text-ink-muted">Dev: fill code from bootstrap secret</summary>
              <div className="mt-3 space-y-2">
                <Input
                  type="password"
                  value={devSecret}
                  onChange={(e) => setDevSecret(e.target.value)}
                  placeholder="Paste secret from bootstrap_admin.py"
                  autoComplete="off"
                />
                <Button type="button" variant="secondary" className="w-full" onClick={fillDevCode}>
                  Fill current code
                </Button>
              </div>
            </details>

            {error && (
              <p className="rounded-lg border border-red-800/50 bg-red-950/30 px-3 py-2 text-sm text-red-200">
                {error}
              </p>
            )}

            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </Card>

        <p className="mt-6 text-center text-xs text-ink-faint">
          First admin? Run <code className="text-ink-muted">scripts/bootstrap_admin.py</code> on the API server.
        </p>
      </div>
    </div>
  );
}
