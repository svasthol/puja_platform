# Admin UI — compatibility matrix

Pinned versions for the ops console. **Source of truth for this package:** `admin_ui/package.json`.

Backend Python deps remain in repo-root `pyproject.toml` / `requirements.txt`.

| Component | Version | Notes |
|---|---|---|
| Node.js | **20.18+** LTS | Do not use odd (non-LTS) majors |
| Next.js | **15.1.9** | App Router, React 19 |
| React | **19.0.0** | Bundled with Next 15 |
| TypeScript | **5.7.3** | `strict: true` |
| @tanstack/react-query | **5.62.16** | Server state + cache |
| zod | **3.24.2** | Forms + API response validation |
| tailwindcss | **3.4.17** | Utility styling |

Cross-reference: `spec/STACK_VERSIONS.md` § Next.js admin panel.

## Update policy

1. Bump versions in `package.json` only after checking Next.js + React release notes.
2. Run `npm run build` and `npm run typecheck` before committing.
3. Update this file and `spec/STACK_VERSIONS.md` if the matrix changes.

## API contract

- Base URL: `NEXT_PUBLIC_API_URL` (must include `/v1`)
- Auth: Bearer access token; refresh via `/auth/refresh`
- Errors: FastAPI `detail` string (see `spec/API_CONTRACTS.md`)
