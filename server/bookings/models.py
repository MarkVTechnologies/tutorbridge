import hashlib
import secrets

from django.db import models

from core.crypto import EncryptedTextField


class BookingStatus(models.TextChoices):
    AWAITING_PAYMENT = "awaiting_payment", "Awaiting payment"
    OFFERED = "offered", "Waiting for tutor"
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    REASSIGNING = "reassigning", "Finding another tutor"
    REPLACED = "replaced", "Replaced"


class Booking(models.Model):
    parent = models.ForeignKey("parents.ParentProfile", on_delete=models.PROTECT, related_name="bookings")
    tutor = models.ForeignKey("tutors.TutorProfile", on_delete=models.PROTECT, related_name="bookings")
    child = models.ForeignKey("parents.Child", on_delete=models.PROTECT, related_name="bookings")
    request = models.ForeignKey("matching.LessonRequest", null=True, blank=True, on_delete=models.SET_NULL, related_name="bookings")
    subjects = models.ManyToManyField("core.Subject")
    is_trial = models.BooleanField(default=False)
    package_size = models.PositiveSmallIntegerField()
    lesson_minutes = models.PositiveSmallIntegerField()
    schedule = models.JSONField()  # [{"weekday": 0, "start": "16:00"}, ...] recurring weekly slots
    start_date = models.DateField()
    # Pricing snapshot (all kobo)
    hourly_rate_kobo = models.BigIntegerField()
    lesson_price_kobo = models.BigIntegerField()
    commission_pct = models.DecimalField(max_digits=5, decimal_places=2)
    matching_fee_kobo = models.BigIntegerField(default=0)
    matching_credit_kobo = models.BigIntegerField(default=0)
    total_kobo = models.BigIntegerField()
    # Location snapshot
    address = EncryptedTextField(blank=True)
    area = models.ForeignKey("core.Area", null=True, blank=True, on_delete=models.PROTECT)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)  # lesson address, for check-in distance
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_online = models.BooleanField(default=False)
    online_link = models.URLField(blank=True)  # LSN-07
    # Lifecycle
    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.AWAITING_PAYMENT, db_index=True)
    offer_expires_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    declined_tutor_ids = models.JSONField(default=list, blank=True)
    replaces = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="replacements")
    renews = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="renewals")  # BKG-06
    promo = models.ForeignKey("payments.PromoCode", null=True, blank=True, on_delete=models.PROTECT, related_name="bookings")
    discount_kobo = models.BigIntegerField(default=0)
    auto_renew = models.BooleanField(default=False)
    cancel_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Booking #{self.pk} ({self.status})"


class LessonStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    IN_PROGRESS = "in_progress", "In progress"
    COMPLETED = "completed", "Completed (in dispute window)"
    CONFIRMED = "confirmed", "Confirmed"
    DISPUTED = "disputed", "Disputed"
    CANCELLED = "cancelled", "Cancelled"
    NO_SHOW = "no_show", "Tutor no-show"


class EscrowStatus(models.TextChoices):
    RESERVED = "reserved", "Reserved"
    RELEASED = "released", "Released"
    PAID_OUT = "paid_out", "Paid out"
    REFUNDED = "refunded", "Refunded"


def _hash_code(code):
    return hashlib.sha256(code.encode()).hexdigest()


class Lesson(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="lessons")
    tutor = models.ForeignKey("tutors.TutorProfile", on_delete=models.PROTECT, related_name="lessons")
    scheduled_start = models.DateTimeField(db_index=True)
    scheduled_end = models.DateTimeField()
    status = models.CharField(max_length=20, choices=LessonStatus.choices, default=LessonStatus.SCHEDULED, db_index=True)
    amount_kobo = models.BigIntegerField()
    escrow_status = models.CharField(max_length=10, choices=EscrowStatus.choices, default=EscrowStatus.RESERVED)
    # LSN-01: codes shown only to the parent; hashes used to verify the tutor's entry.
    checkin_code_hash = models.CharField(max_length=64)
    checkout_code_hash = models.CharField(max_length=64)
    checkin_code = EncryptedTextField()
    checkout_code = EncryptedTextField()
    code_attempts = models.PositiveSmallIntegerField(default=0)
    checkin_at = models.DateTimeField(null=True, blank=True)
    checkout_at = models.DateTimeField(null=True, blank=True)
    checkin_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    checkin_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    late_minutes = models.PositiveSmallIntegerField(default=0)
    checkin_distance_m = models.PositiveIntegerField(null=True, blank=True)  # from the booked address, if both known
    # LSN-03 lesson note
    note_topics = models.TextField(blank=True)
    note_homework = models.TextField(blank=True)
    note_observations = models.TextField(blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.CharField(max_length=10, blank=True)  # parent | tutor | staff
    cancel_reason = models.CharField(max_length=255, blank=True)
    late_alert_sent = models.BooleanField(default=False)
    reminder_sent = models.BooleanField(default=False)
    payout_item = models.ForeignKey("payments.PayoutItem", null=True, blank=True, on_delete=models.SET_NULL, related_name="lessons")

    class Meta:
        ordering = ["scheduled_start"]

    def set_codes(self):
        cin, cout = f"{secrets.randbelow(10**6):06d}", f"{secrets.randbelow(10**6):06d}"
        while cout == cin:
            cout = f"{secrets.randbelow(10**6):06d}"
        self.checkin_code, self.checkout_code = cin, cout
        self.checkin_code_hash, self.checkout_code_hash = _hash_code(cin), _hash_code(cout)

    def check_code(self, which, code):
        expected = self.checkin_code_hash if which == "in" else self.checkout_code_hash
        return secrets.compare_digest(expected, _hash_code(str(code).strip()))

    @property
    def duration_hours(self):
        return (self.scheduled_end - self.scheduled_start).total_seconds() / 3600
