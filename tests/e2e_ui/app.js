/**
 * TEST ONLY — manual E2E UI. Not imported by app/.
 * Calls API via /proxy (see serve.py).
 */
(() => {
  "use strict";

  const state = {
    customerToken: null,
    pujariToken: null,
    adminToken: null,
    adminTargetUserId: null,
    catalogCategoryId: null,
    catalogPujaId: null,
    catalogAddonId: null,
    catalogMediaId: null,
    bookingId: null,
    orderId: null,
    amountPaise: 0,
    addressId: null,
    holdId: null,
    msg91Configured: false,
    fast2smsConfigured: false,
    msg91Enabled: false,
    smsProviderOrder: "fast2sms,msg91",
    lastOtpSmsSent: null,
  };

  const $ = (id) => document.getElementById(id);
  const logEl = $("log");

  /** Always route via local proxy (serve.py) — never call :8000 directly from browser. */
  const API_PREFIX = "/proxy/v1";

  function apiBase() {
    const v = ($("apiBase")?.value || API_PREFIX).trim().replace(/\/$/, "");
    if (!v.startsWith("/proxy")) {
      return API_PREFIX;
    }
    return v;
  }

  function log(msg, kind = "") {
    const line = document.createElement("div");
    line.className = kind;
    line.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
    logEl.appendChild(line);
    logEl.scrollTop = logEl.scrollHeight;
  }

  async function api(method, path, { token, body, extraHeaders } = {}) {
    const url = `${apiBase()}${path.startsWith("/") ? path : `/${path}`}`;
    const headers = { ...(extraHeaders || {}) };
    if (token) headers.Authorization = `Bearer ${token}`;
    if (body !== undefined) headers["Content-Type"] = "application/json";

    log(`${method} ${url}`);
    const res = await fetch(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    const text = await res.text();
    let data;
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = { raw: text };
    }
    log(`${res.status} ${JSON.stringify(data, null, 2)}`, res.ok ? "log-ok" : "log-err");
    if (!res.ok) {
      const err = new Error(data.detail || res.statusText || "Request failed");
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  function describeSmsResult(data) {
    if (data.sms_sent === true) {
      const provider = data.sms_provider || "unknown";
      return { text: `sms_sent=true via ${provider} — check phone for SMS.`, cls: "log-ok" };
    }
    if (data.sms_sent === false) {
      return {
        text: "sms_sent=false — check FAST2SMS_API_KEY / MSG91 keys, or copy otp_dev_only from uvicorn (DEBUG=true).",
        cls: "warn",
      };
    }
    return { text: "—", cls: "" };
  }

  function setOtpInlineStatus(elId, data) {
    const el = $(elId);
    if (!el) return;
    const { text, cls } = describeSmsResult(data);
    if (data.sms_sent === true || data.sms_sent === false) {
      el.textContent = text;
      el.className = `hint otp-inline-status ${cls}`;
    }
  }

  function setOtpPanelStatus(data, phone) {
    const el = $("otpSmsStatus");
    if (!el) return;
    el.className = "otp-status";
    if (data.sms_sent === true) {
      const provider = data.sms_provider || "unknown";
      el.className = "otp-status ok";
      el.textContent = `Last API request (${phone}): sms_sent=true via ${provider} — enter SMS code below.`;
    } else if (data.sms_sent === false) {
      el.className = "otp-status warn";
      el.textContent = `Last API request (${phone}): sms_sent=false — check uvicorn logs or use otp_dev_only if DEBUG=true.`;
    } else {
      el.textContent = "Last API request: —";
    }
  }

  function setFast2smsDirectStatus(result) {
    const statusEl = $("fast2smsDirectStatus");
    const otpEl = $("fast2smsOtpHint");
    if (!statusEl) return;
    if (result.ok) {
      statusEl.className = "otp-status ok";
      statusEl.textContent = `FAST2SMS direct OK — request_id=${result.request_id || "?"}. Check phone for SMS.`;
      if (otpEl) {
        otpEl.textContent = `OTP sent (for verify below): ${result.otp}`;
        otpEl.className = "hint log-ok";
        if ($("otpCode")) $("otpCode").value = result.otp;
      }
    } else {
      const code = result.status_code ? ` [${result.status_code}]` : "";
      statusEl.className = "otp-status warn";
      statusEl.textContent = `FAST2SMS direct failed${code}: ${result.hint || result.message || result.detail || "unknown error"}`;
      if (otpEl) {
        otpEl.textContent = "OTP value (for verify below): —";
        otpEl.className = "hint";
      }
    }
  }

  async function testFast2smsDirect(phone) {
    const p = phone.trim();
    if (!p) return log("Enter phone for FAST2SMS direct test", "log-err");
    log(`POST /test-fast2sms.json phone=${p}`);
    const res = await fetch("/test-fast2sms.json", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone: p }),
    });
    const text = await res.text();
    let data;
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      log(`${res.status} non-JSON response — restart serve.py (need v5+). Body: ${text.slice(0, 120)}`, "log-err");
      throw new Error("test-fast2sms returned HTML — stop old serve.py and run: python tests/e2e_ui/serve.py");
    }
    log(`${res.status} ${JSON.stringify(data, null, 2)}`, data.ok ? "log-ok" : "log-err");
    setFast2smsDirectStatus(data);
    return data;
  }

  async function requestOtp(phone) {
    const p = phone.trim();
    const data = await api("POST", "/auth/otp/request", { body: { phone: p } });
    state.lastOtpSmsSent = data.sms_sent === true;
    setOtpPanelStatus(data, p);
    return data;
  }

  async function verifyOtp(phone, otp, appContext) {
    const p = phone.trim();
    const code = otp.trim();
    const ctx = appContext || "customer";
    // app_context is a body field (P-ADMIN-AUTH-FIX) — query params are ignored.
    const data = await api("POST", "/auth/otp/verify", {
      body: { phone: p, otp: code, app_context: ctx },
    });
    if (ctx === "customer") {
      state.customerToken = data.access_token;
      $("custPhone").value = p;
      $("custOtp").value = code;
      if ($("otpTokenStatus")) {
        $("otpTokenStatus").textContent = "Customer token saved (use Customer tab for booking).";
        $("otpTokenStatus").className = "hint log-ok";
      }
      log("Customer token saved", "log-ok");
      try {
        await loadServiceAreas();
      } catch (_) {
        /* areas load is optional until address step */
      }
    } else {
      state.pujariToken = data.access_token;
      state.pujariPhone = p;
      $("pjPhone").value = p;
      $("pjOtp").value = code;
      $("pjLoginHint").textContent = `Logged in as ${p}. Offers are per-pujari — use +910000000011 for seeded dispatch.`;
      $("pjLoginHint").className = p === "+910000000011" ? "hint log-ok" : "hint warn";
      if ($("otpTokenStatus")) {
        $("otpTokenStatus").textContent = "Pujari token saved (use Partner tab for offers).";
        $("otpTokenStatus").className = "hint log-ok";
      }
      log(`Pujari token saved (${p})`, "log-ok");
    }
    return data;
  }

  function updateOtpEnvHints() {
    const envEl = $("otpEnvStatus");
    const modeEl = $("otpModeHint");
    const summaryEl = $("otpProviderSummary");
    const parts = [];

    if (state.fast2smsConfigured) {
      parts.push("FAST2SMS: configured (FAST2SMS_API_KEY)");
    } else {
      parts.push("FAST2SMS: not configured");
    }
    if (state.msg91Configured) {
      parts.push("MSG91: enabled + keys OK");
    } else if (state.msg91Enabled) {
      parts.push("MSG91: enabled but missing AUTH_KEY/TEMPLATE_ID");
    } else {
      parts.push("MSG91: disabled (MSG91_ENABLED=false)");
    }
    parts.push(`order: ${state.smsProviderOrder}`);

    if (envEl) {
      envEl.textContent = parts.join(" · ");
      envEl.className = state.fast2smsConfigured || state.msg91Configured ? "hint log-ok" : "hint warn";
    }
    if (summaryEl) {
      summaryEl.textContent = state.fast2smsConfigured
        ? "Step 1: FAST2SMS direct test (no uvicorn). Step 2: API request → expect sms_provider=fast2sms."
        : "Set FAST2SMS_API_KEY in .env, or DEBUG=true for otp_dev_only dev mode.";
      summaryEl.className = state.fast2smsConfigured ? "hint log-ok" : "hint warn";
    }
    if (modeEl) {
      if (state.fast2smsConfigured) {
        modeEl.textContent =
          "FAST2SMS ready — use Direct test below, then API request to confirm sms_router failover.";
        modeEl.className = "hint log-ok";
      } else if (state.msg91Configured) {
        modeEl.textContent =
          "MSG91 ready — API request → uvicorn should log msg91_otp_sent (API authkey + template id).";
        modeEl.className = "hint log-ok";
      } else {
        modeEl.textContent = "Dev mode: Request OTP via API → copy otp_dev_only from uvicorn (DEBUG=true).";
        modeEl.className = "hint warn";
      }
    }
  }

  /** HMAC-SHA256 hex — mock Razorpay webhook locally (dev QA only). */
  async function hmacSha256Hex(secret, message) {
    const enc = new TextEncoder();
    const key = await crypto.subtle.importKey(
      "raw",
      enc.encode(secret),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"]
    );
    const sig = await crypto.subtle.sign("HMAC", key, enc.encode(message));
    return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
  }

  const E2E_PUJA_IDS = [
    "11111111-1111-1111-1111-111111111111", // Test Puja (ensure_seed)
    "e4444444-4444-4444-4444-444444444444", // Mahalakshmi
  ];

  function tomorrowIsoDate() {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    return d.toISOString().slice(0, 10);
  }

  /** Today + ~2h — instant dispatch window (lead ≤4h) and within seed availability. */
  function e2eSlotDefaults() {
    const slot = new Date(Date.now() + 2 * 60 * 60 * 1000);
    const pad = (n) => String(n).padStart(2, "0");
    return {
      date: `${slot.getFullYear()}-${pad(slot.getMonth() + 1)}-${pad(slot.getDate())}`,
      time: `${pad(slot.getHours())}:${pad(slot.getMinutes())}:00`,
    };
  }

  function applyE2eSlotDefaults() {
    const { date, time } = e2eSlotDefaults();
    if ($("slotDate")) $("slotDate").value = date;
    if ($("slotTime")) $("slotTime").value = time;
  }

  // ---- Admin TOTP (dev helper — RFC 6238 SHA1 / 6 digits / 30s) ------------
  function base32Decode(secret) {
    const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
    let bits = "";
    const s = secret.replace(/=+$/, "").replace(/\s/g, "").toUpperCase();
    for (const c of s) {
      const val = alphabet.indexOf(c);
      if (val < 0) continue;
      bits += val.toString(2).padStart(5, "0");
    }
    const bytes = [];
    for (let i = 0; i + 8 <= bits.length; i += 8) {
      bytes.push(parseInt(bits.slice(i, i + 8), 2));
    }
    return new Uint8Array(bytes);
  }

  async function totpAt(secret, atSec = Math.floor(Date.now() / 1000)) {
    const key = base32Decode(secret);
    if (!key.length) throw new Error("Invalid base32 secret");
    const counter = Math.floor(atSec / 30);
    const buf = new ArrayBuffer(8);
    const view = new DataView(buf);
    view.setUint32(0, 0);
    view.setUint32(4, counter);
    const cryptoKey = await crypto.subtle.importKey(
      "raw",
      key,
      { name: "HMAC", hash: "SHA-1" },
      false,
      ["sign"]
    );
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

  function setAdminLoginStatus(ok, msg) {
    const el = $("adminLoginStatus");
    if (!el) return;
    el.textContent = msg;
    el.className = ok ? "hint log-ok" : "hint log-err";
  }

  function renderAdminTarget(user) {
    state.adminTargetUserId = user.user_id;
    $("adminTargetUserId").textContent = user.user_id;
    const roles = Array.isArray(user.roles) ? user.roles : [];
    $("adminTargetRoles").textContent = roles.length ? roles.join(", ") : "(none)";
    let cred = "none";
    if (user.has_credential) {
      cred = user.credential_activated ? "provisioned + activated" : "provisioned (not activated)";
    }
    $("adminTargetCred").textContent = cred;
  }

  async function adminLogin(phone, code) {
    const data = await api("POST", "/admin/auth/login", {
      body: { phone: phone.trim(), code: code.trim() },
    });
    state.adminToken = data.access_token;
    setAdminLoginStatus(true, "Admin token saved — use sections below.");
    log("Admin token saved (app_context=admin)", "log-ok");
    return data;
  }

  async function lookupAdminUser(phone) {
    const p = phone.trim();
    if (!p) throw new Error("Enter target phone");
    log(`GET /test-user.json?phone=${p}`);
    const res = await fetch(`/test-user.json?phone=${encodeURIComponent(p)}`);
    const data = await res.json();
    log(`${res.status} ${JSON.stringify(data, null, 2)}`, res.ok ? "log-ok" : "log-err");
    if (!res.ok) throw new Error(data.detail || "Lookup failed");
    renderAdminTarget(data.user);
    return data.user;
  }

  function requireAdminToken() {
    if (!state.adminToken) {
      log("Login on Admin tab first (TOTP)", "log-err");
      return false;
    }
    return true;
  }

  function requireAdminTarget() {
    if (!state.adminTargetUserId) {
      log("Lookup target user by phone first", "log-err");
      return false;
    }
    return true;
  }

  const CATALOG = "/admin/catalog";

  function catalogLabel(prefix) {
    return `${prefix}-${Date.now().toString(36)}`;
  }

  function setCatalogOut(data) {
    const el = $("adminCatalogOut");
    if (el) el.textContent = JSON.stringify(data, null, 2);
  }

  function setCatalogSmokeStatus(ok, msg) {
    const el = $("adminCatalogSmokeStatus");
    if (!el) return;
    el.textContent = msg;
    el.className = ok ? "hint log-ok" : "hint log-err";
  }

  function renderCatalogIds({ category, puja, addon } = {}) {
    if (category) {
      state.catalogCategoryId = category.id;
      $("adminCatId").textContent = String(category.id);
      $("adminCatSlug").textContent = category.slug || "—";
    }
    if (puja) {
      state.catalogPujaId = puja.id;
      $("adminPujaId").textContent = puja.id;
    }
    if (addon) {
      state.catalogAddonId = addon.id;
      $("adminAddonId").textContent = addon.id;
    }
  }

  function requireCatalogCategory() {
    if (!state.catalogCategoryId) {
      log("Create or select a category first", "log-err");
      return false;
    }
    return true;
  }

  function requireCatalogPuja() {
    if (!state.catalogPujaId) {
      log("Create a puja first", "log-err");
      return false;
    }
    return true;
  }

  async function adminCatalogListCategories() {
    const data = await api("GET", `${CATALOG}/categories`, { token: state.adminToken });
    setCatalogOut(data);
    if (data.categories?.length) {
      renderCatalogIds({ category: data.categories[data.categories.length - 1] });
    }
    return data;
  }

  async function adminCatalogCreateCategory(name) {
    const catName = (name || catalogLabel("E2E-Cat")).trim();
    const data = await api("POST", `${CATALOG}/categories`, {
      token: state.adminToken,
      body: { name: catName, change_reason: "e2e-ui" },
    });
    renderCatalogIds({ category: data });
    setCatalogOut(data);
    if ($("adminCatName")) $("adminCatName").value = catName;
    return data;
  }

  async function adminCatalogUpdateCategory() {
    const id = state.catalogCategoryId;
    if (!id) throw new Error("No category ID — create or list first");
    const data = await api("PUT", `${CATALOG}/categories/${id}`, {
      token: state.adminToken,
      body: {
        description: `E2E updated ${new Date().toISOString()}`,
        change_reason: "e2e-ui",
      },
    });
    renderCatalogIds({ category: data });
    setCatalogOut(data);
    return data;
  }

  async function adminCatalogListPujas() {
    const q =
      state.catalogCategoryId != null ? `?category_id=${state.catalogCategoryId}` : "";
    const data = await api("GET", `${CATALOG}/pujas${q}`, { token: state.adminToken });
    setCatalogOut(data);
    if (data.pujas?.length) {
      renderCatalogIds({ puja: data.pujas[data.pujas.length - 1] });
    }
    return data;
  }

  async function adminCatalogCreatePuja(name, price) {
    if (!requireCatalogCategory()) throw new Error("category required");
    const pujaName = (name || catalogLabel("E2E-Puja")).trim();
    const defaultPrice = Number(price || $("adminPujaPrice")?.value || 1500);
    const data = await api("POST", `${CATALOG}/pujas`, {
      token: state.adminToken,
      body: {
        category_id: state.catalogCategoryId,
        name: pujaName,
        default_price: defaultPrice,
        price_max: defaultPrice + 500,
        duration_minutes: 90,
        tagline: "E2E smoke puja",
        change_reason: "e2e-ui",
      },
    });
    renderCatalogIds({ puja: data });
    setCatalogOut(data);
    if ($("adminPujaName")) $("adminPujaName").value = pujaName;
    return data;
  }

  async function adminCatalogUpdatePuja() {
    if (!requireCatalogPuja()) throw new Error("puja required");
    const data = await api("PUT", `${CATALOG}/pujas/${state.catalogPujaId}`, {
      token: state.adminToken,
      body: {
        tagline: `E2E tagline ${Date.now()}`,
        change_reason: "e2e-ui",
      },
    });
    renderCatalogIds({ puja: data });
    setCatalogOut(data);
    return data;
  }

  async function adminCatalogPujaImpact() {
    if (!requireCatalogPuja()) throw new Error("puja required");
    const data = await api("GET", `${CATALOG}/pujas/${state.catalogPujaId}/impact`, {
      token: state.adminToken,
    });
    setCatalogOut(data);
    return data;
  }

  async function adminCatalogGetContent() {
    if (!requireCatalogPuja()) throw new Error("puja required");
    const data = await api(
      "GET",
      `${CATALOG}/pujas/${state.catalogPujaId}/content?kind=inclusion`,
      { token: state.adminToken }
    );
    setCatalogOut(data);
    return data;
  }

  async function adminCatalogPutContent() {
    if (!requireCatalogPuja()) throw new Error("puja required");
    const data = await api("PUT", `${CATALOG}/pujas/${state.catalogPujaId}/content`, {
      token: state.adminToken,
      body: {
        kind: "inclusion",
        items: [
          { text: "Flowers and fruits", position: 0 },
          { text: "Prasad for family", position: 1 },
        ],
        change_reason: "e2e-ui",
      },
    });
    setCatalogOut(data);
    return data;
  }

  async function adminCatalogListAddons() {
    if (!requireCatalogPuja()) throw new Error("puja required");
    const data = await api("GET", `${CATALOG}/pujas/${state.catalogPujaId}/addons`, {
      token: state.adminToken,
    });
    setCatalogOut(data);
    if (data.addons?.length) {
      renderCatalogIds({ addon: data.addons[data.addons.length - 1] });
    }
    return data;
  }

  async function adminCatalogCreateAddon() {
    if (!requireCatalogPuja()) throw new Error("puja required");
    const data = await api("POST", `${CATALOG}/pujas/${state.catalogPujaId}/addons`, {
      token: state.adminToken,
      body: {
        name: "Extra diya",
        price: 99,
        description: "Brass diya",
        change_reason: "e2e-ui",
      },
    });
    renderCatalogIds({ addon: data });
    setCatalogOut(data);
    return data;
  }

  async function adminCatalogUpdateAddon() {
    if (!state.catalogAddonId) throw new Error("Create addon first");
    const data = await api("PUT", `${CATALOG}/addons/${state.catalogAddonId}`, {
      token: state.adminToken,
      body: { is_active: false, change_reason: "e2e-ui retire addon" },
    });
    renderCatalogIds({ addon: data });
    setCatalogOut(data);
    return data;
  }

  function intToUuid(n) {
    const hex = BigInt(n).toString(16).padStart(32, "0");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  function _mediaEntityId(entityType) {
    if (entityType === "category") {
      if (!state.catalogCategoryId) throw new Error("Create or list a category first");
      return intToUuid(state.catalogCategoryId);
    }
    if (!state.catalogPujaId) throw new Error("Create a puja first");
    return state.catalogPujaId;
  }

  async function adminCatalogUploadMedia(file, entityType) {
    if (!file) throw new Error("Choose an image file");
    const entityId = _mediaEntityId(entityType);
    const contentType = file.type || "image/jpeg";
    const presign = await api("POST", `${CATALOG}/media/presign`, {
      token: state.adminToken,
      body: {
        entity_type: entityType,
        entity_id: entityId,
        content_type: contentType,
        content_length: file.size,
        alt_text: "E2E upload",
        change_reason: "e2e-ui",
      },
    });

    log(`PUT upload via API proxy → ${presign.s3_key}`);
    const uploadUrl = `${apiBase()}${CATALOG}/media/${presign.media_id}/upload`;
    let putRes;
    try {
      putRes = await fetch(uploadUrl, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${state.adminToken}`,
          "Content-Type": contentType,
        },
        body: file,
      });
    } catch (fetchErr) {
      throw fetchErr;
    }
    if (!putRes.ok) {
      const t = await putRes.text();
      throw new Error(`Upload proxy failed ${putRes.status}: ${t.slice(0, 200)}`);
    }
    log(`Upload proxy ${putRes.status}`, "log-ok");

    const confirmed = await api("POST", `${CATALOG}/media/${presign.media_id}/confirm`, {
      token: state.adminToken,
      body: {},
    });
    state.catalogMediaId = confirmed.id;
    if ($("adminMediaId")) $("adminMediaId").textContent = confirmed.id;
    if ($("adminMediaUrl")) $("adminMediaUrl").textContent = confirmed.public_url || "—";
    setCatalogOut(confirmed);
    return confirmed;
  }

  async function adminCatalogSmoke() {
    if (!requireAdminToken()) throw new Error("admin token required");
    const cat = await adminCatalogCreateCategory($("adminCatName")?.value.trim() || "");
    await adminCatalogListCategories();
    await adminCatalogUpdateCategory();
    const puja = await adminCatalogCreatePuja(
      $("adminPujaName")?.value.trim() || "",
      $("adminPujaPrice")?.value
    );
    await adminCatalogPujaImpact();
    await adminCatalogPutContent();
    const content = await adminCatalogGetContent();
    if (!content.items || content.items.length < 2) {
      throw new Error("content replace-all did not persist 2 inclusions");
    }
    const addon = await adminCatalogCreateAddon();
    await adminCatalogListAddons();
    await adminCatalogUpdateAddon();
    await adminCatalogUpdatePuja();

    // Duplicate category name must 409
    try {
      await api("POST", `${CATALOG}/categories`, {
        token: state.adminToken,
        body: { name: cat.name },
      });
      throw new Error("duplicate category name should return 409");
    } catch (err) {
      if (err.status !== 409) throw err;
      log("Duplicate category correctly rejected (409)", "log-ok");
    }

    return { category: cat, puja, addon, content };
  }

  function updateAdminEnvHints() {
    const el = $("adminEnvStatus");
    if (!el) return;
    if (state.totpEncConfigured) {
      el.textContent =
        "TOTP_ENC_KEYS: configured in .env. Run bootstrap_admin.py if you have no admin yet.";
      el.className = "hint log-ok";
    } else {
      el.textContent =
        "TOTP_ENC_KEYS: NOT set — add a Fernet key to .env and restart uvicorn before admin login.";
      el.className = "hint warn";
    }
  }

  // Tabs
  let opsPollTimer = null;
  let knownBookingIds = new Set();

  function switchTab(tabName) {
    document.querySelectorAll(".tab").forEach((b) => {
      b.classList.toggle("active", b.dataset.tab === tabName);
    });
    document.querySelectorAll(".tab-panel").forEach((p) => {
      p.classList.toggle("active", p.id === `tab-${tabName}`);
    });
    if (tabName === "ops") {
      startOpsPoll();
    } else {
      stopOpsPoll();
    }
  }

  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  $("btnClearLog").addEventListener("click", () => {
    logEl.textContent = "";
  });

  $("btnHealth").addEventListener("click", async () => {
    try {
      const res = await fetch("/proxy/health");
      const data = await res.json();
      log(`health ${res.status} ${JSON.stringify(data)}`, res.ok ? "log-ok" : "log-err");
    } catch (e) {
      log(`health error: ${e.message}`, "log-err");
    }
  });

  // Customer OTP (uses shared helpers)
  $("btnCustOtp").addEventListener("click", async () => {
    try {
      const phone = $("custPhone").value.trim();
      const data = await requestOtp(phone);
      setOtpInlineStatus("custOtpStatus", data);
      if ($("otpPhone")) $("otpPhone").value = phone;
    } catch (_) {}
  });

  $("btnCustVerify").addEventListener("click", async () => {
    try {
      await verifyOtp($("custPhone").value, $("custOtp").value, "customer");
    } catch (_) {}
  });

  // Dedicated OTP / SMS tab
  $("btnFast2smsDirect")?.addEventListener("click", async () => {
    try {
      const phone = ($("fast2smsPhone")?.value || $("otpPhone")?.value || "").trim();
      if ($("fast2smsPhone") && phone) $("fast2smsPhone").value = phone;
      if ($("otpPhone") && phone) $("otpPhone").value = phone;
      await testFast2smsDirect(phone);
    } catch (e) {
      log(`FAST2SMS direct error: ${e.message}`, "log-err");
    }
  });

  $("btnOtpRequest")?.addEventListener("click", async () => {
    try {
      const phone = $("otpPhone").value.trim();
      if (!phone) return log("Enter phone on OTP tab", "log-err");
      const data = await requestOtp(phone);
      if (data.sms_sent === true) {
        log(`SMS OK via ${data.sms_provider || "unknown"} — check phone`, "log-ok");
      } else {
        log("No SMS sent — check DEBUG uvicorn log for otp_dev_only", "log-warn");
      }
    } catch (_) {}
  });

  $("btnOtpVerify")?.addEventListener("click", async () => {
    try {
      const phone = $("otpPhone").value.trim();
      const otp = $("otpCode").value.trim();
      const ctx = $("otpAppContext").value;
      if (!phone || !otp) return log("Phone and OTP required", "log-err");
      await verifyOtp(phone, otp, ctx);
    } catch (_) {}
  });

  $("btnOtpRequestVerify")?.addEventListener("click", async () => {
    try {
      const phone = $("otpPhone").value.trim();
      const otp = $("otpCode").value.trim();
      const ctx = $("otpAppContext").value;
      if (!phone) return log("Enter phone first", "log-err");
      await requestOtp(phone);
      if (!otp) {
        log("Enter OTP in the field above, then click Verify (or this button again)", "log-warn");
        return;
      }
      await verifyOtp(phone, otp, ctx);
    } catch (_) {}
  });

  $("otpPhone")?.addEventListener("change", () => {
    const p = $("otpPhone").value.trim();
    if (p) {
      $("custPhone").value = p;
      $("pjPhone").value = p;
      if ($("fast2smsPhone")) $("fast2smsPhone").value = p;
    }
  });

  $("fast2smsPhone")?.addEventListener("change", () => {
    const p = $("fast2smsPhone").value.trim();
    if (p && $("otpPhone")) $("otpPhone").value = p;
  });

  async function loadServiceAreas({ autoSelectE2e = true } = {}) {
    if (!state.customerToken) return log("Login customer first", "log-err");
    const city = ($("addrCity")?.value || "").trim();
    const path = city ? `/service-areas?city=${encodeURIComponent(city)}` : "/service-areas";
    const data = await api("GET", path, { token: state.customerToken });
    const sel = $("addrServiceArea");
    if (!sel) return data;
    sel.innerHTML = "";
    const areas = data.areas || [];
    if (!areas.length) {
      sel.innerHTML = '<option value="">No active areas — run ensure_seed.py</option>';
      log("No service areas — run: python tests/e2e_ui/ensure_seed.py", "log-err");
      return data;
    }
    for (const a of areas) {
      const opt = document.createElement("option");
      opt.value = String(a.id);
      opt.textContent = `${a.city} — ${a.zone_name}`;
      sel.appendChild(opt);
    }
    if (autoSelectE2e) {
      const e2e = areas.find((a) => a.zone_name === "E2E Zone");
      if (e2e) sel.value = String(e2e.id);
    }
    log(`Loaded ${areas.length} service area(s)`, "log-ok");
    return data;
  }

  $("btnLoadServiceAreas")?.addEventListener("click", async () => {
    try {
      await loadServiceAreas();
    } catch (_) {}
  });

  $("btnCreateAddr").addEventListener("click", async () => {
    if (!state.customerToken) return log("Login customer first", "log-err");
    const serviceAreaId = Number($("addrServiceArea")?.value);
    if (!serviceAreaId) {
      return log("Select service area — click GET /service-areas first", "log-err");
    }
    try {
      const data = await api("POST", "/addresses", {
        token: state.customerToken,
        body: {
          line1: $("addrLine1").value,
          city: $("addrCity").value,
          latitude: Number($("addrLat").value),
          longitude: Number($("addrLng").value),
          service_area_id: serviceAreaId,
          is_default: true,
        },
      });
      state.addressId = data.id;
      $("addressId").textContent = data.id;
    } catch (_) {}
  });

  $("btnFillSeedPujari")?.addEventListener("click", async () => {
    try {
      const res = await fetch("/test-pujari.json?phone=%2B910000000011");
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      const pid = data.pujari?.pujari_id;
      if (!pid) throw new Error("pujari_id missing in response");
      $("holdPujari").value = pid;
      log(`Filled seed pujari_id ${pid} — POST /slot-holds should return 410`, "log-ok");
    } catch (err) {
      log(`Fill seed pujari failed: ${err.message}`, "log-err");
    }
  });

  $("btnLoadPujas").addEventListener("click", async () => {
    if (!state.customerToken) return log("Login customer first", "log-err");
    try {
      const data = await api("GET", "/pujas", { token: state.customerToken });
      const pujas = data.pujas || [];
      if (!pujas.length) return;
      const e2e =
        pujas.find((p) => E2E_PUJA_IDS.includes(p.id)) ||
        pujas.find((p) => p.name === "Test Puja") ||
        pujas.find((p) => p.name === "Mahalakshmi");
      const pick = e2e || pujas[0];
      if (!$("pujaId").value) $("pujaId").value = pick.id;
      if (e2e) {
        log(`E2E puja selected: ${pick.name} (${pick.id})`, "log-ok");
      } else {
        log(
          `Warning: no seeded E2E puja found — run ensure_seed.py. Using ${pick.name}`,
          "log-err"
        );
      }
      applyE2eSlotDefaults();
      log(`Slot set to ${$("slotDate").value} ${$("slotTime").value} (instant dispatch)`, "log-ok");
    } catch (_) {}
  });

  $("btnHold").addEventListener("click", async () => {
    if (!state.customerToken) return log("Login customer first", "log-err");
    const pj = $("holdPujari").value.trim();
    try {
      const body = {
        date: $("slotDate").value || tomorrowIsoDate(),
        time: $("slotTime").value || "10:00:00",
      };
      if (pj) body.pujari_id = pj;
      const data = await api("POST", "/slot-holds", { token: state.customerToken, body });
      state.holdId = data.hold_id;
      $("holdId").textContent = data.hold_id;
    } catch (_) {}
  });

  $("btnBook").addEventListener("click", async () => {
    if (!state.customerToken) return log("Login customer first", "log-err");
    if (!state.addressId) return log("Create address first", "log-err");
    if (!state.holdId) return log("Create hold first", "log-err");
    if (!$("pujaId").value) return log("Set puja ID", "log-err");
    try {
      const data = await api("POST", "/bookings", {
        token: state.customerToken,
        body: {
          hold_id: state.holdId,
          puja_id: $("pujaId").value.trim(),
          address_id: state.addressId,
          payment_mode: $("payMode").value,
          addon_ids: [],
        },
      });
      applyBookingResponse(data);
    } catch (err) {
      if (err.status === 409 && err.data?.razorpay_order_id) {
        applyBookingResponse(err.data);
        log("Duplicate booking — resuming existing Razorpay order", "log-ok");
      }
    }
  });

  function applyBookingResponse(data) {
    state.bookingId = data.booking_id;
    state.orderId = data.razorpay_order_id;
    state.amountPaise = Math.round(Number(data.amount_due_online) * 100);
    $("bookingId").textContent = data.booking_id;
    $("orderId").textContent = data.razorpay_order_id || "—";
    $("amountOnline").textContent = `₹${data.amount_due_online} (${state.amountPaise} paise)`;
    $("btnMockWebhook").disabled = !data.booking_id;
    $("btnConfirmPayTest").disabled = !data.booking_id;
    syncRzpPayButton();
  }

  async function confirmPaymentTest(bookingId) {
    const bid = (bookingId || state.bookingId || "").trim();
    if (!bid) throw new Error("booking_id required");
    log(`Confirm payment (test) booking=${bid}`);
    let res = await fetch("/test-confirm-payment.json", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ booking_id: bid }),
    });
    if (res.status === 404) {
      res = await fetch(`/test-confirm-payment.json?booking_id=${encodeURIComponent(bid)}`);
    }
    const data = await res.json();
    if (!res.ok || data.ok === false) {
      throw new Error(data.detail || JSON.stringify(data));
    }
    log(`Payment confirmed — status ${data.webhook?.result || data.status || "ok"}`, "log-ok");
    log("Next: Celery dispatch → Partner heartbeat → GET /offers (or Test ops Re-dispatch)", "log-ok");
    return data;
  }

  $("btnRzpPay").addEventListener("click", () => {
    const key = ($("rzKeyPay")?.value || $("rzKey").value).trim();
    if (!key || !state.orderId) return;
    if (typeof Razorpay === "undefined") return log("Razorpay checkout.js failed to load", "log-err");

    const rzp = new Razorpay({
      key,
      amount: state.amountPaise,
      currency: "INR",
      name: "Puja Platform (TEST)",
      description: "E2E test booking",
      order_id: state.orderId,
      handler(response) {
        log(`Razorpay payment success: ${JSON.stringify(response)}`, "log-ok");
        log(
          "Booking is still payment_pending until webhook arrives. Click Confirm payment (test) or set up ngrok.",
          "log-err"
        );
      },
      modal: {
        ondismiss() {
          log("Razorpay checkout closed", "log-err");
        },
      },
    });
    rzp.on("payment.failed", (r) => log(`Razorpay failed: ${JSON.stringify(r.error)}`, "log-err"));
    rzp.open();
  });

  $("btnMockWebhook").addEventListener("click", async () => {
    const secret = $("whSecret").value.trim();
    if (!secret) {
      if (!state.bookingId) return log("Create booking first", "log-err");
      try {
        await confirmPaymentTest(state.bookingId);
      } catch (err) {
        log(`Mock pay failed: ${err.message}`, "log-err");
      }
      return;
    }
    if (!state.bookingId) return log("Create booking first", "log-err");

    const paymentId = `pay_test_${crypto.randomUUID().slice(0, 12)}`;
    const body = {
      event: "payment.captured",
      payload: {
        payment: {
          entity: {
            id: paymentId,
            amount: state.amountPaise || 210000,
            currency: "INR",
            notes: { booking_id: state.bookingId },
          },
        },
      },
    };
    const raw = JSON.stringify(body);
    try {
      const sig = await hmacSha256Hex(secret, raw);
      await api("POST", "/webhooks/razorpay", {
        body,
        extraHeaders: { "X-Razorpay-Signature": sig },
      });
      log("Mock webhook sent — check Celery for dispatch", "log-ok");
    } catch (_) {}
  });

  $("btnConfirmPayTest")?.addEventListener("click", async () => {
    try {
      await confirmPaymentTest();
    } catch (err) {
      log(`Confirm payment failed: ${err.message}`, "log-err");
    }
  });

  $("btnBookingStatus").addEventListener("click", async () => {
    if (!state.customerToken || !state.bookingId) return log("Need customer login + booking", "log-err");
    try {
      await api("GET", `/bookings/${state.bookingId}`, { token: state.customerToken });
    } catch (_) {}
  });

  // Partner
  $("btnPjOtp").addEventListener("click", async () => {
    try {
      const phone = $("pjPhone").value.trim();
      const data = await requestOtp(phone);
      setOtpInlineStatus("pjOtpStatus", data);
      if ($("otpPhone")) {
        $("otpPhone").value = phone;
        $("otpAppContext").value = "pujari";
      }
    } catch (_) {}
  });

  $("btnPjVerify").addEventListener("click", async () => {
    try {
      await verifyOtp($("pjPhone").value, $("pjOtp").value, "pujari");
    } catch (_) {}
  });

  $("btnHeartbeat").addEventListener("click", async () => {
    if (!state.pujariToken) return log("Login pujari first", "log-err");
    try {
      await api("PUT", "/me/heartbeat", {
        token: state.pujariToken,
        body: { lat: parseFloat($("pjLat").value), lng: parseFloat($("pjLng").value) },
      });
    } catch (_) {}
  });

  $("btnOffers").addEventListener("click", async () => {
    if (!state.pujariToken) return log("Login pujari first", "log-err");
    if (state.pujariPhone && state.pujariPhone !== "+910000000011") {
      log(`Warning: logged in as ${state.pujariPhone}, not +910000000011`, "log-err");
    }
    try {
      const data = await api("GET", "/offers", { token: state.pujariToken });
      const live = (data.offers || []).filter((o) => new Date(o.expires_at) > new Date());
      if (!live.length) {
        log("No live offers — run ensure_seed + redispatch, then Heartbeat within 2 min", "log-err");
        $("assignmentId").value = "";
        return;
      }
      const o = live[0];
      $("assignmentId").value = o.assignment_id;
      log(
        `Live offer: booking ${o.booking_id} · slot ${o.scheduled_date} ${o.scheduled_time} · expires ${o.expires_at}`,
        "log-ok"
      );
    } catch (_) {}
  });

  $("btnAccept").addEventListener("click", async () => {
    if (!state.pujariToken) return log("Login pujari first", "log-err");
    const aid = $("assignmentId").value.trim();
    if (!aid) return log("Set assignment ID", "log-err");
    try {
      await api("POST", `/offers/${aid}/accept`, { token: state.pujariToken });
    } catch (_) {}
  });

  $("btnReject").addEventListener("click", async () => {
    if (!state.pujariToken) return log("Login pujari first", "log-err");
    const aid = $("assignmentId").value.trim();
    if (!aid) return log("Set assignment ID", "log-err");
    try {
      await api("POST", `/offers/${aid}/reject`, { token: state.pujariToken });
    } catch (_) {}
  });

  // Admin (Phase 4 — TOTP)
  $("btnAdminFillCode")?.addEventListener("click", async () => {
    try {
      const secret = $("adminTotpSecret").value.trim();
      if (!secret) return log("Paste bootstrap secret first", "log-err");
      const code = await totpAt(secret);
      $("adminTotpCode").value = code;
      log(`Dev TOTP code filled (${code}) — valid ~30s`, "log-ok");
    } catch (err) {
      log(`TOTP generate failed: ${err.message}`, "log-err");
    }
  });

  $("btnAdminLogin")?.addEventListener("click", async () => {
    try {
      const phone = $("adminPhone").value.trim();
      const code = $("adminTotpCode").value.trim();
      if (!phone || !code) return log("Admin phone and TOTP code required", "log-err");
      await adminLogin(phone, code);
    } catch (err) {
      let msg = err.message || err.data?.detail || "error";
      if (err.status === 503) {
        msg =
          "TOTP_ENC_KEYS mismatch — the credential in DB was encrypted with a different key than uvicorn has. " +
          "Fix: set TOTP_ENC_KEYS in .env → restart uvicorn → run " +
          "python scripts/bootstrap_admin.py --phone YOUR_PHONE --reset → re-add secret in Authenticator.";
      }
      setAdminLoginStatus(false, `Login failed: ${msg}`);
      log(`Admin login failed (${err.status || "?"}): ${msg}`, "log-err");
    }
  });

  $("btnAdminGetAdvance")?.addEventListener("click", async () => {
    if (!requireAdminToken()) return;
    try {
      const data = await api("GET", "/admin/settings/advance-booking-amount", {
        token: state.adminToken,
      });
      $("adminAdvanceOut").textContent = JSON.stringify(data, null, 2);
    } catch (_) {}
  });

  $("btnAdminSetAdvance")?.addEventListener("click", async () => {
    if (!requireAdminToken()) return;
    const amt = $("adminAdvanceAmt").value.trim();
    if (!amt) return log("Enter new advance amount", "log-err");
    try {
      const data = await api("PUT", "/admin/settings/advance-booking-amount", {
        token: state.adminToken,
        body: {
          amount: amt,
          change_reason: $("adminAdvanceReason").value.trim() || null,
        },
      });
      $("adminAdvanceOut").textContent = JSON.stringify(data, null, 2);
    } catch (_) {}
  });

  $("btnAdminLookupUser")?.addEventListener("click", async () => {
    try {
      await lookupAdminUser($("adminTargetPhone").value);
    } catch (err) {
      $("adminTargetUserId").textContent = "—";
      $("adminTargetRoles").textContent = "—";
      $("adminTargetCred").textContent = "—";
      state.adminTargetUserId = null;
    }
  });

  $("btnAdminListRoles")?.addEventListener("click", async () => {
    if (!requireAdminToken() || !requireAdminTarget()) return;
    try {
      const data = await api("GET", `/admin/users/${state.adminTargetUserId}/roles`, {
        token: state.adminToken,
      });
      renderAdminTarget({
        user_id: data.user_id,
        roles: data.roles,
        has_credential: $("adminTargetCred").textContent.includes("provisioned"),
        credential_activated: $("adminTargetCred").textContent.includes("activated"),
      });
      log(`Roles: ${(data.roles || []).join(", ") || "(none)"}`, "log-ok");
    } catch (_) {}
  });

  $("btnAdminAssignRole")?.addEventListener("click", async () => {
    if (!requireAdminToken() || !requireAdminTarget()) return;
    try {
      const data = await api("POST", `/admin/users/${state.adminTargetUserId}/roles`, {
        token: state.adminToken,
        body: {
          role: $("adminAssignRole").value,
          change_reason: $("adminRoleReason").value.trim() || null,
        },
      });
      renderAdminTarget({
        user_id: data.user_id,
        roles: data.roles,
        has_credential: $("adminTargetCred").textContent.includes("provisioned"),
        credential_activated: $("adminTargetCred").textContent.includes("activated"),
      });
    } catch (_) {}
  });

  $("btnAdminRevokeRole")?.addEventListener("click", async () => {
    if (!requireAdminToken() || !requireAdminTarget()) return;
    const role = $("adminAssignRole").value;
    try {
      const data = await api("DELETE", `/admin/users/${state.adminTargetUserId}/roles/${role}`, {
        token: state.adminToken,
      });
      renderAdminTarget({
        user_id: data.user_id,
        roles: data.roles,
        has_credential: $("adminTargetCred").textContent.includes("provisioned"),
        credential_activated: $("adminTargetCred").textContent.includes("activated"),
      });
    } catch (_) {}
  });

  $("btnAdminProvision")?.addEventListener("click", async () => {
    if (!requireAdminToken() || !requireAdminTarget()) return;
    try {
      const data = await api("POST", `/admin/users/${state.adminTargetUserId}/credential`, {
        token: state.adminToken,
      });
      const out = [
        data.note || "",
        `user_id: ${data.user_id}`,
        `secret: ${data.secret}`,
        `otpauth: ${data.provisioning_uri}`,
      ].join("\n");
      $("adminProvisionOut").textContent = out;
      $("adminProvisionOut").className = "admin-pre admin-secret";
      if ($("adminTotpSecret")) $("adminTotpSecret").value = data.secret;
      $("adminTargetCred").textContent = "provisioned (not activated)";
      log("Credential provisioned — secret shown once above", "log-ok");
    } catch (_) {}
  });

  $("adminTargetPhone")?.addEventListener("change", () => {
    state.adminTargetUserId = null;
    $("adminTargetUserId").textContent = "—";
    $("adminTargetRoles").textContent = "—";
    $("adminTargetCred").textContent = "—";
  });

  // Admin catalogue (4B Wave 1)
  $("btnAdminCatalogSmoke")?.addEventListener("click", async () => {
    if (!requireAdminToken()) return;
    setCatalogSmokeStatus(false, "Smoke: running…");
    try {
      const result = await adminCatalogSmoke();
      setCatalogSmokeStatus(
        true,
        `Smoke OK — category ${result.category.id}, puja ${result.puja.id}, addon ${result.addon.id}`
      );
      log("Catalogue smoke passed (categories → pujas → content → addons)", "log-ok");
    } catch (err) {
      const msg = err.message || err.data?.detail || "failed";
      setCatalogSmokeStatus(false, `Smoke failed: ${msg}`);
      log(`Catalogue smoke failed: ${msg}`, "log-err");
    }
  });

  $("btnAdminCatList")?.addEventListener("click", async () => {
    if (!requireAdminToken()) return;
    try {
      await adminCatalogListCategories();
    } catch (_) {}
  });

  $("btnAdminCatCreate")?.addEventListener("click", async () => {
    if (!requireAdminToken()) return;
    try {
      await adminCatalogCreateCategory($("adminCatName")?.value.trim() || "");
    } catch (_) {}
  });

  $("btnAdminCatUpdate")?.addEventListener("click", async () => {
    if (!requireAdminToken()) return;
    if (!requireCatalogCategory()) return;
    try {
      await adminCatalogUpdateCategory();
    } catch (_) {}
  });

  $("btnAdminPujaList")?.addEventListener("click", async () => {
    if (!requireAdminToken()) return;
    try {
      await adminCatalogListPujas();
    } catch (_) {}
  });

  $("btnAdminPujaCreate")?.addEventListener("click", async () => {
    if (!requireAdminToken()) return;
    if (!requireCatalogCategory()) return;
    try {
      await adminCatalogCreatePuja(
        $("adminPujaName")?.value.trim() || "",
        $("adminPujaPrice")?.value
      );
    } catch (_) {}
  });

  $("btnAdminPujaUpdate")?.addEventListener("click", async () => {
    if (!requireAdminToken()) return;
    if (!requireCatalogPuja()) return;
    try {
      await adminCatalogUpdatePuja();
    } catch (_) {}
  });

  $("btnAdminPujaImpact")?.addEventListener("click", async () => {
    if (!requireAdminToken()) return;
    if (!requireCatalogPuja()) return;
    try {
      await adminCatalogPujaImpact();
    } catch (_) {}
  });

  $("btnAdminContentGet")?.addEventListener("click", async () => {
    if (!requireAdminToken()) return;
    if (!requireCatalogPuja()) return;
    try {
      await adminCatalogGetContent();
    } catch (_) {}
  });

  $("btnAdminContentPut")?.addEventListener("click", async () => {
    if (!requireAdminToken()) return;
    if (!requireCatalogPuja()) return;
    try {
      await adminCatalogPutContent();
    } catch (_) {}
  });

  $("btnAdminAddonList")?.addEventListener("click", async () => {
    if (!requireAdminToken()) return;
    if (!requireCatalogPuja()) return;
    try {
      await adminCatalogListAddons();
    } catch (_) {}
  });

  $("btnAdminAddonCreate")?.addEventListener("click", async () => {
    if (!requireAdminToken()) return;
    if (!requireCatalogPuja()) return;
    try {
      await adminCatalogCreateAddon();
    } catch (_) {}
  });

  $("btnAdminAddonUpdate")?.addEventListener("click", async () => {
    if (!requireAdminToken()) return;
    if (!state.catalogAddonId) return log("Create addon first", "log-err");
    try {
      await adminCatalogUpdateAddon();
    } catch (_) {}
  });

  $("btnAdminMediaUpload")?.addEventListener("click", async () => {
    if (!requireAdminToken()) return;
    const file = $("adminMediaFile")?.files?.[0];
    const entityType = $("adminMediaEntityType")?.value || "puja";
    try {
      await adminCatalogUploadMedia(file, entityType);
      log("Media upload confirmed", "log-ok");
    } catch (err) {
      log(`Media upload failed: ${err.message}`, "log-err");
    }
  });

  // Test ops dashboard (read-only DB feed via serve.py)
  function fmtShortTs(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return iso;
    }
  }

  function fmtSlot(date, time) {
    if (!date) return "—";
    const t = time ? String(time).slice(0, 5) : "";
    return t ? `${date} ${t}` : date;
  }

  function statusPill(code) {
    const c = code || "unknown";
    const cls = ["requested", "confirmed", "payment_pending"].includes(c) ? c : "default";
    return `<span class="status-pill ${cls}">${c}</span>`;
  }

  function opsRowClass(row) {
    if (row.status === "payment_pending") return "row-pending-pay";
    if (row.status === "requested" && row.paid_at) return "row-waiting";
    if (row.status === "confirmed") return "row-confirmed";
    return "";
  }

  function renderOpsTable(bookings) {
    const body = $("opsTableBody");
    if (!bookings.length) {
      body.innerHTML = '<tr><td colspan="11" class="ops-empty">No bookings yet — create one on Customer tab.</td></tr>';
      return;
    }
    body.innerHTML = bookings
      .map(
        (b) => `
      <tr class="${opsRowClass(b)}">
        <td>${fmtShortTs(b.created_at)}</td>
        <td>${statusPill(b.status)}</td>
        <td>${b.customer_phone || "—"}</td>
        <td>${b.puja_name || "—"}</td>
        <td>${fmtSlot(b.scheduled_date, b.scheduled_time)}</td>
        <td>${b.amount_due_online != null ? b.amount_due_online : "—"}</td>
        <td>${b.paid_at ? "✓" : "—"}</td>
        <td class="mono">${b.razorpay_payment_id || "—"}</td>
        <td>${b.offers_live ?? 0} live / ${b.offers_sent ?? 0} total</td>
        <td>${b.assigned_pujari_name || b.assigned_pujari_phone || "—"}</td>
        <td class="mono ops-booking-id" data-booking-id="${b.booking_id}">${b.booking_id}</td>
      </tr>`
      )
      .join("");
    body.querySelectorAll(".ops-booking-id").forEach((cell) => {
      cell.style.cursor = "pointer";
      cell.title = "Click to copy booking id into Re-dispatch field";
      cell.addEventListener("click", () => {
        $("opsRedispatchId").value = cell.dataset.bookingId || cell.textContent.trim();
      });
    });
  }

  async function refreshOpsDashboard() {
    const errEl = $("opsError");
    errEl.hidden = true;
    try {
      const res = await fetch("/test-bookings.json?limit=50");
      const raw = await res.text();
      const ctype = res.headers.get("content-type") || "";
      if (!ctype.includes("json") && raw.trimStart().startsWith("<")) {
        throw new Error(
          "Server returned HTML (404) — stop the old process on port 8765 and restart: python tests/e2e_ui/serve.py"
        );
      }
      let data;
      try {
        data = raw ? JSON.parse(raw) : {};
      } catch {
        throw new Error(`Invalid JSON from /test-bookings.json: ${raw.slice(0, 80)}…`);
      }
      if (!res.ok) {
        throw new Error(data.detail || res.statusText);
      }
      const bookings = data.bookings || [];
      renderOpsTable(bookings);

      const ids = new Set(bookings.map((b) => b.booking_id));
      if ($("opsNotify")?.checked && knownBookingIds.size > 0) {
        const fresh = bookings.filter((b) => !knownBookingIds.has(b.booking_id));
        if (fresh.length && "Notification" in window) {
          if (Notification.permission === "granted") {
            fresh.forEach((b) => {
              new Notification("E2E: new booking", {
                body: `${b.customer_phone} · ${b.puja_name} · ${b.status}`,
              });
            });
          } else if (Notification.permission !== "denied") {
            Notification.requestPermission();
          }
        }
      }
      knownBookingIds = ids;

      $("opsUpdated").textContent = `Updated ${new Date().toLocaleTimeString()} · ${bookings.length} row(s)`;
    } catch (err) {
      errEl.textContent = `Dashboard error: ${err.message}. Is DATABASE_URL in .env correct? Restart serve.py after .env changes.`;
      errEl.hidden = false;
      $("opsUpdated").textContent = "Refresh failed";
    }
  }

  function startOpsPoll() {
    stopOpsPoll();
    refreshOpsDashboard();
    if ($("opsAutoRefresh")?.checked) {
      opsPollTimer = setInterval(refreshOpsDashboard, 5000);
    }
  }

  function stopOpsPoll() {
    if (opsPollTimer) {
      clearInterval(opsPollTimer);
      opsPollTimer = null;
    }
  }

  $("btnOpsRefresh")?.addEventListener("click", () => refreshOpsDashboard());
  $("btnOpsConfirmPay")?.addEventListener("click", async () => {
    const bookingId = ($("opsRedispatchId")?.value || state.bookingId || "").trim();
    if (!bookingId) return log("Set booking ID (click id in Test ops table)", "log-err");
    try {
      await confirmPaymentTest(bookingId);
      refreshOpsDashboard();
    } catch (err) {
      log(`Confirm payment failed: ${err.message}`, "log-err");
    }
  });
  $("btnOpsRedispatch")?.addEventListener("click", async () => {
    const bookingId = ($("opsRedispatchId")?.value || state.bookingId || "").trim();
    if (!bookingId) return log("Set booking ID for re-dispatch (click id in Test ops table)", "log-err");
    try {
      log(`Re-dispatch booking=${bookingId} (sets partner presence + dispatch)`);
      let res = await fetch("/test-redispatch.json", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ booking_id: bookingId }),
      });
      let raw = await res.text();
      if (!res.ok || raw.trimStart().startsWith("<")) {
        log("POST redispatch unavailable — trying GET fallback", "log-err");
        res = await fetch(`/test-redispatch.json?booking_id=${encodeURIComponent(bookingId)}`);
        raw = await res.text();
      }
      if (raw.trimStart().startsWith("<")) {
        throw new Error("Restart serve.py (v3): powershell -File tests/e2e_ui/run_serve.ps1");
      }
      const data = JSON.parse(raw);
      log(`${res.status} ${JSON.stringify(data, null, 2)}`, res.ok ? "log-ok" : "log-err");
      if (res.ok && data.dispatch?.offers) {
        log(`Created ${data.dispatch.offers} offer(s). Partner: Heartbeat → GET /offers → Accept`, "log-ok");
        refreshOpsDashboard();
      } else if (res.ok && data.dispatch?.offers === 0) {
        log(
          "0 offers — run: python tests/e2e_ui/ensure_seed.py (pricing + availability), then Re-dispatch",
          "log-err"
        );
        refreshOpsDashboard();
      }
    } catch (err) {
      log(`Re-dispatch failed: ${err.message}`, "log-err");
    }
  });
  $("opsAutoRefresh")?.addEventListener("change", () => {
    if ($("tab-ops")?.classList.contains("active")) {
      startOpsPoll();
    }
  });

  function setRzKey(value) {
    const v = (value || "").trim();
    $("rzKey").value = v;
    if ($("rzKeyPay")) $("rzKeyPay").value = v;
    localStorage.setItem("e2e_rz_key", v);
    syncRzpPayButton();
  }

  function syncRzpPayButton() {
    const key = ($("rzKeyPay")?.value || $("rzKey").value).trim();
    if ($("rzKeyPay") && $("rzKeyPay").value !== $("rzKey").value) {
      $("rzKey").value = key;
    }
    $("btnRzpPay").disabled = !state.orderId || !key;
    const hint = $("rzPayHint");
    if (hint) {
      if (!key) {
        hint.textContent = "Enter rzp_test_… above (same as RAZORPAY_KEY_ID in .env) to enable Pay.";
      } else if (!state.orderId) {
        hint.textContent = "Create booking first (POST /bookings).";
      } else {
        hint.textContent = "Ready — click Razorpay Pay (do not use Mock if testing real checkout).";
        hint.className = "hint log-ok";
      }
    }
  }

  async function loadTestEnv() {
    try {
      const res = await fetch("/test-env.json");
      const data = await res.json();
      state.msg91Configured = data.msg91_configured === true;
      state.fast2smsConfigured = data.fast2sms_configured === true;
      state.msg91Enabled = data.msg91_enabled === true;
      state.totpEncConfigured = data.totp_enc_configured === true;
      state.smsProviderOrder = data.sms_provider_order || "fast2sms,msg91";
      updateOtpEnvHints();
      updateAdminEnvHints();
      if (data.razorpay_key_id && data.razorpay_key_id.startsWith("rzp_")) {
        setRzKey(data.razorpay_key_id);
        log("Loaded Razorpay Key ID from .env", "log-ok");
      }
    } catch (_) {
      if ($("otpEnvStatus")) {
        $("otpEnvStatus").textContent = "Could not load /test-env.json";
        $("otpEnvStatus").className = "hint log-err";
      }
    }
  }

  // Persist test Razorpay key in browser only (never commit).
  const savedKey = localStorage.getItem("e2e_rz_key");
  if (savedKey) setRzKey(savedKey);
  $("rzKey").addEventListener("input", () => setRzKey($("rzKey").value));
  if ($("rzKeyPay")) {
    $("rzKeyPay").addEventListener("input", () => setRzKey($("rzKeyPay").value));
  }
  loadTestEnv().then(() => syncRzpPayButton());

  fetch("/e2e-ui-version.json")
    .then((r) => r.json())
    .then((v) => {
      const el = $("e2eVersion");
      if (el) el.textContent = `v${v.version}`;
      log(`E2E UI v${v.version} (media upload uses API proxy)`, "log-ok");
    })
    .catch(() => {});

  applyE2eSlotDefaults();
  log("E2E test UI ready — Admin tab: TOTP + catalogue smoke (4B); OTP / SMS for customer/partner.", "log-ok");
})();
