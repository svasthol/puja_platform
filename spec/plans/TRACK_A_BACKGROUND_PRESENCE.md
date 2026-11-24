# Track A — partner background presence (Phase 1)

**Branch:** `feature/partner-background-presence`  
**Depends on:** Track B `expand_for_pujari` on backend (`dev` after urgency PR)

## Phase 1 (this branch)

| Item | Status |
|------|--------|
| Resume → immediate `sendHeartbeat(foreground)` | done (`partner_shell.dart`) |
| Paused/inactive → one `background` heartbeat (10m Redis TTL server-side) | done |
| Failed heartbeat → `online: false` locally | done (`duty_controller.dart`) |
| `Heartbeat.presence_mode` API + OpenAPI | done |
| `PUJARI_PRESENCE_BACKGROUND_TTL_SECONDS` (default 600) | done |
| Onboarding sign-out calls `goOffline()` when on duty | done |

## Phase 2 (not started)

- Android FGS behind remote flag
- iOS honest UX copy
- Optional `UIBackgroundModes` fetch (defer)

## Ship note

Backend + partner APK must deploy together for `presence_mode` to extend TTL. Old apps ignore the field → 90s TTL only.