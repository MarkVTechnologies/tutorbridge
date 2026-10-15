from django.utils import timezone
from rest_framework import serializers

from parents.models import Child, ParentProfile


class ParentProfileSerializer(serializers.ModelSerializer):
    area_name = serializers.CharField(source="area.name", read_only=True, default=None)

    class Meta:
        model = ParentProfile
        fields = ["address", "area", "area_name", "lat", "lng", "address_verified", "is_diaspora", "cancellation_count"]
        read_only_fields = ["address_verified", "cancellation_count"]


class ChildSerializer(serializers.ModelSerializer):
    level_name = serializers.CharField(source="level.name", read_only=True)
    curriculum_name = serializers.CharField(source="curriculum.name", read_only=True)
    parental_consent = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = Child
        fields = [
            "id", "first_name", "class_name", "level", "level_name", "curriculum", "curriculum_name", "school_type",
            "learning_notes", "special_needs", "parental_consent", "is_active",
        ]

    def validate(self, attrs):
        if self.instance is None and not attrs.get("parental_consent"):
            raise serializers.ValidationError({"parental_consent": "Please confirm you consent to us storing this information."})
        return attrs

    def create(self, validated):
        validated.pop("parental_consent", None)
        validated["parental_consent_at"] = timezone.now()
        return super().create(validated)

    def update(self, instance, validated):
        validated.pop("parental_consent", None)
        return super().update(instance, validated)
