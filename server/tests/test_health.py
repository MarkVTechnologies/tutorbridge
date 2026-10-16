"""Monitoring: health checks, daily admin email, staff panel."""
from datetime import timedelta

from django.core import mail
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role
from core.health import checks, send_daily_report
from core.models import CronHeartbeat, Job
from messaging.models import Notification
from tests.factories import make_parent, make_staff, seed, staff_client


class HealthTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def _by_key(self):
        return {c["key"]: c for c in checks()}

    def test_fresh_system_flags_missing_cron_and_reconciliation(self):
        r = self._by_key()
        self.assertFalse(r["cron"]["ok"])
        self.assertFalse(r["reconciliation"]["ok"])
        self.assertTrue(r["ledger"]["ok"])
        self.assertTrue(r["disk"]["ok"] in (True, False))

    def test_healthy_after_crons_run(self):
        from io import StringIO

        from django.core.management import call_command

        for task in ("minute", "five", "hourly", "daily"):
            call_command("cron", task, stdout=StringIO())
        r = self._by_key()
        self.assertTrue(r["cron"]["ok"], r["cron"])
        self.assertTrue(r["reconciliation"]["ok"], r["reconciliation"])
        self.assertTrue(r["jobs"]["ok"], r["jobs"])

    def test_stale_or_erroring_cron_flagged(self):
        now = timezone.now()
        for name in ("process_jobs", "cron_five", "cron_hourly", "cron_daily"):
            CronHeartbeat.objects.create(name=name, last_finished_at=now)
        CronHeartbeat.objects.filter(name="cron_hourly").update(last_finished_at=now - timedelta(hours=3))
        CronHeartbeat.objects.filter(name="cron_daily").update(last_error="Traceback...")
        detail = self._by_key()["cron"]["detail"]
        self.assertIn("cron_hourly", detail)
        self.assertIn("cron_daily (last run errored)", detail)

    def test_failed_jobs_and_unacknowledged_incidents(self):
        Job.objects.create(kind="send_sms", status=Job.FAILED, run_after=timezone.now(), finished_at=timezone.now())
        from trust.models import Incident

        parent, _ = make_parent()
        i = Incident.objects.create(reporter=parent.user, description="x")
        Incident.objects.filter(pk=i.pk).update(created_at=timezone.now() - timedelta(hours=2))
        r = self._by_key()
        self.assertFalse(r["jobs"]["ok"])
        self.assertFalse(r["incidents"]["ok"])

    def test_daily_report_emails_super_admins_only(self):
        admin = make_staff(Role.SUPER)
        ops = make_staff(Role.OPS)
        send_daily_report()
        n = Notification.objects.get(user=admin, event="health_report")
        self.assertIn("issue(s) need attention", n.subject)
        self.assertTrue(n.body.startswith("✗ "))  # problems listed first
        self.assertFalse(Notification.objects.filter(user=ops, event="health_report").exists())
        self.assertEqual(len(mail.outbox), 0)  # queued for the job runner, not sent inline

    def test_staff_health_endpoint(self):
        self.assertEqual(len(staff_client(APIClient(), make_staff(Role.SUPER)).get("/api/staff/health/").json()), 8)
        self.assertEqual(staff_client(APIClient(), make_staff(Role.OPS)).get("/api/staff/health/").status_code, 403)
