from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from accounts.models import Role, User
from accounts.phone import normalise_phone


class UserSerializer(serializers.ModelSerializer):
    is_verified = serializers.BooleanField(read_only=True)
    is_staff_member = serializers.BooleanField(read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "phone", "first_name", "last_name", "gender", "role", "is_verified", "is_staff_member",
            "email_verified_at", "phone_verified_at", "totp_enabled", "notification_prefs", "consent_marketing",
            "consent_location", "permissions",
        ]
        read_only_fields = ["id", "email", "phone", "role", "email_verified_at", "phone_verified_at", "totp_enabled"]

    def get_permissions(self, user):
        from accounts.permissions import role_permissions

        return sorted(set(role_permissions(user.role)) | set(user.extra_permissions or []))


class SignupSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=[Role.PARENT, Role.TUTOR])
    first_name = serializers.CharField(max_length=60)
    last_name = serializers.CharField(max_length=60)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20)
    gender = serializers.ChoiceField(choices=["female", "male"], required=False, allow_blank=True)
    password = serializers.CharField(write_only=True)
    consent_terms = serializers.BooleanField()
    consent_marketing = serializers.BooleanField(required=False, default=False)

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate_phone(self, value):
        phone = normalise_phone(value)
        if not phone:
            raise serializers.ValidationError("Enter a valid phone number, e.g. 0803 123 4567.")
        if User.objects.filter(phone=phone).exists():
            raise serializers.ValidationError("An account with this phone number already exists.")
        return phone

    def validate_consent_terms(self, value):
        if not value:
            raise serializers.ValidationError("You must accept the terms and privacy policy.")
        return value

    def validate(self, attrs):
        candidate = User(email=attrs["email"], first_name=attrs["first_name"], last_name=attrs["last_name"])
        validate_password(attrs["password"], candidate)
        return attrs


class PasswordResetSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True)
