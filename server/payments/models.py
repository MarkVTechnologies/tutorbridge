from django.conf import settings
from django.db import models

from core.crypto import EncryptedTextField
from core.models import AppendOnlyModel


class AccountKind(models.TextChoices):
    GATEWAY_CLEARING = "gateway_clearing", "Gateway clearing"
    PARENT_WALLET = "parent_wallet", "Parent wallet"
    ESCROW = "escrow", "Escrow"
    TUTOR_EARNINGS = "tutor_earnings", "Tutor earnings"
    PLATFORM_REVENUE = "platform_revenue", "Platform revenue"
    GATEWAY_FEES = "gateway_fees", "Gateway fees expense"
    PAYOUTS_IN_TRANSIT = "payouts_in_transit", "Payouts in transit"


# Debit-normal accounts (assets/expenses): balance = debits - credits. All others: credits - debits.
DEBIT_NORMAL = {AccountKind.GATEWAY_CLEARING, AccountKind.GATEWAY_FEES}


class LedgerAccount(models.Model):
    kind = models.CharField(max_length=20, choices=AccountKind.choices)
    parent = models.ForeignKey("parents.ParentProfile", null=True, blank=True, on_delete=models.PROTECT)
    tutor = models.ForeignKey("tutors.TutorProfile", null=True, blank=True, on_delete=models.PROTECT)
    booking = models.ForeignKey("bookings.Booking", null=True, blank=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["kind", "parent", "tutor", "booking"], name="uniq_ledger_account"),
        ]

    def __str__(self):
        owner = self.parent_id or self.tutor_id or self.booking_id or "platform"
        return f"{self.kind}:{owner}"


class LedgerTransaction(AppendOnlyModel):
    """A balanced group of entries. `reference` is the idempotency key (PAY-08)."""

    reference = models.CharField(max_length=120, unique=True)
    kind = models.CharField(max_length=40, db_index=True)
    description = models.CharField(max_length=255)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    payment = models.ForeignKey("payments.Payment", null=True, blank=True, on_delete=models.PROTECT)
    booking = models.ForeignKey("bookings.Booking", null=True, blank=True, on_delete=models.PROTECT)
    lesson = models.ForeignKey("bookings.Lesson", null=True, blank=True, on_delete=models.PROTECT)
    payout_item = models.ForeignKey("payments.PayoutItem", null=True, blank=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)


class LedgerEntry(AppendOnlyModel):
    transaction = models.ForeignKey(LedgerTransaction, on_delete=models.PROTECT, related_name="entries")
    account = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT, related_name="entries")
    debit_kobo = models.BigIntegerField(default=0)
    credit_kobo = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(debit_kobo__gte=0) & models.Q(credit_kobo__gte=0)),
                name="ledger_entry_non_negative",
            ),
        ]


class Payment(models.Model):
    class Status(models.TextChoices):
        INITIATED = "initiated"
        SUCCESS = "success"
        FAILED = "failed"
        ABANDONED = "abandoned"

    parent = models.ForeignKey("parents.ParentProfile", on_delete=models.PROTECT, related_name="payments")
    booking = models.ForeignKey("bookings.Booking", null=True, blank=True, on_delete=models.SET_NULL, related_name="payments")
    gateway = models.CharField(max_length=20)
    reference = models.CharField(max_length=80, unique=True)
    amount_kobo = models.BigIntegerField()
    fee_kobo = models.BigIntegerField(default=0)
    currency = models.CharField(max_length=3, default="NGN")
    channel = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.INITIATED, db_index=True)
    authorization_url = models.URLField(max_length=500, blank=True)
    raw_verification = models.JSONField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class WebhookEvent(models.Model):
    """Every webhook is stored raw and processed idempotently (section 14)."""

    gateway = models.CharField(max_length=20)
    event = models.CharField(max_length=60)
    idempotency_key = models.CharField(max_length=160, unique=True)
    payload = models.JSONField()
    signature_valid = models.BooleanField()
    processed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)


class BankAccount(models.Model):
    tutor = models.ForeignKey("tutors.TutorProfile", on_delete=models.CASCADE, related_name="bank_accounts")
    bank_code = models.CharField(max_length=10)
    bank_name = models.CharField(max_length=80)
    account_number = EncryptedTextField()
    account_last4 = models.CharField(max_length=4)
    account_name = models.CharField(max_length=120)
    name_match = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    recipient_code = models.CharField(max_length=60, blank=True)
    is_active = models.BooleanField(default=True)
    payout_hold_until = models.DateTimeField(null=True, blank=True)  # OUT-05: 48h hold after a change
    created_at = models.DateTimeField(auto_now_add=True)


class Payout(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft"
        APPROVED = "approved"
        COMPLETED = "completed"
        PARTIAL = "partial", "Partially failed"
        CANCELLED = "cancelled"

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    total_kobo = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class PayoutItem(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        SENT = "sent"
        SUCCESS = "success"
        FAILED = "failed"
        REMOVED = "removed"

    payout = models.ForeignKey(Payout, on_delete=models.CASCADE, related_name="items")
    tutor = models.ForeignKey("tutors.TutorProfile", on_delete=models.PROTECT, related_name="payout_items")
    amount_kobo = models.BigIntegerField()
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT)
    bank_snapshot = models.JSONField()  # bank name, last4, account name, recipient code at time of payout
    transfer_reference = models.CharField(max_length=80, unique=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    failure_reason = models.CharField(max_length=255, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class ReconciliationRun(models.Model):
    run_date = models.DateField()
    checked = models.PositiveIntegerField(default=0)
    mismatches = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
