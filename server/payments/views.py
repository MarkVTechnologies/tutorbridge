import json
from datetime import datetime

import pyotp
from django.conf import settings
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts.models import OTPCode
from accounts.permissions import IsParent, IsTutor, IsVerifiedUser
from bookings.models import EscrowStatus, Lesson, LessonStatus
from core.money import split_commission
from core.throttles import OTPThrottle, PaymentThrottle
from messaging.notify import notify
from payments import ledger, services
from payments.gateways import GATEWAYS, FakeGateway, GatewayError, InvalidPayload, get_gateway
from payments.models import AccountKind, BankAccount, LedgerEntry, Payment, PayoutItem, SavedCard
from tutors.services import check
from vetting.models import CheckStatus, CheckType


def _payment_json(p):
    return {
        "reference": p.reference, "amount_kobo": p.amount_kobo, "status": p.status, "gateway": p.gateway, "channel": p.channel,
        "booking": p.booking_id, "created_at": p.created_at, "verified_at": p.verified_at,
    }


@api_view(["POST"])
@permission_classes([IsParent, IsVerifiedUser])
@throttle_classes([PaymentThrottle])
def topup(request):
    try:
        amount = int(request.data.get("amount_kobo", 0))
    except (TypeError, ValueError):
        amount = 0
    if not 100_000 <= amount <= 500_000_000:
        raise ValidationError({"amount_kobo": "Top up between ₦1,000 and ₦5,000,000."})
    p = services.start_checkout(request.user.parent_profile, amount)
    return Response({**_payment_json(p), "authorization_url": p.authorization_url}, status=201)


@api_view(["GET"])
@permission_classes([IsParent])
def payments_list(request):
    qs = Payment.objects.filter(parent__user=request.user).order_by("-created_at")[:100]
    return Response([_payment_json(p) for p in qs])


@api_view(["GET"])
@permission_classes([IsParent])
def payment_status(request, reference):
    """Read-only: the browser redirect never credits anything (PAY-02)."""
    p = get_object_or_404(Payment, reference=reference, parent__user=request.user)
    return Response(_payment_json(p))


@api_view(["GET"])
@permission_classes([IsParent])
def receipt(request, reference):
    from core.pdf import receipt_pdf

    p = get_object_or_404(Payment, reference=reference, parent__user=request.user, status=Payment.Status.SUCCESS)
    resp = HttpResponse(receipt_pdf(p), content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="receipt-{p.reference}.pdf"'
    return resp


@csrf_exempt
def webhook(request, gateway):
    """Gateway webhooks: raw body + signature check; always 200 on valid-but-ignored events so the gateway stops retrying."""
    if request.method != "POST":
        return HttpResponse(status=405)
    if gateway not in GATEWAYS or (gateway == "fake" and not settings.DEBUG):
        return HttpResponse(status=404)
    try:
        ok = services.handle_webhook(gateway, request.body, request.headers)
    except InvalidPayload:
        return HttpResponse(status=400)
    except Exception:  # noqa: BLE001 - transient failure (e.g. verify call timed out): 5xx so the gateway retries
        return HttpResponse(status=500)
    return HttpResponse(status=200 if ok else 401)


@api_view(["POST"])
@permission_classes([IsParent])
def fake_complete(request):
    """DEBUG only: simulate the gateway confirming a payment by sending ourselves a signed webhook."""
    if not settings.DEBUG or settings.PAYMENT_GATEWAY != "fake":
        return Response(status=404)
    p = get_object_or_404(Payment, reference=request.data.get("reference"), parent__user=request.user, gateway="fake")
    p.raw_verification = {**(p.raw_verification or {}), "fake_paid": True}
    p.save(update_fields=["raw_verification"])
    body = json.dumps({"event": "charge.success", "reference": p.reference, "id": p.reference}).encode()
    services.handle_webhook("fake", body, {"X-Fake-Signature": FakeGateway.sign(body)})
    p.refresh_from_db()
    return Response(_payment_json(p))


@api_view(["GET"])
@permission_classes([IsParent])
def wallet(request):
    parent = request.user.parent_profile
    acc = ledger.wallet(parent)
    entries = LedgerEntry.objects.filter(account=acc).select_related("transaction").order_by("-created_at")[:100]
    escrow_total = sum(ledger.balance(a) for a in ledger.LedgerAccount.objects.filter(kind=AccountKind.ESCROW, booking__parent=parent))
    return Response({
        "balance_kobo": ledger.balance(acc),
        "in_escrow_kobo": escrow_total,
        "entries": [{"date": e.created_at, "description": e.transaction.description, "kind": e.transaction.kind,
                     "amount_kobo": e.credit_kobo - e.debit_kobo} for e in entries],
        "saved_cards": [{"id": c.pk, "brand": c.brand, "last4": c.last4, "exp_month": c.exp_month, "exp_year": c.exp_year, "added": c.created_at}
                        for c in SavedCard.objects.filter(parent=parent, is_active=True)],
    })


@api_view(["DELETE"])
@permission_classes([IsParent])
def remove_saved_card(request, pk):
    """Parents can withdraw consent to automatic charges at any time."""
    card = get_object_or_404(SavedCard, pk=pk, parent__user=request.user, is_active=True)
    card.is_active = False
    card.save(update_fields=["is_active"])
    from core.audit import audit

    audit(request.user, "card.remove", "saved_card", card.pk, request=request)
    return Response(status=204)


# --- Tutor earnings (OUT-01) ----------------------------------------------


@api_view(["GET"])
@permission_classes([IsTutor])
def earnings(request):
    tutor = request.user.tutor_profile
    pending = 0
    lessons = Lesson.objects.filter(tutor=tutor).exclude(status=LessonStatus.CANCELLED, escrow_status=EscrowStatus.REFUNDED).select_related("booking", "booking__child").order_by("-scheduled_start")[:200]
    rows = []
    for l in lessons:
        net, _ = split_commission(l.amount_kobo, l.booking.commission_pct)
        if l.escrow_status == EscrowStatus.RESERVED and l.status in (LessonStatus.IN_PROGRESS, LessonStatus.COMPLETED, LessonStatus.DISPUTED):
            pending += net
        rows.append({"id": l.pk, "date": l.scheduled_start, "child": l.booking.child.first_name, "status": l.status,
                     "escrow_status": l.escrow_status, "net_kobo": net})
    paid = PayoutItem.objects.filter(tutor=tutor, status=PayoutItem.Status.SUCCESS).aggregate(s=Sum("amount_kobo"))["s"] or 0
    in_transit = PayoutItem.objects.filter(tutor=tutor, status__in=[PayoutItem.Status.PENDING, PayoutItem.Status.SENT]).aggregate(s=Sum("amount_kobo"))["s"] or 0
    payouts = PayoutItem.objects.filter(tutor=tutor).order_by("-updated_at")[:20]
    return Response({
        "pending_kobo": pending,  # delivered, inside the dispute window
        "cleared_kobo": ledger.balance(ledger.earnings(tutor)),  # payable at the next payout run
        "in_transit_kobo": in_transit,
        "paid_kobo": paid,
        "lessons": rows,
        "payouts": [{"date": p.updated_at, "amount_kobo": p.amount_kobo, "status": p.status, "bank": f"{p.bank_snapshot.get('bank_name')} ****{p.bank_snapshot.get('last4')}"} for p in payouts],
    })


@api_view(["GET"])
@permission_classes([IsTutor])
def statement(request):
    from core.pdf import statement_pdf

    try:
        m = datetime.strptime(request.query_params.get("month", ""), "%Y-%m")
    except ValueError as e:
        raise ValidationError({"month": "Use YYYY-MM."}) from e
    resp = HttpResponse(statement_pdf(request.user.tutor_profile, m.year, m.month), content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="statement-{m:%Y-%m}.pdf"'
    return resp


# --- Bank account (TUT-08, OUT-05) ----------------------------------------


@api_view(["GET"])
@permission_classes([IsTutor])
def banks(request):
    try:
        return Response(get_gateway().list_banks())
    except GatewayError as e:
        return Response({"detail": str(e)}, status=502)


def _bank_json(b):
    return {"id": b.pk, "bank_name": b.bank_name, "account_last4": b.account_last4, "account_name": b.account_name,
            "name_match": b.name_match, "verified_at": b.verified_at, "payout_hold_until": b.payout_hold_until}


@api_view(["POST"])
@permission_classes([IsTutor])
@throttle_classes([OTPThrottle])
def bank_change_otp(request):
    notify(request.user, "bank_change_otp", {"code": OTPCode.issue(request.user, "bank_change")})
    return Response({"detail": "Code sent to your phone."})


@api_view(["GET", "POST"])
@permission_classes([IsTutor])
@throttle_classes([OTPThrottle])
def bank_account(request):
    tutor = request.user.tutor_profile
    current = BankAccount.objects.filter(tutor=tutor, is_active=True).first()
    if request.method == "GET":
        return Response(_bank_json(current) if current else None)
    if current and current.verified_at:
        # Changing an existing account requires 2FA (if enabled) or an SMS OTP.
        code = str(request.data.get("code", ""))
        user = request.user
        ok = (user.totp_enabled and pyotp.TOTP(user.totp_secret).verify(code, valid_window=1)) or OTPCode.verify(user, "bank_change", code)
        if not ok:
            raise ValidationError({"code": "Enter the code we sent to your phone."})
    number = "".join(ch for ch in str(request.data.get("account_number", "")) if ch.isdigit())
    if len(number) != 10:
        raise ValidationError({"account_number": "Account numbers have 10 digits."})
    try:
        bank = services.add_bank_account(tutor, str(request.data.get("bank_code", "")), str(request.data.get("bank_name", ""))[:80], number)
    except GatewayError as e:
        raise ValidationError({"account_number": f"We couldn't verify this account: {e}"}) from e
    c = check(tutor, CheckType.BANK)
    c.status = CheckStatus.PASSED if bank.name_match else CheckStatus.MANUAL_REVIEW
    c.result = {"account_name": bank.account_name, "bank": bank.bank_name, "last4": bank.account_last4}
    c.save()
    return Response(_bank_json(bank), status=201)


# --- Referrals (PAY-10) ------------------------------------------------------


@api_view(["GET"])
def referrals(request):
    from core import config
    from payments.models import ReferralReward
    from payments.promotions import referral_code_for

    user = request.user
    if user.is_staff_member:
        return Response({"detail": "Referrals are for parents and tutors."}, status=403)
    code = referral_code_for(user)
    rewards = ReferralReward.objects.filter(referrer=user)
    return Response({
        "code": code,
        "link": f"{settings.SITE_URL}/signup?ref={code}",
        "enabled": config.get("referrals_enabled"),
        "credit_kobo": config.get("referral_credit_kobo"),
        "invited": user.referrals.count(),
        "rewarded": rewards.count(),
        "earned_kobo": sum(r.amount_kobo for r in rewards),
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def referral_lookup(request, code):
    """Shown on the signup page: who invited you (first name only)."""
    from payments.promotions import find_referrer

    u = find_referrer(code)
    return Response({"valid": bool(u), "first_name": u.first_name if u else None})

