from django.conf import settings
from django.db import models


class Review(models.Model):
    """REV-01/02: parent→tutor (public) and tutor→parent (private, staff + aggregate only)."""

    DIRECTIONS = [("parent_to_tutor", "Parent rates tutor"), ("tutor_to_parent", "Tutor rates parent")]
    booking = models.ForeignKey("bookings.Booking", on_delete=models.CASCADE, related_name="reviews")
    direction = models.CharField(max_length=20, choices=DIRECTIONS)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reviews_written")
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True)
    period = models.CharField(max_length=10)  # "trial" or "YYYY-MM" — one review per booking per period
    is_hidden = models.BooleanField(default=False)
    hidden_reason = models.CharField(max_length=255, blank=True)
    hidden_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("booking", "direction", "period")]
        ordering = ["-created_at"]


class DisputeStatus(models.TextChoices):
    OPEN = "open", "Open"
    INVESTIGATING = "investigating", "Investigating"
    RESOLVED = "resolved", "Resolved"


class Dispute(models.Model):
    """SAF-01/02: raised on a lesson within the dispute window; freezes that lesson's payout."""

    RESOLUTIONS = [("refund", "Full refund"), ("partial", "Partial refund"), ("reject", "Rejected — tutor paid")]
    lesson = models.OneToOneField("bookings.Lesson", on_delete=models.PROTECT, related_name="dispute")
    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    reason = models.CharField(max_length=40)
    description = models.TextField()
    evidence = models.ManyToManyField("vetting.Document", blank=True)
    status = models.CharField(max_length=15, choices=DisputeStatus.choices, default=DisputeStatus.OPEN, db_index=True)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    resolution = models.CharField(max_length=10, choices=RESOLUTIONS, blank=True)
    refund_kobo = models.BigIntegerField(default=0)
    notes = models.TextField(blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Incident(models.Model):
    """SAF-03: urgent safety reports."""

    SEVERITIES = [("urgent", "Urgent"), ("high", "High"), ("medium", "Medium"), ("low", "Low")]
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="incidents_reported")
    subject_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="incidents_about")
    lesson = models.ForeignKey("bookings.Lesson", null=True, blank=True, on_delete=models.SET_NULL)
    booking = models.ForeignKey("bookings.Booking", null=True, blank=True, on_delete=models.SET_NULL)
    severity = models.CharField(max_length=10, choices=SEVERITIES, default="urgent")
    description = models.TextField()
    status = models.CharField(max_length=15, choices=DisputeStatus.choices, default=DisputeStatus.OPEN, db_index=True)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    actions_taken = models.TextField(blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Strike(models.Model):
    """SAF-05: strikes for no-shows and policy breaches; three trigger review."""

    tutor = models.ForeignKey("tutors.TutorProfile", on_delete=models.CASCADE, related_name="strike_records")
    reason = models.CharField(max_length=40)  # no_show, late_cancel, policy_breach, contact_sharing
    lesson = models.ForeignKey("bookings.Lesson", null=True, blank=True, on_delete=models.SET_NULL)
    notes = models.TextField(blank=True)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
