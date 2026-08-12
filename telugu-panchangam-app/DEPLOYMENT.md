# Deployment Guide — Telugu Panchangam App

This guide covers deploying your own instance of the Telugu Panchangam App. The entire stack is free for reasonable traffic levels.

---

## Prerequisites

- GitHub account (free)
- Cloudflare account (free) — [cloudflare.com](https://cloudflare.com)
- Node.js 18.x
- OpenCage geocoding API key — [opencagedata.com](https://opencagedata.com) (2,500 free requests/day)

---

## 1. Fork the Repository

```bash
# Fork on GitHub, then clone your fork
git clone https://github.com/YOUR_USERNAME/telugu-panchangam-app
cd telugu-panchangam-app
npm install
```

---

## 2. Create Cloudflare Resources

### D1 Database

```bash
# Install Wrangler CLI
npm install -g wrangler

# Login to Cloudflare
wrangler login

# Create D1 database
wrangler d1 create telugu-panchangam-db
# Note the database_id from the output

# Run migrations
wrangler d1 execute telugu-panchangam-db --file=./migrations/001_initial.sql
```

### KV Namespace

```bash
# Create KV namespace
wrangler kv:namespace create "PANCHANGAM_CACHE"
# Note the id from the output

# Create preview namespace (for local development)
wrangler kv:namespace create "PANCHANGAM_CACHE" --preview
```

### Update wrangler.toml

```toml
name = "telugu-panchangam-app"
pages_build_output_dir = ".vercel/output/static"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat_v2"]

[[kv_namespaces]]
binding = "PANCHANGAM_CACHE"
id = "YOUR_KV_NAMESPACE_ID"

[[d1_databases]]
binding = "PANCHANGAM_DB"
database_name = "telugu-panchangam-db"
database_id = "YOUR_D1_DATABASE_ID"
```

> **Important:** `nodejs_compat_v2` is required — the app uses `node:async_hooks` (via Next.js internals) which needs full Node.js compat. The compat flag must also be set on the Pages project via the Cloudflare API or dashboard.

---

## 3. Environment Variables

### Local Development (.env.local)

```bash
cp .env.example .env.local
```

Edit `.env.local`:
```bash
OPENCAGE_API_KEY=your_opencage_key_here
```

### Production (Cloudflare Pages Secrets)

Set secrets via wrangler CLI (never the dashboard — secrets are encrypted):

```bash
npx wrangler pages secret put OPENCAGE_API_KEY --project-name=telugu-panchangam-app
npx wrangler pages secret put RESEND_API_KEY --project-name=telugu-panchangam-app
npx wrangler pages secret put RESEND_FROM_EMAIL --project-name=telugu-panchangam-app
```

Each command prompts you to enter the value interactively.

> **Note:** In Cloudflare Pages edge runtime, `process.env` is not available. API routes use `getEnvVar()` from `src/lib/cloudflare.ts` which reads from the Cloudflare request context.

Never commit API keys to the repository. The `.env.local` file is in `.gitignore`.

---

## 4. Connect to Cloudflare Pages

### Option A — Cloudflare Dashboard (recommended for beginners)

1. Go to [Cloudflare Pages](https://pages.cloudflare.com)
2. Click "Create a project" → "Connect to Git"
3. Select your forked repository
4. Configure build settings:
   ```
   Build command:    npx @cloudflare/next-on-pages
   Build output dir: .vercel/output/static
   Root directory:   /
   ```
5. Add environment variables (Step 3 above)
6. Click "Save and Deploy"

### Option B — Wrangler CLI

```bash
# Build for Cloudflare Pages
npm run pages:build

# Deploy
npm run pages:deploy
# Or manually:
npx wrangler pages deploy .vercel/output/static --project-name=telugu-panchangam-app
```

---

## 5. Set Up Automatic Deployment

The repository includes a GitHub Actions workflow in `.github/workflows/deploy.yml`.

Add these secrets to your GitHub repository (Settings → Secrets → Actions):

```
CLOUDFLARE_API_TOKEN   ← Create at Cloudflare Dashboard → API Tokens
CLOUDFLARE_ACCOUNT_ID  ← Found at Cloudflare Dashboard → right sidebar
```

After adding secrets, every push to `main` will automatically deploy to Cloudflare Pages.

---

## 6. Pre-compute Cache (Recommended)

Run the pre-computation script to seed the cache with common dates. This ensures the first user in each city gets fast responses:

```bash
# Pre-compute current year ± 2 years for default cities
npm run precompute

# Pre-compute a specific year range
npm run precompute -- --from=2024 --to=2030

# Pre-compute for additional cities
npm run precompute -- --cities="Sydney,Brisbane,London,New York"
```

---

## 7. Custom Domain (Optional)

In Cloudflare Pages project settings → Custom Domains:

1. Add your domain (e.g. `panchangam.yourdomain.com`)
2. Follow DNS configuration instructions
3. Cloudflare provides free SSL automatically

---

## 8. Verify Deployment

```bash
# Test the API
curl "https://your-domain.pages.dev/api/panchangam?date=2026-03-19&lat=17.385&lng=78.486&tz=Asia/Kolkata"

# Expected: Ugadi data with samvatsaram: Parabhava
```

---

## Local Development

```bash
# Start local development server
npm run dev

# Start with Cloudflare Workers simulation (D1 + KV)
npm run dev:cloudflare
# Requires wrangler.toml to be configured

# Run tests
npm test

# Type check
npm run typecheck

# Lint
npm run lint
```

---

## Cloudflare Free Tier Limits

| Resource | Free Limit | Expected Usage |
|---|---|---|
| Pages requests | Unlimited | All traffic |
| Workers requests | 100,000/day | API calls |
| KV reads | 100,000/day | Cache lookups |
| KV writes | 1,000/day | Cache population |
| D1 reads | 100,000/day | Month views, festivals |
| D1 storage | 5GB | Panchangam cache |

If you expect high traffic, upgrade to Cloudflare Workers Paid ($5/month) for 10M requests/day.

---

## Troubleshooting

### Build fails: "Cannot find module '@ishubhamx/panchangam-js'"
```bash
npm install
```

### D1 errors: "Database not found"
Verify `database_id` in `wrangler.toml` matches the ID from `wrangler d1 list`.

### KV errors: "Namespace not found"
Verify `id` in `wrangler.toml` matches the ID from `wrangler kv:namespace list`.

### Geocoding returns empty results
Verify `OPENCAGE_API_KEY` is set correctly in Cloudflare Pages environment variables.

### Telugu font not loading
The app loads Noto Sans Telugu from Google Fonts. Ensure your deployment has outbound internet access (default on Cloudflare Pages).

---

## Questions?

Open an issue on GitHub with the label `deployment-help`.
