import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils import timezone

from core.crypto import EncryptedTextField


class Role(models.TextChoices):
    PARENT = "parent", "Parent / Guardian"
    TUTOR = "tutor", "Tutor"
    VETTING = "vetting_officer", "Vetting Officer"
    OPS = "ops_officer", "Operations / Matching Officer"
    FINANCE = "finance_officer", "Finance Officer"
    SAFETY = "safety_officer", "Safety Officer"
    SUPER = "super_admin", "Super Admin"


STAFF_ROLES = {Role.VETTING, Role.OPS, Role.FINANCE, Role.SAFETY, Role.SUPER}


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, phone, password=None, **extra):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email).lower(), phone=phone, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, phone, password=None, **extra):
        extra.setdefault("role", Role.SUPER)
        extra.setdefault("email_verified_at", timezone.now())
        extra.setdefault("phone_verified_at", timezone.now())
        return self.create_user(email, phone, password, **extra)


class User(AbstractBaseUser):
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, unique=True)  # E.164, e.g. +2348012345678
    first_name = models.CharField(max_length=60)
    last_name = models.CharField(max_length=60)
    gender = models.CharField(max_length=10, blank=True, choices=[("female", "Female"), ("male", "Male")])
    role = models.CharField(max_length=20, choices=Role.choices, db_index=True)
    is_active = models.BooleanField(default=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    date_joined = models.DateTimeField(default=timezone.now)
    # AUTH-05 lockout
    failed_login_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    # AUTH-06/07 two-factor (TOTP)
    totp_secret = EncryptedTextField(blank=True, default="")
    totp_enabled = models.BooleanField(default=False)
    # AUTH-08 extra granular permissions on top of the role defaults
    extra_permissions = models.JSONField(default=list, blank=True)
    # Suspension (SAF-04)
    suspended_at = models.DateTimeField(null=True, blank=True)
    suspension_reason = models.TextField(blank=True)
    # NDPA consents
    consent_terms_at = models.DateTimeField(null=True, blank=True)
    consent_marketing = models.BooleanField(default=False)
    consent_location = models.BooleanField(default=False)
    notification_prefs = models.JSONField(default=dict, blank=True)  # MSG-07

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["phone"]

    def __str__(self):
        return f"{self.get_full_name()} <{self.email}>"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def display_name(self):
        """First name + last initial, the only name shown across the marketplace (TUT-14)."""
        return f"{self.first_name} {self.last_name[:1]}.".strip()

    @property
    def is_staff_member(self):
        return self.role in STAFF_ROLES

    @property
    def is_verified(self):
        return bool(self.email_verified_at and self.phone_verified_at)

    @property
    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())

    def has_perm_code(self, code):
        from accounts.permissions import role_permissions

        return code in role_permissions(self.role) or code in (self.extra_permissions or [])


class OTPCode(models.Model):
    """One-time codes for phone verification, bank changes and similar sensitive steps."""

    PURPOSES = [("phone", "Phone verification"), ("bank_change", "Bank account change"), ("login", "Login")]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otp_codes")
    purpose = models.CharField(max_length=20, choices=PURPOSES)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def hash(code):
        return hashlib.sha256(code.encode()).hexdigest()

    @classmethod
    def issue(cls, user, purpose, minutes=10):
        code = f"{secrets.randbelow(10**6):06d}"
        cls.objects.filter(user=user, purpose=purpose, used_at__isnull=True).update(used_at=timezone.now())
        cls.objects.create(
            user=user, purpose=purpose, code_hash=cls.hash(code), expires_at=timezone.now() + timedelta(minutes=minutes)
        )
        return code

    @classmethod
    def verify(cls, user, purpose, code):
        otp = cls.objects.filter(user=user, purpose=purpose, used_at__isnull=True).order_by("-created_at").first()
        if not otp or otp.expires_at < timezone.now() or otp.attempts >= 5:
            return False
        if not secrets.compare_digest(otp.code_hash, cls.hash(str(code).strip())):
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            return False
        otp.used_at = timezone.now()
        otp.save(update_fields=["used_at"])
        return True
