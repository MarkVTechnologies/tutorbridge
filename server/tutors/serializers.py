from rest_framework import serializers

from tutors.models import AvailabilitySlot, BlockedDate, TutorProfile, TutorSubject


class TutorSubjectSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    level_name = serializers.CharField(source="level.name", read_only=True)

    class Meta:
        model = TutorSubject
        fields = ["id", "subject", "subject_name", "level", "level_name", "test_score", "verified"]
        read_only_fields = ["test_score", "verified"]


class AvailabilitySlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvailabilitySlot
        fields = ["id", "weekday", "start_time", "end_time"]

    def validate(self, attrs):
        if not 0 <= attrs["weekday"] <= 6:
            raise serializers.ValidationError("weekday must be 0 (Mon) to 6 (Sun)")
        if attrs["end_time"] <= attrs["start_time"]:
            raise serializers.ValidationError("End time must be after start time.")
        return attrs


class BlockedDateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlockedDate
        fields = ["id", "date", "reason"]


def _badges(tutor):
    checks = {c.check_type: c.status for c in tutor.checks.all()}
    labels = {
        "identity": "ID verified", "background": "Background checked", "interview": "Interviewed",
        "subject_test": "Subject tested", "references": "References checked", "safeguarding": "Safeguarding trained",
    }
    return [label for key, label in labels.items() if checks.get(key) == "passed"]


class TutorPublicSerializer(serializers.ModelSerializer):
    """TUT-14: first name + initial, photo, badges, subjects, rating, hours, bio — never contact details."""

    name = serializers.CharField(source="user.display_name")
    gender = serializers.CharField(source="user.gender")
    photo_url = serializers.SerializerMethodField()
    subjects = TutorSubjectSerializer(many=True)
    curricula = serializers.SlugRelatedField(many=True, read_only=True, slug_field="name")
    areas = serializers.SerializerMethodField()
    badges = serializers.SerializerMethodField()
    home_area_name = serializers.CharField(source="home_area.name", default=None)

    class Meta:
        model = TutorProfile
        fields = [
            "id", "name", "gender", "photo_url", "headline", "bio", "highest_qualification", "years_experience",
            "subjects", "curricula", "areas", "home_area_name", "hourly_rate_kobo", "tier", "rating_avg", "rating_count",
            "reliability_score", "hours_taught", "lessons_completed", "badges", "accepts_special_needs", "offers_online",
        ]

    def get_photo_url(self, obj):
        return f"/api/tutors/{obj.pk}/photo/" if obj.photo_id else None

    def get_areas(self, obj):
        return [a.area.name for a in obj.areas.all()]

    def get_badges(self, obj):
        return _badges(obj)


class TutorOwnProfileSerializer(serializers.ModelSerializer):
    subjects = TutorSubjectSerializer(many=True, read_only=True)
    availability = AvailabilitySlotSerializer(many=True, read_only=True)
    areas = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = TutorProfile
        fields = [
            "id", "status", "status_display", "headline", "bio", "photo", "photo_url", "highest_qualification", "years_experience",
            "trcn_number", "curricula", "hourly_rate_kobo", "home_area", "max_travel_km", "accepts_special_needs", "offers_online",
            "subjects", "availability", "areas", "tier", "rating_avg", "rating_count", "reliability_score", "hours_taught",
            "lessons_completed", "strikes", "safeguarding_completed_at", "agreement_signed_at", "location_consent",
            "submitted_at", "approved_at", "background_valid_until", "reverify_due",
        ]
        read_only_fields = [
            "status", "photo", "tier", "rating_avg", "rating_count", "reliability_score", "hours_taught", "lessons_completed",
            "strikes", "safeguarding_completed_at", "agreement_signed_at", "submitted_at", "approved_at",
            "background_valid_until", "reverify_due",
        ]

    def get_areas(self, obj):
        return [{"id": a.area_id, "name": a.area.name} for a in obj.areas.select_related("area")]

    def get_photo_url(self, obj):
        return f"/api/tutors/{obj.pk}/photo/" if obj.photo_id else None

    def validate_hourly_rate_kobo(self, value):
        tutor = self.instance
        if tutor is not None and value:
            from tutors.services import rate_band

            band = rate_band(tutor)
            if band and not band["min_kobo"] <= value <= band["max_kobo"]:
                raise serializers.ValidationError(
                    f"For the levels you teach, your rate must be between ₦{band['min_kobo'] // 100:,} and ₦{band['max_kobo'] // 100:,} per hour."
                )
        return value
