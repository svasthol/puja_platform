import { getRequestContext } from "@cloudflare/next-on-pages";

/**
 * Get the D1 database binding from Cloudflare context.
 * Returns null when not running in Cloudflare (local dev without wrangler).
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function getDB(): any | null {
  try {
    const { env } = getRequestContext();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return (env as any).PANCHANGAM_DB ?? null;
  } catch {
    return null;
  }
}

/**
 * Get the KV namespace binding from Cloudflare context.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function getKV(): any | null {
  try {
    const { env } = getRequestContext();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return (env as any).PANCHANGAM_CACHE ?? null;
  } catch {
    return null;
  }
}

/**
 * Get an environment variable from Cloudflare context,
 * falling back to process.env for local dev.
 */
export function getEnvVar(key: string): string | undefined {
  try {
    const { env } = getRequestContext();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return (env as any)[key] ?? undefined;
  } catch {
    return process.env[key];
  }
}
