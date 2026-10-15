"""
Scheduled tasks (section 13.4). Configure in cPanel → Cron Jobs, e.g.:

  * * * * *    cd ~/tutorbridge/server && ~/virtualenv/.../bin/python manage.py cron minute
  */5 * * * *  ... manage.py cron five
  0 * * * *    ... manage.py cron hourly
  0 2 * * *    ... manage.py cron daily
  0 18 * * 4   ... manage.py cron weekly
  0 3 1 * *    ... manage.py cron monthly

Each schedule holds a database lock row so overlapping runs never process the
same work twice, and records a heartbeat that /api/health/ reports on.
"""
import logging
from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.jobs import cron_lock, process_pending

log = logging.getLogger(__name__)


def minute():
    process_pending()


def five():
    from bookings import services as b

    b.expire_offers()
    b.expire_unpaid()
    b.send_reminders()
    b.detect_late_and_no_shows()
    _request_sla_alerts()


def hourly():
    from bookings.services import auto_confirm

    auto_confirm()


def daily():
    from payments.services import reconcile
    from trust.services import nightly_reputation

    reconcile()
    nightly_reputation()
    call_command("clearsessions")
    _expire_background_checks()
    _purge_rejected_documents()


def weekly():
    from payments.services import create_payout_batch

    create_payout_batch(user=None)  # Finance approves on Friday (maker-checker)


def monthly():
    _reverification_reminders()
    _monthly_review_reminders()


TASKS = {"minute": minute, "five": five, "hourly": hourly, "daily": daily, "weekly": weekly, "monthly": monthly}


def _request_sla_alerts():
    """REQ-08: alert ops when a request is unmatched past its SLA."""
    from accounts.models import Role, User
    from matching.models import LessonRequest, RequestStatus
    from messaging.notify import notify

    overdue = LessonRequest.objects.filter(status__in=[RequestStatus.SUBMITTED, RequestStatus.MATCHING], sla_due_at__lt=timezone.now(), sla_alerted=False)
    for r in overdue:
        for u in User.objects.filter(role=Role.OPS, is_active=True):
            notify(u, "finance_alert", {"title": f"Request #{r.pk} is past its 24h SLA", "detail": f"{r.child.first_name}, {r.area.name}"}, force_channels=("inapp", "email"))
        r.sla_alerted = True
        r.save(update_fields=["sla_alerted"])


def _expire_background_checks():
    """TUT-16: suspend tutors whose background check has expired."""
    from tutors.models import TutorProfile, TutorStatus
    from tutors.services import set_status

    for t in TutorProfile.objects.filter(status=TutorStatus.ACTIVE, background_valid_until__lt=timezone.localdate()):
        set_status(t, TutorStatus.APPROVED, None, "Background check expired — re-verification required")


def _purge_rejected_documents():
    """NDPA retention: rejected tutors' documents are deleted after 6 months."""
    from tutors.models import TutorStatus
    from vetting.models import Document
    from vetting.storage import delete_file

    cutoff = timezone.now() - timedelta(days=183)
    docs = Document.objects.filter(owner__tutor_profile__status=TutorStatus.REJECTED, owner__tutor_profile__status_history__created_at__lt=cutoff,
                                   owner__tutor_profile__status_history__to_status=TutorStatus.REJECTED).distinct()
    for d in docs:
        delete_file(d)
        d.delete()


def _reverification_reminders():
    from messaging.notify import notify
    from tutors.models import TutorProfile, TutorStatus

    soon = timezone.localdate() + timedelta(days=30)
    for t in TutorProfile.objects.filter(status=TutorStatus.ACTIVE, background_valid_until__lte=soon).select_related("user"):
        notify(t.user, "reverification_due", {"due": t.background_valid_until.strftime("%d %b %Y")})


def _monthly_review_reminders():
    from bookings.models import Booking, BookingStatus
    from messaging.notify import notify

    for b in Booking.objects.filter(status=BookingStatus.ACTIVE).select_related("parent__user", "tutor__user"):
        notify(b.parent.user, "review_reminder", {"tutor_name": b.tutor.user.display_name}, link=f"/parent/bookings/{b.pk}")


class Command(BaseCommand):
    help = "Run a scheduled task group: " + ", ".join(TASKS)

    def add_arguments(self, parser):
        parser.add_argument("task", choices=list(TASKS))

    def handle(self, task, **opts):
        name = "process_jobs" if task == "minute" else f"cron_{task}"
        with cron_lock(name, ttl_minutes=55 if task in ("hourly", "daily", "weekly", "monthly") else 4) as acquired:
            if not acquired:
                self.stdout.write(f"{task}: another run holds the lock; skipping")
                return
            TASKS[task]()
        self.stdout.write(f"{task}: done")
