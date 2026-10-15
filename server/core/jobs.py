"""
Database-backed background job queue (section 13.4).

Enqueue with `enqueue("send_email", {...})`; the `process_jobs` management
command (cron, every minute) claims and runs pending jobs. Claiming uses a
conditional UPDATE so overlapping cron runs never process the same job twice.
"""
import logging
import traceback
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.models import CronHeartbeat, Job

log = logging.getLogger(__name__)
HANDLERS = {}


def job_handler(kind):
    def register(fn):
        HANDLERS[kind] = fn
        return fn

    return register


def enqueue(kind, payload=None, delay_seconds=0, max_attempts=5):
    def _create():
        Job.objects.create(
            kind=kind,
            payload=payload or {},
            run_after=timezone.now() + timedelta(seconds=delay_seconds),
            max_attempts=max_attempts,
        )

    # Only enqueue once the surrounding transaction commits, so jobs never reference rolled-back rows.
    transaction.on_commit(_create)


def _claim(job):
    return (
        Job.objects.filter(pk=job.pk, status=Job.PENDING)
        .update(status=Job.RUNNING, locked_at=timezone.now(), attempts=job.attempts + 1)
        == 1
    )


def process_pending(limit=100):
    _load_handlers()
    now = timezone.now()
    # Recover jobs stuck in RUNNING (worker died) after 10 minutes.
    Job.objects.filter(status=Job.RUNNING, locked_at__lt=now - timedelta(minutes=10)).update(status=Job.PENDING)
    processed = 0
    for job in Job.objects.filter(status=Job.PENDING, run_after__lte=now).order_by("run_after")[:limit]:
        if not _claim(job):
            continue
        job.refresh_from_db()
        handler = HANDLERS.get(job.kind)
        try:
            if handler is None:
                raise LookupError(f"No handler for job kind {job.kind}")
            handler(**job.payload)
            job.status, job.finished_at, job.last_error = Job.DONE, timezone.now(), ""
        except Exception:  # noqa: BLE001 - every failure is recorded and retried
            job.last_error = traceback.format_exc()[-4000:]
            if job.attempts >= job.max_attempts:
                job.status = Job.FAILED
                log.error("Job %s (%s) failed permanently", job.pk, job.kind)
            else:
                job.status = Job.PENDING
                job.run_after = timezone.now() + timedelta(minutes=2 ** job.attempts)
        job.save(update_fields=["status", "finished_at", "last_error", "run_after"])
        processed += 1
    return processed


def _load_handlers():
    # Import modules that register handlers.
    import messaging.notify  # noqa: F401


class cron_lock:
    """Context manager: run a scheduled task only if no other run holds the lock."""

    def __init__(self, name, ttl_minutes=30):
        self.name, self.ttl, self.acquired = name, timedelta(minutes=ttl_minutes), False

    def __enter__(self):
        now = timezone.now()
        CronHeartbeat.objects.get_or_create(name=self.name)
        from django.db.models import Q

        self.acquired = (
            CronHeartbeat.objects.filter(name=self.name)
            .filter(Q(locked_until__isnull=True) | Q(locked_until__lt=now))
            .update(locked_until=now + self.ttl, last_started_at=now)
            == 1
        )
        return self.acquired

    def __exit__(self, exc_type, exc, tb):
        if self.acquired:
            CronHeartbeat.objects.filter(name=self.name).update(
                locked_until=None,
                last_finished_at=timezone.now(),
                last_error="" if exc is None else "".join(traceback.format_exception(exc_type, exc, tb))[-4000:],
            )
        return False
