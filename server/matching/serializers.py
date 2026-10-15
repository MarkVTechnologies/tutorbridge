from datetime import datetime

from django.utils import timezone
from rest_framework import serializers

from core.models import Subject
from matching.models import LessonRequest, Match
from tutors.serializers import TutorPublicSerializer


def validate_schedule(value):
    if not isinstance(value, list) or not value:
        raise serializers.ValidationError("Choose at least one weekly slot.")
    if len(value) > 7:
        raise serializers.ValidationError("At most 7 weekly slots.")
    clean = []
    for slot in value:
        try:
            weekday = int(slot["weekday"])
            start = datetime.strptime(slot["start"], "%H:%M").strftime("%H:%M")
        except (KeyError, ValueError, TypeError) as e:
            raise serializers.ValidationError("Each slot needs a weekday (0-6) and start time (HH:MM).") from e
        if not 0 <= weekday <= 6:
            raise serializers.ValidationError("weekday must be 0 (Mon) to 6 (Sun).")
        clean.append({"weekday": weekday, "start": start})
    return clean


class LessonRequestSerializer(serializers.ModelSerializer):
    subjects = serializers.PrimaryKeyRelatedField(many=True, queryset=Subject.objects.filter(is_active=True))
    subject_names = serializers.SerializerMethodField()
    child_name = serializers.CharField(source="child.first_name", read_only=True)
    area_name = serializers.CharField(source="area.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = LessonRequest
        fields = [
            "id", "child", "child_name", "subjects", "subject_names", "goals", "schedule", "lesson_minutes", "start_date",
            "address", "area", "area_name", "lat", "lng", "budget_min_kobo", "budget_max_kobo", "preferences",
            "requested_tutor", "is_online", "status", "status_display", "sla_due_at", "shortlist_published_at", "created_at",
        ]
        read_only_fields = ["status", "sla_due_at", "shortlist_published_at", "created_at"]
        extra_kwargs = {"address": {"write_only": True}}

    def get_subject_names(self, obj):
        return [s.name for s in obj.subjects.all()]

    def validate_schedule(self, value):
        return validate_schedule(value)

    def validate_start_date(self, value):
        if value < timezone.localdate():
            raise serializers.ValidationError("Start date cannot be in the past.")
        return value

    def validate_child(self, child):
        parent = self.context["request"].user.parent_profile
        if child.parent_id != parent.pk or not child.is_active:
            raise serializers.ValidationError("Child not found.")
        return child

    def validate(self, attrs):
        if attrs.get("budget_max_kobo") and attrs.get("budget_min_kobo", 0) > attrs["budget_max_kobo"]:
            raise serializers.ValidationError({"budget_max_kobo": "Maximum budget must be above the minimum."})
        if not attrs.get("is_online") and not attrs.get("address"):
            raise serializers.ValidationError({"address": "Enter the address where lessons will take place."})
        return attrs


class ShortlistItemSerializer(serializers.ModelSerializer):
    tutor = TutorPublicSerializer()

    class Meta:
        model = Match
        fields = ["id", "tutor", "score", "rank", "status"]


class StaffMatchSerializer(serializers.ModelSerializer):
    tutor = TutorPublicSerializer()
    tutor_full_name = serializers.CharField(source="tutor.user.get_full_name", read_only=True)

    class Meta:
        model = Match
        fields = ["id", "tutor", "tutor_full_name", "score", "breakdown", "status", "in_shortlist", "rank", "decline_reason", "responded_at"]
