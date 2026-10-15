from django.conf import settings
from django.db import models


class TutorStatus(models.TextChoices):
    APPLIED = "applied", "Applied"
    UNDER_REVIEW = "under_review", "Under review"
    INTERVIEW = "interview", "Interview"
    APPROVED = "approved", "Approved"
    ACTIVE = "active", "Active"
    REJECTED = "rejected", "Rejected"
    SUSPENDED = "suspended", "Suspended"
    BANNED = "banned", "Banned"


class Tier(models.TextChoices):
    VERIFIED = "verified", "Verified"
    GOLD = "gold", "Gold"
    ELITE = "elite", "Elite"


class TutorProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tutor_profile")
    status = models.CharField(max_length=20, choices=TutorStatus.choices, default=TutorStatus.APPLIED, db_index=True)
    headline = models.CharField(max_length=120, blank=True)
    bio = models.TextField(blank=True)
    photo = models.ForeignKey("vetting.Document", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    highest_qualification = models.CharField(max_length=120, blank=True)
    years_experience = models.PositiveSmallIntegerField(default=0)
    trcn_number = models.CharField(max_length=40, blank=True)
    curricula = models.ManyToManyField("core.Curriculum", blank=True)
    hourly_rate_kobo = models.BigIntegerField(default=0)
    home_area = models.ForeignKey("core.Area", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    max_travel_km = models.PositiveSmallIntegerField(default=10)
    accepts_special_needs = models.BooleanField(default=False)
    offers_online = models.BooleanField(default=False)
    # Reputation (computed by nightly job)
    tier = models.CharField(max_length=10, choices=Tier.choices, default=Tier.VERIFIED)
    rating_avg = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    rating_count = models.PositiveIntegerField(default=0)
    reliability_score = models.PositiveSmallIntegerField(default=100)  # 0..100
    hours_taught = models.DecimalField(max_digits=8, decimal_places=1, default=0)
    lessons_completed = models.PositiveIntegerField(default=0)
    strikes = models.PositiveSmallIntegerField(default=0)
    # Agreements & safeguarding (TUT-12)
    safeguarding_completed_at = models.DateTimeField(null=True, blank=True)
    agreement_signed_at = models.DateTimeField(null=True, blank=True)
    agreement_signature = models.CharField(max_length=120, blank=True)
    agreement_version = models.CharField(max_length=20, blank=True)
    location_consent = models.BooleanField(default=False)
    # Lifecycle
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    background_valid_until = models.DateField(null=True, blank=True)
    reverify_due = models.DateField(null=True, blank=True)  # TUT-16
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Tutor {self.user.get_full_name()} ({self.status})"

    @property
    def is_searchable(self):
        return self.status == TutorStatus.ACTIVE


class TutorSubject(models.Model):
    """TUT-02: subjects × levels matrix with curriculum and test result."""

    tutor = models.ForeignKey(TutorProfile, on_delete=models.CASCADE, related_name="subjects")
    subject = models.ForeignKey("core.Subject", on_delete=models.PROTECT)
    level = models.ForeignKey("core.Level", on_delete=models.PROTECT)
    test_score = models.PositiveSmallIntegerField(null=True, blank=True)
    verified = models.BooleanField(default=False)

    class Meta:
        unique_together = [("tutor", "subject", "level")]


class TutorArea(models.Model):
    tutor = models.ForeignKey(TutorProfile, on_delete=models.CASCADE, related_name="areas")
    area = models.ForeignKey("core.Area", on_delete=models.PROTECT)

    class Meta:
        unique_together = [("tutor", "area")]


class AvailabilitySlot(models.Model):
    """TUT-04: weekly availability grid. weekday 0=Monday."""

    tutor = models.ForeignKey(TutorProfile, on_delete=models.CASCADE, related_name="availability")
    weekday = models.PositiveSmallIntegerField()
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ["weekday", "start_time"]


class BlockedDate(models.Model):
    tutor = models.ForeignKey(TutorProfile, on_delete=models.CASCADE, related_name="blocked_dates")
    date = models.DateField()
    reason = models.CharField(max_length=120, blank=True)

    class Meta:
        unique_together = [("tutor", "date")]


class StatusChange(models.Model):
    """Every vetting decision is logged with the reviewer's name and reason (section 4.1)."""

    tutor = models.ForeignKey(TutorProfile, on_delete=models.CASCADE, related_name="status_history")
    from_status = models.CharField(max_length=20)
    to_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
