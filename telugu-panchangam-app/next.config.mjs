/** @type {import('next').NextConfig} */
const nextConfig = {};

// Only wire up the Cloudflare dev platform in local dev — not in CI.
// In CI (Playwright e2e on GitHub Actions), wrangler isn't installed
// and next-dev would crash with `Cannot find module 'wrangler'`.
// E2E tests don't hit D1/KV directly so the bindings aren't needed.
if (process.env.NODE_ENV === "development" && !process.env.CI) {
  try {
    const { setupDevPlatform } = await import(
      "@cloudflare/next-on-pages/next-dev"
    );
    await setupDevPlatform();
  } catch (err) {
    console.warn(
      "[next.config] Skipping setupDevPlatform —",
      err instanceof Error ? err.message : err
    );
  }
}

export default nextConfig;
