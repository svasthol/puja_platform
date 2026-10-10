"""QA Phase 2: worker registration + live idempotent invocation of maintenance tasks."""
from __future__ import annotations

import sys
import traceback

EXPECTED = [
    "app.workers.advance_offers.refresh_advance_offers_task",
    "app.workers.dispatch.broadcast_booking",
    "app.workers.dispatch.direct_dispatch",
    "app.workers.dispatch.rebroadcast_booking",
    "app.workers.kyc.expire_kyc_requests_task",
    "app.workers.notifications.alert_refund_failed",
    "app.workers.notifications.notify_accept_ack",
    "app.workers.notifications.notify_no_pujari",
    "app.workers.notifications.notify_offer_instant",
    "app.workers.notifications.notify_offer_withdrawn",
    "app.workers.notifications.notify_offers",
    "app.workers.notifications.notify_reconfirm_escalation",
    "app.workers.notifications.notify_reconfirm_ping",
    "app.workers.notifications.notify_rm_dispatch_escalation",
    "app.workers.panchangam.refresh_panchangam_cache_task",
    "app.workers.refund.process_refunds",
    "app.workers.rm_escalation.rm_escalation_scan_task",
    "app.workers.sweep.sweep_task",
    "app.workers.tds_accrual.process_tds_accrual_intents",
    "app.workers.tds_accrual.sweep_never_collected_tds",
    "app.workers.urgency_flip.escalate_urgency_on_threshold_task",
]


def check_registration() -> None:
    from app.workers.celery_app import celery_app

    names = set(celery_app.tasks.keys())
    print("== REGISTRATION ==")
    missing = [t for t in EXPECTED if t not in names]
    for t in EXPECTED:
        print(f"  {'OK ' if t in names else 'MISSING'} {t}")
    print(f"registered_total={len(names)} expected={len(EXPECTED)} missing={missing}")

    print("\n== BEAT SCHEDULE ==")
    for key, cfg in celery_app.conf.beat_schedule.items():
        print(f"  {key}: task={cfg['task']} every={cfg['schedule']}s")


def _run(label, fn, *args):
    import io
    import contextlib

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            out = fn(*args)
        print(f"  {label}: OK -> {out!r}")
        return out
    except Exception as e:  # noqa: BLE001
        print(f"  {label}: ERROR {type(e).__name__}: {str(e).splitlines()[0]}")
        return ("ERR", e)


def invoke_maintenance() -> None:
    from app.workers.sweep import get_connection, run_sweep
    from app.workers.advance_offers import refresh_advance_offers
    from app.workers.urgency_flip import escalate_urgency_on_threshold
    from app.workers.rm_escalation import scan_rm_escalations
    from app.workers.kyc import expire_kyc_requests, run_kyc_maintenance
    from app.workers.reconfirmation import process_reconfirm_pings, process_reconfirm_escalations
    from app.workers.no_show import flag_stuck_confirmed_bookings
    from app.workers.redis_sync import get_sync_redis

    print("\n== LIVE IDEMPOTENT INVOCATION (run x2) ==")

    conn = get_connection()
    try:
        redis_client = get_sync_redis()
    except Exception as e:  # noqa: BLE001
        redis_client = None
        print(f"  (redis client error: {e})")

    print("[sweep.run_sweep]")
    _run("run#1", run_sweep, conn, redis_client)
    _run("run#2", run_sweep, conn, redis_client)

    print("[advance_offers.refresh_advance_offers]")
    _run("run#1", refresh_advance_offers, conn)
    _run("run#2", refresh_advance_offers, conn)

    print("[urgency_flip.escalate_urgency_on_threshold]")
    _run("run#1", escalate_urgency_on_threshold, conn)
    _run("run#2", escalate_urgency_on_threshold, conn)

    print("[rm_escalation.scan_rm_escalations]")
    _run("run#1", scan_rm_escalations, conn)
    _run("run#2", scan_rm_escalations, conn)

    print("[kyc.expire_kyc_requests]")
    _run("run#1", expire_kyc_requests, conn)
    _run("run#2", expire_kyc_requests, conn)

    print("[kyc.run_kyc_maintenance]")
    _run("run#1", run_kyc_maintenance, conn, 30)

    print("[reconfirmation.process_reconfirm_pings]")
    _run("run#1", process_reconfirm_pings, conn)
    _run("run#2", process_reconfirm_pings, conn)

    print("[reconfirmation.process_reconfirm_escalations]")
    _run("run#1", process_reconfirm_escalations, conn)

    print("[no_show.flag_stuck_confirmed_bookings]")
    _run("run#1", flag_stuck_confirmed_bookings, conn)

    try:
        conn.close()
    except Exception:
        pass


def invoke_refund_tds_panchangam() -> None:
    print("\n== REFUND / TDS / PANCHANGAM TASKS ==")
    from app.workers.refund import process_refunds
    from app.workers.tds_accrual import process_tds_accrual_intents, sweep_never_collected_tds
    _run("refund.process_refunds(batch=3)", process_refunds, 3)
    _run("tds.process_tds_accrual_intents(batch=5)", process_tds_accrual_intents, 5)
    _run("tds.sweep_never_collected_tds(batch=5)", sweep_never_collected_tds, 5)

    from app.workers.sweep import get_connection
    from app.workers.panchangam import refresh_panchangam_cache
    conn = get_connection()
    _run("panchangam.refresh_panchangam_cache", refresh_panchangam_cache, conn)
    conn.close()


if __name__ == "__main__":
    try:
        check_registration()
        invoke_maintenance()
        invoke_refund_tds_panchangam()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
