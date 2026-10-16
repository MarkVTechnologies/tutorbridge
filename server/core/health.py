"""
Operational health checks (section 16): used by the daily admin email, the
staff dashboard panel and the public /api/health/ probe.
"""
import shutil
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from core.models import CronHeartbeat, Job

# Each scheduled task must have finished within this window, or it's flagged.
CRON_MAX_AGE = {
    "process_jobs": timedelta(minutes=10),
    "cron_five": timedelta(minutes=20),
    "cron_hourly": timedelta(hours=2),
    "cron_daily": timedelta(hours=26),
}


def checks():
    """List of {key, label, ok, detail}. Never raises: a broken check reports itself as failing."""
    out = []

    def add(key, label, fn):
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001 - surface, don't crash the report
            ok, detail = False, f"Check failed: {e}"
        out.append({"key": key, "label": label, "ok": bool(ok), "detail": detail})

    now = timezone.now()

    def cron():
        stale = []
        beats = {h.name: h for h in CronHeartbeat.objects.all()}
        for name, max_age in CRON_MAX_AGE.items():
            h = beats.get(name)
            if not h or not h.last_finished_at or now - h.last_finished_at > max_age:
                stale.append(name)
            elif h.last_error:
                stale.append(f"{name} (last run errored)")
        return not stale, "All scheduled tasks ran on time." if not stale else "Late or failing: " + ", ".join(stale)

    def jobs():
        failed = Job.objects.filter(status=Job.FAILED, finished_at__gte=now - timedelta(days=1)).count()
        backlog = Job.objects.filter(status=Job.PENDING, run_after__lt=now - timedelta(minutes=10)).count()
        return failed == 0 and backlog == 0, f"{failed} failed in 24h, {backlog} waiting over 10 min"

    def ledger_balanced():
        from payments import ledger

        d, c = ledger.trial_balance()
        return d == c, "Debits equal credits." if d == c else f"OUT OF BALANCE: debits {d} vs credits {c}"

    def reconciliation():
        from payments.models import ReconciliationRun

        run = ReconciliationRun.objects.order_by("-created_at").first()
        if run is None:
            return False, "Never run."
        problems = [m for m in run.mismatches if "credited by reconciliation" not in m.get("issue", "")]
        fresh = now - run.created_at < timedelta(hours=30)
        return fresh and not problems, f"Last run {timezone.localtime(run.created_at):%d %b %H:%M}: {len(problems)} problem(s)" + ("" if fresh else " (stale)")

    def incidents():
        from trust.models import Incident

        late = Incident.objects.filter(acknowledged_at__isnull=True, created_at__lt=now - timedelta(hours=1)).exclude(status="resolved").count()
        return late == 0, f"{late} safety report(s) unacknowledged for over an hour" if late else "Every safety report acknowledged."

    def requests_sla():
        from matching.models import LessonRequest, RequestStatus

        late = LessonRequest.objects.filter(status__in=[RequestStatus.SUBMITTED, RequestStatus.MATCHING], sla_due_at__lt=now).count()
        return late == 0, f"{late} request(s) past the 24h shortlist target" if late else "All requests within target."

    def payouts():
        from payments.models import Payout, PayoutItem

        drafts = Payout.objects.filter(status=Payout.Status.DRAFT, created_at__lt=now - timedelta(days=2)).count()
        failed = PayoutItem.objects.filter(status=PayoutItem.Status.FAILED).count()
        return drafts == 0 and failed == 0, f"{drafts} batch(es) awaiting approval for 2+ days, {failed} failed transfer(s)"

    def disk():
        usage = shutil.disk_usage(settings.BASE_DIR)
        free_pct = usage.free / usage.total * 100
        return free_pct >= 15, f"{usage.free / 1e9:.1f} GB free ({free_pct:.0f}%)"

    add("cron", "Scheduled tasks", cron)
    add("jobs", "Email/SMS job queue", jobs)
    add("ledger", "Ledger balanced", ledger_balanced)
    add("reconciliation", "Payment reconciliation", reconciliation)
    add("incidents", "Safety reports", incidents)
    add("requests", "Matching SLA", requests_sla)
    add("payouts", "Payouts", payouts)
    add("disk", "Server disk space", disk)
    return out


def send_daily_report():
    """Email super admins a summary; problems first."""
    from accounts.models import Role, User
    from messaging.notify import notify

    results = checks()
    problems = [r for r in results if not r["ok"]]
    lines = [("✗ " if not r["ok"] else "✓ ") + f"{r['label']}: {r['detail']}" for r in sorted(results, key=lambda r: r["ok"])]
    title = f"{len(problems)} issue(s) need attention" if problems else "All systems healthy"
    for admin in User.objects.filter(Q(role=Role.SUPER), is_active=True):
        notify(admin, "health_report", {"title": title, "detail": "\n".join(lines)}, force_channels=("email",))
    return results
