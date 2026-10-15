from django.conf import settings
from django.db import models


class AppendOnlyModel(models.Model):
    """Rows can be inserted but never updated or deleted (audit log, ledger)."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk is not None and not self._state.adding:
            raise RuntimeError(f"{type(self).__name__} is append-only")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError(f"{type(self).__name__} is append-only")


# --- Reference data (ADM-02: subjects, areas, levels) ---------------------


class Level(models.Model):
    code = models.SlugField(unique=True)  # nursery, primary, jss, sss, a_level, university
    name = models.CharField(max_length=60)
    order = models.PositiveSmallIntegerField(default=0)
    min_rate_kobo = models.BigIntegerField(default=0)  # TUT-05 rate band
    max_rate_kobo = models.BigIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name


class Curriculum(models.Model):
    code = models.SlugField(unique=True)
    name = models.CharField(max_length=60)

    def __str__(self):
        return self.name


class Subject(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class State(models.Model):
    name = models.CharField(max_length=60, unique=True)

    def __str__(self):
        return self.name


class LGA(models.Model):
    state = models.ForeignKey(State, on_delete=models.PROTECT, related_name="lgas")
    name = models.CharField(max_length=80)

    class Meta:
        unique_together = [("state", "name")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Area(models.Model):
    """Neighbourhood, with a centre point used for distance scoring."""

    lga = models.ForeignKey(LGA, on_delete=models.PROTECT, related_name="areas")
    name = models.CharField(max_length=80)
    slug = models.SlugField(unique=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


# --- Configuration & operations -------------------------------------------


class Setting(models.Model):
    """Key-value configuration for fees, policies and feature flags."""

    key = models.CharField(max_length=80, unique=True)
    value = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return self.key


class AuditLog(AppendOnlyModel):
    """ADM-04: immutable record of staff actions and money movements."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=80, db_index=True)
    entity_type = models.CharField(max_length=60, db_index=True)
    entity_id = models.CharField(max_length=40, db_index=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class Job(models.Model):
    """Database-backed job queue, processed by cron every minute."""

    PENDING, RUNNING, DONE, FAILED = "pending", "running", "done", "failed"
    STATUS_CHOICES = [(s, s) for s in (PENDING, RUNNING, DONE, FAILED)]

    kind = models.CharField(max_length=60, db_index=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    run_after = models.DateTimeField(db_index=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)


class CronHeartbeat(models.Model):
    """One row per scheduled task: lock against overlapping runs + heartbeat for monitoring."""

    name = models.CharField(max_length=60, unique=True)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_started_at = models.DateTimeField(null=True, blank=True)
    last_finished_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
