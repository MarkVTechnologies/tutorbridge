from django.conf import settings
from django.db import models

from core.crypto import EncryptedTextField


class RequestStatus(models.TextChoices):
    SUBMITTED = "submitted", "Submitted"
    MATCHING = "matching", "Matching"
    SHORTLIST_READY = "shortlist_ready", "Shortlist ready"
    BOOKED = "booked", "Booked"
    CLOSED = "closed", "Closed"


class LessonRequest(models.Model):
    """REQ-02: what the parent needs."""

    parent = models.ForeignKey("parents.ParentProfile", on_delete=models.PROTECT, related_name="requests")
    child = models.ForeignKey("parents.Child", on_delete=models.PROTECT, related_name="requests")
    subjects = models.ManyToManyField("core.Subject")
    goals = models.TextField(blank=True)
    schedule = models.JSONField()  # [{"weekday": 0, "start": "16:00"}]
    lesson_minutes = models.PositiveSmallIntegerField(default=90)
    start_date = models.DateField()
    address = EncryptedTextField(blank=True)
    area = models.ForeignKey("core.Area", on_delete=models.PROTECT)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    budget_min_kobo = models.BigIntegerField(default=0)  # per hour
    budget_max_kobo = models.BigIntegerField(default=0)
    preferences = models.JSONField(default=dict, blank=True)  # {"gender": "female", "special_needs": true, "curriculum": "british"}
    requested_tutor = models.ForeignKey("tutors.TutorProfile", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    is_online = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=RequestStatus.choices, default=RequestStatus.SUBMITTED, db_index=True)
    assigned_officer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    sla_due_at = models.DateTimeField(null=True, blank=True)
    sla_alerted = models.BooleanField(default=False)
    shortlist_published_at = models.DateTimeField(null=True, blank=True)
    ops_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class MatchStatus(models.TextChoices):
    SUGGESTED = "suggested", "Suggested"
    INVITED = "invited", "Invited"
    ACCEPTED = "accepted", "Tutor accepted"
    DECLINED = "declined", "Tutor declined"
    BOOKED = "booked", "Booked"
    WITHDRAWN = "withdrawn", "Withdrawn"


class Match(models.Model):
    request = models.ForeignKey(LessonRequest, on_delete=models.CASCADE, related_name="matches")
    tutor = models.ForeignKey("tutors.TutorProfile", on_delete=models.CASCADE, related_name="matches")
    score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    breakdown = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=MatchStatus.choices, default=MatchStatus.SUGGESTED)
    in_shortlist = models.BooleanField(default=False)
    rank = models.PositiveSmallIntegerField(default=0)
    decline_reason = models.CharField(max_length=255, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("request", "tutor")]
        ordering = ["rank", "-score"]
