import hashlib
import secrets

from django.conf import settings
from django.db import models

from core.crypto import EncryptedJSONField


class CheckType(models.TextChoices):
    IDENTITY = "identity", "NIN + selfie"
    BANK = "bank", "Bank account"
    CREDENTIALS = "credentials", "Credentials"
    SUBJECT_TEST = "subject_test", "Subject test"
    INTERVIEW = "interview", "Interview"
    REFERENCES = "references", "References"
    GUARANTOR = "guarantor", "Guarantor"
    ADDRESS = "address", "Address"
    BACKGROUND = "background", "Background check"
    SAFEGUARDING = "safeguarding", "Safeguarding training"


class CheckStatus(models.TextChoices):
    PENDING = "pending", "Not started"
    SUBMITTED = "submitted", "Submitted"
    MANUAL_REVIEW = "manual_review", "Needs manual review"
    PASSED = "passed", "Passed"
    FAILED = "failed", "Failed"


# Checks required before approval. Background is required before the first home visit (activation).
REQUIRED_FOR_APPROVAL = [
    CheckType.IDENTITY, CheckType.BANK, CheckType.CREDENTIALS, CheckType.SUBJECT_TEST, CheckType.INTERVIEW,
    CheckType.REFERENCES, CheckType.GUARANTOR, CheckType.ADDRESS, CheckType.SAFEGUARDING,
]


class VerificationCheck(models.Model):
    tutor = models.ForeignKey("tutors.TutorProfile", on_delete=models.CASCADE, related_name="checks")
    check_type = models.CharField(max_length=20, choices=CheckType.choices)
    status = models.CharField(max_length=20, choices=CheckStatus.choices, default=CheckStatus.PENDING)
    provider = models.CharField(max_length=30, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    result = EncryptedJSONField(null=True, blank=True)
    notes = models.TextField(blank=True)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("tutor", "check_type")]


class DocType(models.TextChoices):
    PHOTO = "photo", "Profile photo"
    SELFIE = "selfie", "Selfie"
    CV = "cv", "CV"
    DEGREE = "degree", "Degree certificate"
    NCE = "nce", "NCE certificate"
    TRCN = "trcn", "TRCN certificate"
    CERTIFICATE = "certificate", "Other certificate"
    POLICE = "police_certificate", "Police character certificate"
    GUARANTOR_ID = "guarantor_id", "Guarantor ID"
    PROOF_OF_ADDRESS = "proof_of_address", "Proof of address"
    EVIDENCE = "evidence", "Dispute/incident evidence"


class Document(models.Model):
    """TUT-06: private uploads, stored outside the web root, served through permission-checked views."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="documents")
    doc_type = models.CharField(max_length=30, choices=DocType.choices)
    storage_path = models.CharField(max_length=255)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=60)
    size = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    status = models.CharField(max_length=10, default="pending", choices=[("pending", "Pending"), ("accepted", "Accepted"), ("rejected", "Rejected")])
    review_note = models.CharField(max_length=255, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Question(models.Model):
    """TUT-09: admin-managed question bank."""

    subject = models.ForeignKey("core.Subject", on_delete=models.CASCADE, related_name="questions")
    level = models.ForeignKey("core.Level", on_delete=models.CASCADE)
    text = models.TextField()
    options = models.JSONField()  # list of strings
    correct_index = models.PositiveSmallIntegerField()
    is_active = models.BooleanField(default=True)


class TestAttempt(models.Model):
    tutor = models.ForeignKey("tutors.TutorProfile", on_delete=models.CASCADE, related_name="test_attempts")
    subject = models.ForeignKey("core.Subject", on_delete=models.PROTECT)
    level = models.ForeignKey("core.Level", on_delete=models.PROTECT)
    question_ids = models.JSONField()
    answers = models.JSONField(default=dict)
    started_at = models.DateTimeField(auto_now_add=True)
    deadline = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    score_pct = models.PositiveSmallIntegerField(null=True, blank=True)
    passed = models.BooleanField(default=False)


class InterviewSlot(models.Model):
    """TUT-10: interview slots published by vetting staff."""

    officer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="interview_slots")
    starts_at = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=30)
    meeting_link = models.URLField(blank=True)
    tutor = models.ForeignKey("tutors.TutorProfile", null=True, blank=True, on_delete=models.SET_NULL, related_name="interviews")
    outcome = models.CharField(max_length=10, blank=True, choices=[("pass", "Pass"), ("fail", "Fail"), ("no_show", "No-show")])
    notes = models.TextField(blank=True)
    reminded_24h = models.BooleanField(default=False)  # TUT-10
    reminded_1h = models.BooleanField(default=False)

    class Meta:
        ordering = ["starts_at"]


class Reference(models.Model):
    """TUT-11: referees and guarantor, contacted by secure single-use link."""

    KINDS = [("referee", "Referee"), ("guarantor", "Guarantor")]
    tutor = models.ForeignKey("tutors.TutorProfile", on_delete=models.CASCADE, related_name="references")
    kind = models.CharField(max_length=10, choices=KINDS)
    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    relationship = models.CharField(max_length=80)
    organisation = models.CharField(max_length=120, blank=True)
    is_professional = models.BooleanField(default=False)
    token_hash = models.CharField(max_length=64, unique=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    response = models.JSONField(null=True, blank=True)
    id_document = models.ForeignKey(Document, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    call_verified = models.BooleanField(default=False)
    call_notes = models.TextField(blank=True)

    @staticmethod
    def hash_token(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def issue_token(self):
        token = secrets.token_urlsafe(32)
        self.token_hash = self.hash_token(token)
        return token
