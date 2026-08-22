# Mobile apps — Firebase & Flutter identifiers

**Purpose:** Canonical record of Firebase project + Android package names so Flutter
setup matches what was registered in the console. **Read this before `flutter create`.**

**Related:** [`ARCHITECTURE.md`](./ARCHITECTURE.md) · [`MOBILE_FLUTTER.md`](./MOBILE_FLUTTER.md) · [`STACK_VERSIONS.md`](./STACK_VERSIONS.md) (Flutter deps) ·
[`openapi.json`](./openapi.json) · [`API_CONTRACTS.md`](./API_CONTRACTS.md) v3.4 ·
[`plans/STATUS.md`](./plans/STATUS.md) (`P-FCM-E2E`, `C-FLUTTER-*`)

**Secrets:** Never commit server keys, service-account JSON, or `google-services.json`
to git. Store in `.env` / secrets manager / Flutter `android/app/` only locally.

---

## Firebase project

| Field | Value |
|---|---|
| **Console project name** | `manapujari` |
| **Project number** | `770184529713` |
| **Registered** | 2026-07-29 |

Console: [Firebase Console](https://console.firebase.google.com/) → project **manapujari**

---

## Android apps (registered)

Two separate Android apps in the **same** Firebase project — one per Flutter flavor /
Play Store listing.

### Customer flavor

| Field | Value |
|---|---|
| **Nickname** | Mana Guruji Customer |
| **Package name (`applicationId`)** | `com.managuruji.customer` |
| **Firebase App ID** | `1:770184529713:android:769399ecfb0db85ab8d210` |
| **Config file** | Download `google-services.json` from Firebase → Project settings → this app |

### Partner (pujari) flavor

| Field | Value |
|---|---|
| **Nickname** | Mana Guruji Partner |
| **Package name (`applicationId`)** | `com.managuruji.partner` |
| **Firebase App ID** | *(same project — copy from Firebase Console → Partner app row)* |
| **Config file** | Download `google-services.json` from Firebase → Project settings → this app |

**Rule:** `applicationId` in Flutter **must match** the package name above exactly.
Package names **cannot be changed** in Firebase after registration.

---

## iOS apps (not registered yet)

When adding iOS in Firebase, use matching bundle IDs:

| Flavor | Suggested bundle ID |
|---|---|
| Customer | `com.managuruji.customer` |
| Partner | `com.managuruji.partner` |

Also required: APNs key (.p8) uploaded in Firebase → Cloud Messaging.

---

## SHA certificate fingerprints (add when Flutter exists)

Firebase → Project settings → each Android app → **SHA certificate fingerprints**.

Add **debug** SHA-1/SHA-256 before first device test:

```powershell
# Windows — debug keystore (default Flutter/Android debug)
keytool -list -v -keystore "%USERPROFILE%\.android\debug.keystore" -alias androiddebugkey -storepass android -keypass android
```

Add **release** SHA-1/SHA-256 before Play Store / production FCM.

Required for: Google Sign-In (if used later), some Firebase features, Play Integrity.

---

## Backend FCM (this repo — `puja_platform`)

| Env var | Purpose |
|---|---|
| `FCM_SERVICE_ACCOUNT_PATH` | **Primary.** Path to Firebase service-account JSON (Project settings → Service accounts → Generate new private key). Used by `app/services/fcm_client.py` (HTTP v1). |
| `FCM_SERVER_KEY` | **Legacy fallback only** — omit on new projects (Legacy API disabled). |

Celery worker must include the `notifications` queue:

```powershell
celery -A app.workers.celery_app worker --pool=solo -Q dispatch,sweep,refund,notifications
```

Device registration API (after OTP login):

- `POST /v1/me/devices` — body `{ "device_token": "…", "platform": "android" | "ios" | "web" }`
- `DELETE /v1/me/devices/{device_token}` — on logout

E2E gate: `P-FCM-E2E` in `plans/STATUS.md` — complete when a real device receives
push after Flutter registers a token.

---

## Flutter repo checklist (when you create it)

Recommended repo name: `mana_guruji_mobile` (separate from `puja_platform`).

1. **Flavors** — `customer` and `partner` with distinct `applicationId`s above.
2. **`google-services.json`** — one per flavor (Gradle `productFlavors` copy task or
   `flutterfire configure` per flavor).
3. **Deps** — see `STACK_VERSIONS.md` (`firebase_core`, `firebase_messaging` 15.2.4).
4. **On login** — `POST /v1/me/devices` with FCM token; refresh on `onTokenRefresh`.
5. **API** — generate client from `spec/openapi.json`; base URL from env.
6. **Handle FCM `data.type`** — `offer_instant`, `offer_advance`, `reconfirm_ping`,
   `reconfirm_escalation`, `accept_ack`, `offer_withdrawn` (see `DISPATCH_FLOW.md` §21.6.H,
   `app/workers/notifications.py`, table below).
7. **Safety net** — partner still polls `GET /v1/offers` (15–30s foreground / on-resume).

### Suggested `build.gradle` flavor sketch

```gradle
productFlavors {
    customer {
        applicationId "com.managuruji.customer"
        // google-services.json → android/app/src/customer/
    }
    partner {
        applicationId "com.managuruji.partner"
        // google-services.json → android/app/src/partner/
    }
}
```

Run:

```bash
flutter run --flavor customer -t lib/main_customer.dart
flutter run --flavor partner -t lib/main_partner.dart
```

Repo: `mana_guruji/mana_guruji_mobile` (sibling of `puja_platform`).

API base URL:

```bash
# Android emulator → host machine
--dart-define=API_BASE_URL=http://10.0.2.2:8000

# Desktop / localhost
--dart-define=API_BASE_URL=http://127.0.0.1:8000
```

---

## FCM payload types (partner app — implement handlers)

| `data.type` | Priority | UX |
|---|---|---|
| `offer_instant` | high | Modal + Offers tab |
| `offer_advance` | normal | Inbox row on Offers tab |
| `reconfirm_ping` | high | Open booking → reconfirm or cancel |
| `reconfirm_escalation` | normal | RM / ops alert style |
| `accept_ack` | normal | Advance accept confirmation |
| `offer_withdrawn` | normal | Customer cancelled — refresh Offers tab / dismiss instant modal |

Customer push types: add rows here when customer notification worker paths are defined.

---

## Changelog

| Date | Change |
|---|---|
| 2026-07-29 | Firebase project `manapujari` created; Android apps `com.managuruji.customer` + `com.managuruji.partner` registered |
| 2026-07-29 | Flutter repo `mana_guruji/mana_guruji_mobile` scaffolded — Phase A partner-first (flavors, OpenAPI client, OTP, FCM hook, offers/bookings shell) |
| 2026-08-12 | `P-FCM-CUSTOMER-CANCEL` **COMPLETED** — `offer_withdrawn` FCM on customer cancel; partner Flutter handler + instant modal dismiss |
| 2026-08-10 | `P-CANCEL-OFFERS-SYNC` — customer cancel expires pending assignments; `GET /v1/offers` excludes `cancelled_at`; partner 410 refresh |
| 2026-07-30 | Added [`MOBILE_FLUTTER.md`](./MOBILE_FLUTTER.md) — normative Flutter implementation contract |
