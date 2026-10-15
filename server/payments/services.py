"""
Money-moving operations. Every function here:
  * runs inside a DB transaction,
  * posts balanced, idempotent ledger transactions,
  * writes an audit log entry for staff-initiated actions.
"""
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core import config
from core.audit import audit
from core.money import naira, percent_of, split_commission
from messaging.notify import notify
from payments import ledger
from payments.gateways import GatewayError, get_gateway
from payments.models import AccountKind, BankAccount, Payment, Payout, PayoutItem, WebhookEvent

log = logging.getLogger(__name__)


def new_reference(prefix):
    return f"{prefix}_{timezone.now():%Y%m%d}_{secrets.token_hex(6)}"


# --- Collections -----------------------------------------------------------


def start_checkout(parent, amount_kobo, booking=None):
    if amount_kobo <= 0:
        raise ValueError("Amount must be positive")
    gateway = get_gateway()
    payment = Payment.objects.create(
        parent=parent, booking=booking, gateway=gateway.name, reference=new_reference("TB"), amount_kobo=amount_kobo,
    )
    payment.authorization_url = gateway.initialize(
        email=parent.user.email,
        amount_kobo=amount_kobo,
        reference=payment.reference,
        callback_url=f"{settings.SITE_URL}/payments/callback",
        metadata={"payment_id": payment.pk, "booking_id": booking.pk if booking else None},
    )
    payment.save(update_fields=["authorization_url"])
    return payment


def handle_webhook(gateway_name, raw_body, headers):
    """Store raw webhook, verify signature, process idempotently (PAY-02, PAY-08)."""
    from payments.gateways import parse_json

    gateway = get_gateway(gateway_name)
    payload = parse_json(raw_body)
    valid = gateway.check_signature(raw_body, headers)
    norm = gateway.normalise_webhook(payload)
    key = f"{gateway.name}:{norm['event']}:{norm['reference']}:{norm['id']}"
    event, created = WebhookEvent.objects.get_or_create(
        idempotency_key=key[:160],
        defaults={"gateway": gateway.name, "event": norm["event"] or "", "payload": payload, "signature_valid": valid},
    )
    if not valid:
        log.warning("Rejected webhook with invalid signature: %s", key)
        return False
    if event.processed_at:
        return True  # replay: no effect
    try:
        if norm["event"] == "charge.success":
            payment = Payment.objects.filter(reference=norm["reference"], gateway=gateway.name).first()
            if payment:
                verify_and_credit(payment, source="webhook")
        elif norm["event"] in ("transfer.success", "transfer.failed"):
            item = PayoutItem.objects.filter(transfer_reference=norm["reference"]).first()
            if item:
                settle_transfer(item, success=norm["event"] == "transfer.success")
        event.processed_at = timezone.now()
        event.error = ""
    except Exception as e:  # noqa: BLE001 - stored for finance review; gateway will retry
        event.error = str(e)[:2000]
        event.save(update_fields=["error"])
        raise
    event.save(update_fields=["processed_at", "error"])
    return True


def verify_and_credit(payment, source="webhook"):
    """Server-side verify call; only a verified, matching success credits the wallet."""
    if payment.status == Payment.Status.SUCCESS:
        return payment
    v = get_gateway(payment.gateway).verify(payment.reference)
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        if payment.status == Payment.Status.SUCCESS:
            return payment
        payment.raw_verification = {**(payment.raw_verification or {}), "verify": v.raw, "source": source}
        if v.status == "failed":
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "raw_verification"])
            return payment
        if v.status != "success":
            payment.save(update_fields=["raw_verification"])
            return payment
        if v.currency != "NGN" or v.amount_kobo != payment.amount_kobo:
            payment.save(update_fields=["raw_verification"])
            _finance_alert("Payment amount mismatch", f"{payment.reference}: expected {payment.amount_kobo} NGN, gateway says {v.amount_kobo} {v.currency}")
            return payment
        payment.status, payment.verified_at = Payment.Status.SUCCESS, timezone.now()
        payment.fee_kobo, payment.channel = v.fee_kobo, v.channel
        payment.save()
        credit_payment(payment)
    notify(payment.parent.user, "payment_received", {"amount": naira(payment.amount_kobo), "reference": payment.reference})
    return payment


def credit_payment(payment):
    """Parent pays: Dr gateway clearing / Cr parent wallet. Gateway fee absorbed by platform."""
    clearing = ledger.platform(AccountKind.GATEWAY_CLEARING)
    ledger.transfer(f"payment:{payment.reference}", "payment", f"Payment {payment.reference}", clearing, ledger.wallet(payment.parent), payment.amount_kobo, payment=payment)
    if payment.fee_kobo:
        ledger.transfer(f"fee:{payment.reference}", "gateway_fee", f"Gateway fee {payment.reference}", ledger.platform(AccountKind.GATEWAY_FEES), clearing, payment.fee_kobo, payment=payment)
    if payment.booking_id:
        from bookings.services import fund_booking

        fund_booking(payment.booking)


# --- Escrow ----------------------------------------------------------------


def reserve_booking(booking):
    """Move a booking's price from the parent wallet into its escrow account (and take the matching fee)."""
    wallet = ledger.wallet(booking.parent)
    esc = ledger.escrow(booking)
    revenue = ledger.platform(AccountKind.PLATFORM_REVENUE)
    lessons_total = booking.lesson_price_kobo * booking.package_size
    with transaction.atomic():
        if booking.matching_credit_kobo:
            ledger.transfer(f"matchcredit:{booking.pk}", "matching_credit", f"Matching fee credited to package #{booking.pk}", revenue, wallet, booking.matching_credit_kobo, booking=booking)
        lines = [(wallet, lessons_total + booking.matching_fee_kobo, 0), (esc, 0, lessons_total)]
        if booking.matching_fee_kobo:
            lines.append((revenue, 0, booking.matching_fee_kobo))
        ledger.post(f"reserve:{booking.pk}", "reserve", f"Reserve funds for booking #{booking.pk}", lines, booking=booking)


def release_lesson(lesson):
    """Confirmed lesson: escrow → tutor earnings (net) + platform revenue (commission)."""
    booking = lesson.booking
    tutor_share, commission = split_commission(lesson.amount_kobo, booking.commission_pct)
    esc = ledger.escrow(booking)
    lines = [(esc, lesson.amount_kobo, 0), (ledger.earnings(lesson.tutor), 0, tutor_share)]
    if commission:
        lines.append((ledger.platform(AccountKind.PLATFORM_REVENUE), 0, commission))
    ledger.post(f"release:{lesson.pk}", "release", f"Lesson #{lesson.pk} confirmed", lines, lesson=lesson, booking=booking)


def refund_lesson(lesson, tutor_pct=0, reason=""):
    """Return a lesson's escrow to the parent wallet, optionally paying the tutor a share (late cancellation)."""
    booking = lesson.booking
    esc = ledger.escrow(booking)
    to_tutor_gross = percent_of(lesson.amount_kobo, tutor_pct) if tutor_pct else 0
    to_parent = lesson.amount_kobo - to_tutor_gross
    lines = [(esc, lesson.amount_kobo, 0)]
    if to_parent:
        lines.append((ledger.wallet(booking.parent), 0, to_parent))
    if to_tutor_gross:
        tutor_share, commission = split_commission(to_tutor_gross, booking.commission_pct)
        lines.append((ledger.earnings(lesson.tutor), 0, tutor_share))
        if commission:
            lines.append((ledger.platform(AccountKind.PLATFORM_REVENUE), 0, commission))
    ledger.post(f"refund:{lesson.pk}", "refund", f"Lesson #{lesson.pk} refunded: {reason}"[:255], lines, lesson=lesson, booking=booking)


def partial_refund_lesson(lesson, refund_kobo, reason=""):
    """Dispute partial refund: part back to the parent, the rest released to the tutor."""
    booking = lesson.booking
    refund_kobo = max(0, min(refund_kobo, lesson.amount_kobo))
    remainder = lesson.amount_kobo - refund_kobo
    lines = [(ledger.escrow(booking), lesson.amount_kobo, 0)]
    if refund_kobo:
        lines.append((ledger.wallet(booking.parent), 0, refund_kobo))
    if remainder:
        tutor_share, commission = split_commission(remainder, booking.commission_pct)
        lines.append((ledger.earnings(lesson.tutor), 0, tutor_share))
        if commission:
            lines.append((ledger.platform(AccountKind.PLATFORM_REVENUE), 0, commission))
    ledger.post(f"partial:{lesson.pk}", "partial_refund", f"Lesson #{lesson.pk} partial refund: {reason}"[:255], lines, lesson=lesson, booking=booking)


def move_escrow(from_booking, to_booking, amount, reason):
    """Carry package balance to a replacement booking (BKG-07)."""
    ledger.transfer(f"carry:{from_booking.pk}:{to_booking.pk}", "carry_over", reason, ledger.escrow(from_booking), ledger.escrow(to_booking), amount, booking=to_booking)


def escrow_to_wallet(booking, amount, reference, reason):
    if amount > 0:
        ledger.transfer(reference, "escrow_return", reason, ledger.escrow(booking), ledger.wallet(booking.parent), amount, booking=booking)


def wallet_cash_refund(parent, amount_kobo, user, request=None):
    """Unused balance paid back to the parent's bank/card on request (minus gateway costs, handled offline)."""
    txn, _ = ledger.transfer(new_reference("cashrefund"), "cash_refund", f"Cash refund to parent #{parent.pk}", ledger.wallet(parent), ledger.platform(AccountKind.GATEWAY_CLEARING), amount_kobo, user=user)
    audit(user, "refund.cash", "parent", parent.pk, after={"amount_kobo": amount_kobo, "txn": txn.reference}, request=request)
    return txn


# --- Payouts ---------------------------------------------------------------


def settle_vetting_fee(tutor):
    """Deduct the one-off vetting fee from first earnings when configured (decision #4)."""
    fee = config.get("vetting_fee_kobo")
    if not fee or not config.get("vetting_fee_deduct_from_earnings"):
        return
    from django.db.models import Sum

    from payments.models import LedgerEntry

    earn = ledger.earnings(tutor)
    already = LedgerEntry.objects.filter(account=earn, transaction__kind="vetting_fee").aggregate(s=Sum("debit_kobo"))["s"] or 0
    amount = min(fee - already, ledger.balance(earn))
    if amount > 0:
        ledger.transfer(f"vettingfee:{tutor.pk}:{already}", "vetting_fee", f"Vetting fee (tutor #{tutor.pk})", earn, ledger.platform(AccountKind.PLATFORM_REVENUE), amount)


def create_payout_batch(user=None):
    """OUT-02: batch all cleared tutor earnings above the minimum threshold."""
    from tutors.models import TutorProfile

    now = timezone.now()
    minimum = config.get("payout_min_kobo")
    with transaction.atomic():
        payout = Payout.objects.create(created_by=user)
        total = 0
        tutor_ids = ledger.LedgerAccount.objects.filter(kind=AccountKind.TUTOR_EARNINGS).values_list("tutor_id", flat=True)
        for tutor in TutorProfile.objects.filter(pk__in=tutor_ids).select_related("user"):
            settle_vetting_fee(tutor)
            amount = ledger.balance(ledger.earnings(tutor))
            if amount < minimum:
                continue
            if PayoutItem.objects.filter(tutor=tutor, status__in=[PayoutItem.Status.PENDING, PayoutItem.Status.SENT]).exists():
                continue
            bank = BankAccount.objects.filter(tutor=tutor, is_active=True, verified_at__isnull=False).order_by("-created_at").first()
            if not bank or (bank.payout_hold_until and bank.payout_hold_until > now):
                continue  # OUT-05: hold after bank change
            PayoutItem.objects.create(
                payout=payout, tutor=tutor, amount_kobo=amount, bank_account=bank,
                bank_snapshot={"bank_name": bank.bank_name, "bank_code": bank.bank_code, "last4": bank.account_last4,
                               "account_name": bank.account_name, "recipient_code": bank.recipient_code},
                transfer_reference=new_reference("PO"),
            )
            total += amount
        payout.total_kobo = total
        payout.save(update_fields=["total_kobo"])
        audit(user, "payout.create", "payout", payout.pk, after={"total_kobo": total, "items": payout.items.count()})
    return payout


def approve_payout(payout, approver, request=None):
    """OUT-03 maker-checker: the creator cannot approve. Caller must have checked a fresh 2FA code."""
    if payout.status != Payout.Status.DRAFT:
        raise ValueError("Only draft payouts can be approved")
    if payout.created_by_id and payout.created_by_id == approver.pk:
        raise PermissionError("The person who created a payout batch cannot approve it")
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(pk=payout.pk)
        payout.status, payout.approved_by, payout.approved_at = Payout.Status.APPROVED, approver, timezone.now()
        payout.save()
        for item in payout.items.filter(status=PayoutItem.Status.PENDING):
            # Earnings → payouts in transit before calling the gateway.
            ledger.transfer(f"payout:{item.transfer_reference}", "payout", f"Payout to tutor #{item.tutor_id}",
                            ledger.earnings(item.tutor), ledger.platform(AccountKind.PAYOUTS_IN_TRANSIT), item.amount_kobo, payout_item=item, user=approver)
        audit(approver, "payout.approve", "payout", payout.pk, after={"total_kobo": payout.total_kobo}, request=request)
    for item in payout.items.filter(status=PayoutItem.Status.PENDING):
        send_transfer(item)
    return payout


def send_transfer(item):
    gateway = get_gateway()
    snap = item.bank_snapshot
    item.attempts += 1
    try:
        gateway.transfer(amount_kobo=item.amount_kobo, recipient_code=snap.get("recipient_code", ""),
                         account_number=item.bank_account.account_number, bank_code=snap["bank_code"],
                         reference=item.transfer_reference, reason="TutorBridge earnings")
        item.status = PayoutItem.Status.SENT
    except GatewayError as e:
        item.failure_reason = str(e)[:255]
        log.error("Transfer %s failed to start: %s", item.transfer_reference, e)
    item.save()
    # Mark lessons covered by this payout.
    from bookings.models import EscrowStatus, Lesson

    Lesson.objects.filter(tutor=item.tutor, escrow_status=EscrowStatus.RELEASED, payout_item__isnull=True).update(
        payout_item=item, escrow_status=EscrowStatus.PAID_OUT)


def settle_transfer(item, success):
    """OUT-04: transfer webhook. Success clears in-transit; failure returns funds to tutor earnings."""
    if item.status in (PayoutItem.Status.SUCCESS, PayoutItem.Status.FAILED):
        return
    transit = ledger.platform(AccountKind.PAYOUTS_IN_TRANSIT)
    with transaction.atomic():
        if success:
            ledger.transfer(f"payoutok:{item.transfer_reference}", "payout_settled", f"Transfer {item.transfer_reference} confirmed",
                            transit, ledger.platform(AccountKind.GATEWAY_CLEARING), item.amount_kobo, payout_item=item)
            item.status = PayoutItem.Status.SUCCESS
        else:
            ledger.transfer(f"payoutfail:{item.transfer_reference}", "payout_failed", f"Transfer {item.transfer_reference} failed",
                            transit, ledger.earnings(item.tutor), item.amount_kobo, payout_item=item)
            item.status = PayoutItem.Status.FAILED
            from bookings.models import EscrowStatus

            item.lessons.update(escrow_status=EscrowStatus.RELEASED, payout_item=None)
        item.save(update_fields=["status"])
        _refresh_payout_status(item.payout)
    user = item.tutor.user
    if success:
        notify(user, "payout_sent", {"amount": naira(item.amount_kobo), "last4": item.bank_snapshot.get("last4", "")})
    else:
        notify(user, "payout_failed", {"amount": naira(item.amount_kobo)})
        _finance_alert("Payout failed", f"Transfer {item.transfer_reference} to tutor #{item.tutor_id} failed. Funds returned to tutor earnings.")


def _refresh_payout_status(payout):
    statuses = set(payout.items.exclude(status=PayoutItem.Status.REMOVED).values_list("status", flat=True))
    if statuses and statuses <= {PayoutItem.Status.SUCCESS}:
        payout.status = Payout.Status.COMPLETED
    elif PayoutItem.Status.FAILED in statuses and not ({PayoutItem.Status.PENDING, PayoutItem.Status.SENT} & statuses):
        payout.status = Payout.Status.PARTIAL
    payout.save(update_fields=["status"])


# --- Bank accounts ---------------------------------------------------------


def name_matches(account_name, first_name, last_name):
    tokens = {t.strip(".,").lower() for t in account_name.split()}
    return first_name.lower() in tokens and last_name.lower() in tokens


def add_bank_account(tutor, bank_code, bank_name, account_number):
    """TUT-08 / OUT-05: resolve account, match name, create recipient, start the 48h hold for changes."""
    gateway = get_gateway()
    user = tutor.user
    account_name = gateway.resolve_account(account_number, bank_code)
    if account_name is None and gateway.name == "fake":
        account_name = f"{user.first_name} {user.last_name}".upper()
    matched = name_matches(account_name, user.first_name, user.last_name)
    is_change = BankAccount.objects.filter(tutor=tutor, verified_at__isnull=False).exists()
    with transaction.atomic():
        BankAccount.objects.filter(tutor=tutor, is_active=True).update(is_active=False)
        bank = BankAccount.objects.create(
            tutor=tutor, bank_code=bank_code, bank_name=bank_name, account_number=account_number,
            account_last4=account_number[-4:], account_name=account_name, name_match=matched,
            verified_at=timezone.now() if matched else None,
            payout_hold_until=timezone.now() + timedelta(hours=config.get("bank_change_hold_hours")) if is_change else None,
        )
        if matched:
            bank.recipient_code = gateway.create_recipient(name=account_name, account_number=account_number, bank_code=bank_code)
            bank.save(update_fields=["recipient_code"])
        audit(user, "bank.change" if is_change else "bank.add", "tutor", tutor.pk, after={"bank": bank_name, "last4": bank.account_last4, "name_match": matched})
    return bank


# --- Reconciliation --------------------------------------------------------


def reconcile(day=None):
    """PAY-09: compare gateway records with the ledger; flag mismatches to finance."""
    from payments.models import ReconciliationRun

    day = day or (timezone.localdate() - timedelta(days=1))
    mismatches, checked = [], 0
    since = timezone.now() - timedelta(days=3)
    stale = timezone.now() - timedelta(minutes=30)
    for p in Payment.objects.filter(created_at__gte=since).exclude(status=Payment.Status.FAILED):
        checked += 1
        has_entry = ledger.LedgerTransaction.objects.filter(reference=f"payment:{p.reference}").exists()
        if p.status == Payment.Status.SUCCESS and not has_entry:
            mismatches.append({"reference": p.reference, "issue": "success without ledger entry"})
            continue
        if p.status == Payment.Status.INITIATED and p.created_at < stale:
            try:
                v = get_gateway(p.gateway).verify(p.reference)
            except GatewayError as e:
                mismatches.append({"reference": p.reference, "issue": f"verify failed: {e}"})
                continue
            if v.status == "success":
                verify_and_credit(p, source="reconciliation")  # missed webhook recovered
                mismatches.append({"reference": p.reference, "issue": "missed webhook; credited by reconciliation"})
            elif v.status == "failed" or p.created_at < timezone.now() - timedelta(days=1):
                p.status = Payment.Status.ABANDONED if v.status != "failed" else Payment.Status.FAILED
                p.save(update_fields=["status"])
    debits, credits = ledger.trial_balance()
    if debits != credits:
        mismatches.append({"issue": f"ledger out of balance: debits {debits} credits {credits}"})
    run = ReconciliationRun.objects.create(run_date=day, checked=checked, mismatches=mismatches)
    if any("credited by reconciliation" not in m["issue"] for m in mismatches):
        _finance_alert("Reconciliation mismatches", "\n".join(str(m) for m in mismatches))
    return run


def _finance_alert(title, detail):
    from accounts.models import Role, User

    for u in User.objects.filter(role__in=[Role.FINANCE, Role.SUPER], is_active=True):
        notify(u, "finance_alert", {"title": title, "detail": detail})
