#!/usr/bin/env python3
"""
TEST ONLY — static E2E UI + CORS proxy to the real API.

Serves tests/e2e_ui/ on http://127.0.0.1:8765 and forwards /proxy/* to the API
so the browser can call localhost:8000 without changing app CORS settings.

Never import this module from app/ or deploy it.
"""
from __future__ import annotations

import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parents[1]
API_UPSTREAM = os.environ.get("E2E_API_UPSTREAM", "http://127.0.0.1:8000").rstrip("/")
PORT = int(os.environ.get("E2E_UI_PORT", "8765"))
E2E_UI_VERSION = "14"  # v14: ensure_seed prices all pujas; E2E slot/puja defaults


class E2EHandler(SimpleHTTPRequestHandler):
    """Static files + /proxy reverse proxy with permissive CORS (dev QA only)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[e2e-ui] " + (fmt % args) + "\n")

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Authorization, Content-Type, X-Razorpay-Signature",
        )

    def _path_only(self) -> str:
        return urlparse(self.path).path

    def _should_proxy(self) -> bool:
        p = self._path_only()
        return p.startswith("/proxy/") or p.startswith("/v1/")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def end_headers(self) -> None:
        p = self._path_only()
        if p.endswith((".js", ".html", ".css")):
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        super().end_headers()

    def do_GET(self) -> None:
        path = self._path_only()
        if path == "/test-env.json":
            self._serve_test_env()
            return
        if path == "/test-bookings.json":
            self._serve_test_bookings()
            return
        if path == "/test-user.json":
            self._serve_test_user()
            return
        if path == "/test-pujari.json":
            self._serve_test_pujari()
            return
        if path == "/test-confirm-payment.json":
            self._serve_test_confirm_payment_get()
            return
        if path == "/test-redispatch.json":
            self._serve_test_redispatch_get()
            return
        if path == "/test-fast2sms.json":
            self._serve_test_fast2sms_get()
            return
        if path == "/e2e-ui-version.json":
            self._serve_json({
                "version": E2E_UI_VERSION,
                "endpoints": [
                    "/test-env.json",
                    "/test-bookings.json",
                    "/test-user.json",
                    "/test-pujari.json",
                    "/test-confirm-payment.json",
                    "/test-redispatch.json",
                    "/test-fast2sms.json",
                ],
            })
            return
        if self._should_proxy():
            self._proxy("GET")
        else:
            super().do_GET()

    def _serve_test_env(self) -> None:
        """TEST ONLY — expose public Razorpay key from .env for the local UI."""
        import json

        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env")
        key_id = os.environ.get("RAZORPAY_KEY_ID", "")
        fast2sms_ok = bool(os.environ.get("FAST2SMS_API_KEY"))
        msg91_ok = (
            os.environ.get("MSG91_ENABLED", "").lower() in ("1", "true", "yes")
            and bool(os.environ.get("MSG91_AUTH_KEY") and os.environ.get("MSG91_TEMPLATE_ID"))
        )
        msg91_enabled = os.environ.get("MSG91_ENABLED", "").lower() in ("1", "true", "yes")
        totp_enc_ok = bool(os.environ.get("TOTP_ENC_KEYS", "").strip())
        payload = json.dumps({
            "razorpay_key_id": key_id,
            "msg91_configured": msg91_ok,
            "msg91_enabled": msg91_enabled,
            "fast2sms_configured": fast2sms_ok,
            "sms_configured": fast2sms_ok or msg91_ok,
            "sms_provider_order": os.environ.get("SMS_PROVIDER_ORDER", "fast2sms,msg91"),
            "totp_enc_configured": totp_enc_ok,
        }).encode()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _serve_json(self, obj: object, *, status: int = 200) -> None:
        import json

        payload = json.dumps(obj).encode()
        try:
            self.send_response(status)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (ConnectionAbortedError, BrokenPipeError):
            # Test ops auto-refresh cancels in-flight polls — harmless on Windows.
            pass

    def _serve_test_bookings(self) -> None:
        """TEST ONLY — read-only recent bookings from local DB for Test ops tab."""
        import json
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(self.path).query)
        try:
            limit = int((qs.get("limit") or ["50"])[0])
        except ValueError:
            limit = 50

        try:
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from test_db import fetch_recent_bookings

            bookings = fetch_recent_bookings(limit=limit)
            self._serve_json({"bookings": bookings, "count": len(bookings)})
        except Exception as exc:
            self.log_message("test-bookings error: %s", exc)
            self._serve_json({"detail": str(exc), "bookings": []}, status=500)

    def _serve_test_user(self) -> None:
        """TEST ONLY — phone → user_id + roles for Admin tab."""
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(self.path).query)
        phone = (qs.get("phone") or [""])[0].strip()
        if not phone:
            self._serve_json({"detail": "phone query param required"}, status=422)
            return
        try:
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from test_db import fetch_user_by_phone

            user = fetch_user_by_phone(phone)
            if user is None:
                self._serve_json({"detail": "User not found", "phone": phone}, status=404)
                return
            self._serve_json({"user": user})
        except Exception as exc:
            self.log_message("test-user error: %s", exc)
            self._serve_json({"detail": str(exc)}, status=500)

    def _serve_test_pujari(self) -> None:
        """TEST ONLY — partner phone → pujari_id for NO-DIRECT slot-hold test."""
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(self.path).query)
        phone = (qs.get("phone") or ["+910000000011"])[0].strip()
        try:
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from test_db import fetch_pujari_by_phone

            pujari = fetch_pujari_by_phone(phone)
            if pujari is None:
                self._serve_json(
                    {"detail": "Pujari not found — run ensure_seed.py", "phone": phone},
                    status=404,
                )
                return
            self._serve_json({"pujari": pujari})
        except Exception as exc:
            self.log_message("test-pujari error: %s", exc)
            self._serve_json({"detail": str(exc)}, status=500)

    def _serve_test_confirm_payment_get(self) -> None:
        """TEST ONLY — GET ?booking_id=… — signed payment.captured webhook."""
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(self.path).query)
        booking_id = (qs.get("booking_id") or [""])[0].strip()
        self._run_test_confirm_payment(booking_id)

    def _serve_test_confirm_payment(self) -> None:
        """TEST ONLY — POST {booking_id} — signed payment.captured webhook."""
        import json

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._serve_json({"detail": "Invalid JSON body"}, status=400)
            return
        booking_id = (body.get("booking_id") or "").strip()
        self._run_test_confirm_payment(booking_id)

    def _run_test_confirm_payment(self, booking_id: str) -> None:
        if not booking_id:
            self._serve_json({"detail": "booking_id required"}, status=422)
            return
        try:
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from test_payment import confirm_booking_payment

            result = confirm_booking_payment(booking_id)
            status = 200 if result.get("ok") else 502
            self._serve_json(result, status=status)
        except Exception as exc:
            self.log_message("test-confirm-payment error: %s", exc)
            self._serve_json({"ok": False, "detail": str(exc)}, status=500)

    def _serve_test_redispatch_get(self) -> None:
        """TEST ONLY — GET ?booking_id=… (same as POST body)."""
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(self.path).query)
        booking_id = (qs.get("booking_id") or [""])[0].strip()
        self._run_test_redispatch(booking_id)

    def _serve_test_redispatch(self) -> None:
        """TEST ONLY — POST {booking_id} — run dispatch round synchronously."""
        import json

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._serve_json({"detail": "Invalid JSON body"}, status=400)
            return
        booking_id = (body.get("booking_id") or "").strip()
        self._run_test_redispatch(booking_id)

    def _run_test_redispatch(self, booking_id: str) -> None:
        if not booking_id:
            self._serve_json({"detail": "booking_id required"}, status=422)
            return
        try:
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from test_db import redispatch_booking

            result = redispatch_booking(booking_id)
            self._serve_json({"status": "ok", "booking_id": booking_id, "dispatch": result})
        except Exception as exc:
            self.log_message("test-redispatch error: %s", exc)
            self._serve_json({"detail": str(exc)}, status=500)

    def _serve_test_fast2sms_get(self) -> None:
        """TEST ONLY — GET ?phone=… (same as POST body)."""
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(self.path).query)
        phone = (qs.get("phone") or [""])[0].strip()
        self._run_test_fast2sms(phone)

    def _serve_test_fast2sms(self) -> None:
        """TEST ONLY — POST {phone} — call FAST2SMS bulkV2 directly."""
        import json

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._serve_json({"detail": "Invalid JSON body"}, status=400)
            return
        phone = (body.get("phone") or "").strip()
        self._run_test_fast2sms(phone)

    def _run_test_fast2sms(self, phone: str) -> None:
        if not phone:
            self._serve_json({"detail": "phone required"}, status=422)
            return
        try:
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from test_fast2sms import send_direct_otp

            result = send_direct_otp(phone)
            status = 200 if result.get("ok") else 502
            self._serve_json(result, status=status)
        except Exception as exc:
            self.log_message("test-fast2sms error: %s", exc)
            self._serve_json({"ok": False, "detail": str(exc)}, status=500)

    def do_POST(self) -> None:
        path = self._path_only()
        if path == "/test-redispatch.json":
            self._serve_test_redispatch()
            return
        if path == "/test-fast2sms.json":
            self._serve_test_fast2sms()
            return
        if path == "/test-confirm-payment.json":
            self._serve_test_confirm_payment()
            return
        if self._should_proxy():
            self._proxy("POST")
        else:
            self.send_error(404)

    def do_PUT(self) -> None:
        if self._should_proxy():
            self._proxy("PUT")
        else:
            self.send_error(404)

    def do_PATCH(self) -> None:
        if self._should_proxy():
            self._proxy("PATCH")
        else:
            self.send_error(404)

    def do_DELETE(self) -> None:
        if self._should_proxy():
            self._proxy("DELETE")
        else:
            self.send_error(404)

    def _upstream_path(self) -> str:
        p = self._path_only()
        if p.startswith("/proxy"):
            return p[len("/proxy") :]
        return p

    def _proxy(self, method: str) -> None:
        upstream_path = self._upstream_path()
        parsed = urlparse(self.path)
        url = f"{API_UPSTREAM}{upstream_path}"
        if parsed.query:
            url = f"{url}?{parsed.query}"
        self.log_message("proxy %s -> %s", method, url)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else None

        headers = {}
        for key in ("Authorization", "Content-Type", "X-Razorpay-Signature"):
            if key in self.headers:
                headers[key] = self.headers[key]

        req = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(req, timeout=60) as resp:
                data = resp.read()
                self.send_response(resp.status)
                self._cors()
                ctype = resp.headers.get("Content-Type")
                if ctype:
                    self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except HTTPError as exc:
            data = exc.read()
            self.send_response(exc.code)
            self._cors()
            ctype = exc.headers.get("Content-Type", "application/json")
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except URLError as exc:
            msg = f'{{"detail":"Proxy error: {exc.reason}. Is uvicorn running on {API_UPSTREAM}?"}}'
            encoded = msg.encode()
            self.send_response(502)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)


def main() -> None:
    httpd = HTTPServer(("127.0.0.1", PORT), E2EHandler)
    print(f"E2E test UI v{E2E_UI_VERSION}: http://127.0.0.1:{PORT}")
    print(f"API upstream: {API_UPSTREAM}  (via /proxy/v1/…)")
    print(f"Test ops feed: http://127.0.0.1:{PORT}/test-bookings.json")
    print("If /test-bookings.json returns 404, stop ALL old serve.py processes first.")
    print("TEST ONLY — do not deploy. Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
