from django.conf import settings
from django.db import models

from core.crypto import EncryptedTextField


class ParentProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="parent_profile")
    address = EncryptedTextField(blank=True)
    area = models.ForeignKey("core.Area", null=True, blank=True, on_delete=models.PROTECT)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    address_verified = models.BooleanField(default=False)
    is_diaspora = models.BooleanField(default=False)
    cancellation_count = models.PositiveIntegerField(default=0)  # visible to tutors (section 4.3)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Parent {self.user.get_full_name()}"


class Child(models.Model):
    """REQ-01: child sub-profile. Data minimised: first name, class, learning needs only (NDPA)."""

    SCHOOL_TYPES = [("private", "Private"), ("public", "Public"), ("international", "International"), ("homeschool", "Home-school")]
    parent = models.ForeignKey(ParentProfile, on_delete=models.CASCADE, related_name="children")
    first_name = models.CharField(max_length=60)
    class_name = models.CharField(max_length=30)  # e.g. "JSS2", "Primary 5", "Year 9"
    level = models.ForeignKey("core.Level", on_delete=models.PROTECT)
    curriculum = models.ForeignKey("core.Curriculum", on_delete=models.PROTECT)
    school_type = models.CharField(max_length=20, choices=SCHOOL_TYPES, blank=True)
    learning_notes = EncryptedTextField(blank=True)
    special_needs = models.BooleanField(default=False)
    parental_consent_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "children"

    def __str__(self):
        return f"{self.first_name} ({self.class_name})"
