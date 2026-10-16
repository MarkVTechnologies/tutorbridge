"""
Long-running scheduler for hosts without cron (Railway, Docker): runs the same task
groups as the cPanel crontab in `cron.py`, in-process, on the same schedule (Lagos time).

  python manage.py run_scheduler

`cron` keeps its own database locks, so running this next to a real crontab is safe.
"""
import logging
import time

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

log = logging.getLogger(__name__)


def due(now):
    """Task groups due at this (local) minute — mirrors the crontab in cron.py."""
    tasks = ["minute"]
    if now.minute % 5 == 0:
        tasks.append("five")
    if now.minute == 0:
        tasks.append("hourly")
        if now.hour == 2:
            tasks.append("daily")
        if now.hour == 18 and now.weekday() == 3:
            tasks.append("weekly")
        if now.hour == 3 and now.day == 1:
            tasks.append("monthly")
    return tasks


class Command(BaseCommand):
    help = "Run scheduled tasks forever (for hosts without cron)"

    def handle(self, **opts):
        self.stdout.write("Scheduler started")
        last = None
        while True:
            now = timezone.localtime().replace(second=0, microsecond=0)
            if now != last:
                last = now
                for task in due(now):
                    try:
                        call_command("cron", task)
                    except Exception:  # noqa: BLE001 - one failing group must not stop the scheduler
                        log.exception("Scheduled task %s failed", task)
            time.sleep(5)
