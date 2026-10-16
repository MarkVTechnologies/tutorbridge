from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from bookings.models import Booking, Lesson, LessonStatus


class LessonSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    codes = serializers.SerializerMethodField()
    can_dispute = serializers.SerializerMethodField()
    dispute_status = serializers.SerializerMethodField()
    tutor_name = serializers.CharField(source="tutor.user.display_name", read_only=True)
    child_name = serializers.CharField(source="booking.child.first_name", read_only=True)

    class Meta:
        model = Lesson
        fields = [
            "id", "booking", "tutor_name", "child_name", "scheduled_start", "scheduled_end", "status", "status_display",
            "amount_kobo", "escrow_status", "checkin_at", "checkout_at", "late_minutes", "note_topics", "note_homework",
            "note_observations", "confirmed_at", "cancelled_by", "cancel_reason", "codes", "can_dispute", "dispute_status",
        ]

    def get_codes(self, obj):
        """LSN-01: codes are visible only to the parent, and only around the lesson."""
        user = self.context["request"].user
        if user.pk != obj.booking.parent.user_id or obj.status not in (LessonStatus.SCHEDULED, LessonStatus.IN_PROGRESS):
            return None
        if obj.scheduled_start - timezone.now() > timedelta(days=1):
            return None
        return {"checkin": obj.checkin_code if obj.status == LessonStatus.SCHEDULED else None, "checkout": obj.checkout_code}

    def get_can_dispute(self, obj):
        from core import config

        window = timedelta(hours=config.get("dispute_window_hours"))
        return obj.status in (LessonStatus.COMPLETED, LessonStatus.IN_PROGRESS) and timezone.now() <= obj.scheduled_end + window

    def get_dispute_status(self, obj):
        d = getattr(obj, "dispute", None)
        return d.status if d else None


class BookingSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    tutor_name = serializers.CharField(source="tutor.user.display_name", read_only=True)
    tutor_id = serializers.IntegerField(source="tutor.pk", read_only=True)
    parent_name = serializers.CharField(source="parent.user.display_name", read_only=True)
    child_name = serializers.CharField(source="child.first_name", read_only=True)
    child_class = serializers.CharField(source="child.class_name", read_only=True)
    subject_names = serializers.SerializerMethodField()
    area_name = serializers.CharField(source="area.name", read_only=True, default=None)
    address_visible = serializers.SerializerMethodField()
    next_lesson = serializers.SerializerMethodField()
    lessons_done = serializers.SerializerMethodField()
    thread_id = serializers.SerializerMethodField()
    renewed_by = serializers.SerializerMethodField()
    amount_due_kobo = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "id", "status", "status_display", "tutor_id", "tutor_name", "parent_name", "child_name", "child_class", "subject_names",
            "is_trial", "package_size", "lesson_minutes", "schedule", "start_date", "hourly_rate_kobo", "lesson_price_kobo",
            "matching_fee_kobo", "matching_credit_kobo", "total_kobo", "area_name", "address_visible", "is_online", "online_link",
            "offer_expires_at", "accepted_at", "auto_renew", "next_lesson", "lessons_done", "thread_id", "created_at",
            "renews", "renewed_by", "amount_due_kobo",
        ]

    def get_subject_names(self, obj):
        return [s.name for s in obj.subjects.all()]

    def get_address_visible(self, obj):
        """The tutor sees the address only after accepting; the parent always does."""
        user = self.context["request"].user
        if user.pk == obj.parent.user_id or (user.pk == obj.tutor.user_id and obj.accepted_at):
            return obj.address
        return None

    def get_next_lesson(self, obj):
        lesson = obj.lessons.filter(status=LessonStatus.SCHEDULED, scheduled_start__gte=timezone.now()).order_by("scheduled_start").first()
        return lesson.scheduled_start if lesson else None

    def get_lessons_done(self, obj):
        return obj.lessons.filter(status=LessonStatus.CONFIRMED).count()

    def get_thread_id(self, obj):
        t = getattr(obj, "thread", None)
        return t.pk if t else None

    def get_renewed_by(self, obj):
        live = ["awaiting_payment", "offered", "active", "completed"]
        r = obj.renewals.filter(status__in=live).order_by("-created_at").first()
        return r.pk if r else None

    def get_amount_due_kobo(self, obj):
        """What the parent still has to pay for an unpaid booking, after wallet credit."""
        if obj.status != "awaiting_payment":
            return 0
        from payments import ledger

        return max(0, obj.total_kobo - ledger.balance(ledger.wallet(obj.parent)))


class CreateBookingSerializer(serializers.Serializer):
    tutor = serializers.IntegerField()
    child = serializers.IntegerField()
    subjects = serializers.ListField(child=serializers.IntegerField(), min_length=1)
    package_size = serializers.IntegerField()
    lesson_minutes = serializers.IntegerField()
    schedule = serializers.JSONField()
    start_date = serializers.DateField()
    request = serializers.IntegerField(required=False, allow_null=True)
    address = serializers.CharField(required=False, allow_blank=True)
    area = serializers.IntegerField(required=False, allow_null=True)
    is_online = serializers.BooleanField(required=False, default=False)

    def validate_schedule(self, value):
        from matching.serializers import validate_schedule

        return validate_schedule(value)
