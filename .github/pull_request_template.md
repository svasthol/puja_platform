## Summary

<!-- What changed and why (1–3 sentences) -->

## Type

- [ ] Feature
- [ ] Bug fix
- [ ] Ops / deploy / CI
- [ ] Docs only

## Staging impact

- [ ] **CI** (`ci.yml`) — required for merge
- [ ] **Deploy staging** will run on merge to `dev` (or I ran **Deploy staging** manually with `git_ref=…`)
- [ ] Needs **`/etc/mana-guruji/api.env`** change on VM (document keys in `deploy/env/staging.api.env.example` + `ENV_STAGING_REFERENCE.md`)
- [ ] Needs **STAGING_CONFIG_ROLLOUT** verify step: <!-- e.g. Phase 2 bootstrap, storage smoke -->

## Test plan

<!-- Local and/or staging URLs/commands -->

- [ ] `curl …/health/live` (staging if deployed)
- [ ] <!-- pytest / script name -->

## Promotion (`dev` → `main` only)

Fill when this PR targets **`main`** (see [`spec/plans/DEVELOPER_RELEASE_FLOW.md`](../spec/plans/DEVELOPER_RELEASE_FLOW.md)):

- [ ] Staging proved the same SHA on **`dev`**
- [ ] STG-CFG / PM rows updated: <!-- IDs -->
- [ ] Incidents doc updated if we hit a new STG issue

## PM / tracker

<!-- Optional: STG-CFG-00x, CI-00x -->
