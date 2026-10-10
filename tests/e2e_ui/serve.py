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

# Load .env before any handler imports app.services (pricing.py needs DATABASE_URL etc.)
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

API_UPSTREAM = os.environ.get("E2E_API_UPSTREAM", "http://127.0.0.1:8000").rstrip("/")
PORT = int(os.environ.get("E2E_UI_PORT", "8765"))
E2E_UI_VERSION = "19"  # v19: Partner tab Setu PAN verify walkthrough


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
        if path == "/test-sprint1-quote.json":
            self._serve_test_sprint1_quote()
            return
        if path == "/test-sprint1-settlement.json":
            self._serve_test_sprint1_settlement()
            return
        if path == "/test-sprint1-refunds.json":
            self._serve_test_sprint1_refunds()
            return
        if path == "/test-sprint2-tds.json":
            self._serve_test_sprint2_tds()
            return
        if path == "/test-sprint2-turnover.json":
            self._serve_test_sprint2_turnover()
            return
        if path == "/test-sprint2-pan-gate.json":
            self._serve_test_sprint2_pan_gate()
            return
        if path == "/test-sprint2-settlement.json":
            self._serve_test_sprint2_settlement()
            return
        if path == "/test-sprint2-tds-config.json":
            self._serve_test_sprint2_tds_config()
            return
        if path == "/test-setu-pan-status.json":
            self._serve_test_setu_pan_status()
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
                    "/test-sprint1-quote.json",
                    "/test-sprint1-settlement.json",
                    "/test-sprint1-refunds.json",
                    "/test-sprint1-simulate-booking.json",
                    "/test-sprint2-tds.json",
                    "/test-sprint2-turnover.json",
                    "/test-sprint2-pan-gate.json",
                    "/test-sprint2-settlement.json",
                    "/test-sprint2-accrual.json",
                    "/test-sprint2-reversal.json",
                    "/test-sprint2-tds-config.json",
                    "/test-setu-pan-status.json",
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

    def _serve_test_sprint1_quote(self) -> None:
        """TEST ONLY — simulated Sprint 1 checkout quote (no API call)."""
        from decimal import Decimal
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(self.path).query)
        try:
            puja_price = Decimal((qs.get("puja_price") or ["2100"])[0])
            addon_total = Decimal((qs.get("addon_total") or ["0"])[0])
            fee_override = (qs.get("booking_fee") or [""])[0].strip()
            fee = Decimal(fee_override) if fee_override else None
        except Exception:
            self._serve_json({"detail": "Invalid puja_price or booking_fee"}, status=422)
            return
        try:
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from sprint1_settlement import sprint1_quote

            quote = sprint1_quote(
                puja_price=puja_price,
                addon_total=addon_total,
                booking_fee=fee,
            )
            self._serve_json({"quote": quote})
        except Exception as exc:
            self.log_message("test-sprint1-quote error: %s", exc)
            self._serve_json({"detail": str(exc)}, status=500)

    def _serve_test_sprint1_settlement(self) -> None:
        """TEST ONLY — settlement breakdown for a booking_id (DB read + Sprint 1 model)."""
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(self.path).query)
        booking_id = (qs.get("booking_id") or [""])[0].strip()
        if not booking_id:
            self._serve_json({"detail": "booking_id query param required"}, status=422)
            return
        try:
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from sprint1_settlement import booking_settlement_view
            from test_db import fetch_booking_by_id

            row = fetch_booking_by_id(booking_id)
            if row is None:
                self._serve_json(
                    {"detail": "Booking not found", "booking_id": booking_id}, status=404
                )
                return
            view = booking_settlement_view(row)
            self._serve_json(view)
        except Exception as exc:
            self.log_message("test-sprint1-settlement error: %s", exc)
            self._serve_json({"detail": str(exc)}, status=500)

    def _serve_test_sprint1_refunds(self) -> None:
        """TEST ONLY — tiered refund matrix for Sprint 1 booking_fee."""
        from decimal import Decimal
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(self.path).query)
        try:
            fee = Decimal((qs.get("booking_fee") or ["61"])[0])
        except Exception:
            self._serve_json({"detail": "Invalid booking_fee"}, status=422)
            return
        try:
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from sprint1_settlement import refund_matrix

            self._serve_json({"booking_fee": str(fee), "scenarios": refund_matrix(fee)})
        except Exception as exc:
            self.log_message("test-sprint1-refunds error: %s", exc)
            self._serve_json({"detail": str(exc)}, status=500)

    def _serve_test_sprint1_simulate_booking(self) -> None:
        """TEST ONLY — POST simulated Sprint 1 booking response (no API / DB write)."""
        import json
        import uuid
        from decimal import Decimal

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._serve_json({"detail": "Invalid JSON body"}, status=400)
            return
        try:
            puja_price = Decimal(str(body.get("puja_price", "2100")))
            fee = Decimal(str(body.get("booking_fee", "61")))
        except Exception:
            self._serve_json({"detail": "Invalid amounts"}, status=422)
            return
        try:
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from sprint1_settlement import sprint1_quote

            quote = sprint1_quote(puja_price=puja_price, booking_fee=fee)
            booking_id = str(uuid.uuid4())
            order_id = f"order_sim_{uuid.uuid4().hex[:12]}"
            self._serve_json(
                {
                    "simulated": True,
                    "booking_id": booking_id,
                    "razorpay_order_id": order_id,
                    "payment_mode": "booking_fee",
                    "booking_fee": quote["booking_fee"],
                    "booking_fee_label": quote["booking_fee_label"],
                    "total_amount": quote["total_amount"],
                    "amount_due_online": quote["amount_due_online"],
                    "amount_due_offline": quote["amount_due_offline"],
                    "razorpay_amount_paise": quote["razorpay_amount_paise"],
                    "note": (
                        "Simulated only — not written to DB. "
                        "Use advance_balance on Customer tab for live dispatch, "
                        "or inspect real bookings here after Sprint 1 ships."
                    ),
                },
                status=201,
            )
        except Exception as exc:
            self.log_message("test-sprint1-simulate-booking error: %s", exc)
            self._serve_json({"detail": str(exc)}, status=500)

    def _serve_test_sprint2_tds(self) -> None:
        """TEST ONLY — TDS calculator preview (no DB write)."""
        from decimal import Decimal
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(self.path).query)
        try:
            entity_type = (qs.get("entity_type") or ["individual"])[0] or None
            if entity_type == "null":
                entity_type = None
            pan_on_file = (qs.get("pan_on_file") or ["true"])[0].lower() in (
                "1",
                "true",
                "yes",
            )
            fy_gross = Decimal((qs.get("fy_gross_before") or ["0"])[0])
            txn = Decimal((qs.get("transaction_amount") or ["2100"])[0])
        except Exception:
            self._serve_json({"detail": "Invalid query params"}, status=422)
            return
        try:
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from sprint2_compliance import current_tds_config, tds_preview

            self._serve_json(
                {
                    "preview": tds_preview(
                        entity_type=entity_type,
                        pan_on_file=pan_on_file,
                        fy_gross_before=fy_gross,
                        transaction_amount=txn,
                    ),
                    "config": current_tds_config().to_json(),
                }
            )
        except Exception as exc:
            self.log_message("test-sprint2-tds error: %s", exc)
            self._serve_json({"detail": str(exc)}, status=500)

    def _serve_test_sprint2_turnover(self) -> None:
        """TEST ONLY — G2 FY fee turnover monitor."""
        from decimal import Decimal
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(self.path).query)
        use_db = (qs.get("from_db") or ["false"])[0].lower() in ("1", "true", "yes")
        try:
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from sprint2_compliance import turnover_preview

            if use_db:
                from test_db import fetch_fy_booking_fee_revenue

                revenue = Decimal(str(fetch_fy_booking_fee_revenue()))
            else:
                revenue = Decimal((qs.get("fy_fee_revenue") or ["0"])[0])
            self._serve_json({"turnover": turnover_preview(revenue), "from_db": use_db})
        except Exception as exc:
            self.log_message("test-sprint2-turnover error: %s", exc)
            self._serve_json({"detail": str(exc)}, status=500)

    def _serve_test_sprint2_pan_gate(self) -> None:
        """TEST ONLY — PAN accept-offer gate preview."""
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(self.path).query)
        pan_on_file = (qs.get("pan_on_file") or ["false"])[0].lower() in (
            "1",
            "true",
            "yes",
        )
        gate_enabled = (qs.get("gate_enabled") or ["true"])[0].lower() in (
            "1",
            "true",
            "yes",
        )
        try:
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from sprint2_compliance import pan_gate_preview

            self._serve_json(
                {
                    "gate": pan_gate_preview(
                        pan_on_file=pan_on_file,
                        gate_enabled=gate_enabled,
                    )
                }
            )
        except Exception as exc:
            self.log_message("test-sprint2-pan-gate error: %s", exc)
            self._serve_json({"detail": str(exc)}, status=500)

    def _serve_test_sprint2_tds_config(self) -> None:
        """TEST ONLY — read platform_settings.tds_facilitation (admin-tunable slabs)."""
        try:
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from sprint2_compliance import current_tds_config

            cfg = current_tds_config()
            self._serve_json({"config": cfg.to_json()})
        except Exception as exc:
            self.log_message("test-sprint2-tds-config error: %s", exc)
            self._serve_json({"detail": str(exc)}, status=500)

    def _serve_test_setu_pan_status(self) -> None:
        """TEST ONLY — whether API .env has Setu PAN product (no secret values)."""
        try:
            from dotenv import load_dotenv

            load_dotenv(ROOT / ".env")
            pid = (os.environ.get("KYC_SETU_PAN_PRODUCT_ID") or "").strip()
            base = (os.environ.get("KYC_SETU_BASE_URL") or "").strip()
            self._serve_json(
                {
                    "pan_product_configured": bool(pid),
                    "setu_base_url": base or None,
                    "hint": (
                        "Ready for live Setu PAN verify via Partner tab."
                        if pid
                        else "Set KYC_SETU_PAN_PRODUCT_ID in .env and restart uvicorn."
                    ),
                }
            )
        except Exception as exc:
            self.log_message("test-setu-pan-status error: %s", exc)
            self._serve_json({"detail": str(exc)}, status=500)

    def _serve_test_sprint2_settlement(self) -> None:
        """TEST ONLY — TDS settlement view for booking_id (DB read + simulation)."""
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(self.path).query)
        booking_id = (qs.get("booking_id") or [""])[0].strip()
        if not booking_id:
            self._serve_json({"detail": "booking_id query param required"}, status=422)
            return
        try:
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from sprint2_compliance import booking_tds_settlement_view
            from test_db import fetch_booking_by_id

            row = fetch_booking_by_id(booking_id)
            if row is None:
                self._serve_json(
                    {"detail": "Booking not found", "booking_id": booking_id}, status=404
                )
                return
            view = booking_tds_settlement_view(row)
            self._serve_json(view)
        except Exception as exc:
            self.log_message("test-sprint2-settlement error: %s", exc)
            self._serve_json({"detail": str(exc)}, status=500)

    def _serve_test_sprint2_accrual(self) -> None:
        """TEST ONLY — POST simulate TDS accrual at balance collection (no DB)."""
        import json
        import uuid
        from decimal import Decimal

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._serve_json({"detail": "Invalid JSON body"}, status=400)
            return
        try:
            entity_type = body.get("entity_type", "individual")
            if entity_type == "null":
                entity_type = None
            pan_on_file = bool(body.get("pan_on_file", True))
            gross = Decimal(str(body.get("gross_amount", "2100")))
            enabled = bool(body.get("tds_accrual_enabled", True))
            reset = bool(body.get("reset_ledger", False))
            booking_id = str(body.get("booking_id") or uuid.uuid4())
            pujari_id = str(body.get("pujari_id") or uuid.uuid4())
        except Exception:
            self._serve_json({"detail": "Invalid body fields"}, status=422)
            return
        try:
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from sprint2_compliance import simulate_accrual

            result = simulate_accrual(
                booking_id=booking_id,
                pujari_id=pujari_id,
                entity_type=entity_type,
                pan_on_file=pan_on_file,
                gross_amount=gross,
                tds_accrual_enabled=enabled,
                reset=reset,
            )
            self._serve_json({"simulated": True, **result})
        except ValueError as exc:
            self._serve_json({"detail": str(exc)}, status=422)
        except Exception as exc:
            self.log_message("test-sprint2-accrual error: %s", exc)
            self._serve_json({"detail": str(exc)}, status=500)

    def _serve_test_sprint2_reversal(self) -> None:
        """TEST ONLY — POST simulate TDS reversal on cancel (no DB)."""
        import json

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._serve_json({"detail": "Invalid JSON body"}, status=400)
            return
        booking_id = str(body.get("booking_id") or "").strip()
        pujari_id = str(body.get("pujari_id") or "").strip()
        if not booking_id or not pujari_id:
            self._serve_json({"detail": "booking_id and pujari_id required"}, status=422)
            return
        try:
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from sprint2_compliance import simulate_reversal

            result = simulate_reversal(booking_id=booking_id, pujari_id=pujari_id)
            self._serve_json({"simulated": True, **result})
        except Exception as exc:
            self.log_message("test-sprint2-reversal error: %s", exc)
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
        if path == "/test-sprint1-simulate-booking.json":
            self._serve_test_sprint1_simulate_booking()
            return
        if path == "/test-sprint2-accrual.json":
            self._serve_test_sprint2_accrual()
            return
        if path == "/test-sprint2-reversal.json":
            self._serve_test_sprint2_reversal()
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
