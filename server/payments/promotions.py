"""
Promo codes and referral credits (PAY-10).

The platform funds every discount and referral credit from the Promotions
expense account, so tutors are always paid their full lesson price and
finance can see exactly what marketing costs.
"""
import secrets

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from core import config
from core.money import naira, percent_of
from messaging.notify import notify
from payments import ledger
from payments.models import AccountKind, PromoCode, PromoRedemption, ReferralReward

# Bookings in these states don't count as "using" a promo code or as a previous booking.
_DEAD = ["cancelled"]
_UNPAID = ["awaiting_payment", "cancelled"]


def normalise(code):
    return (code or "").strip().upper()


def _uses(promo, parent=None):
    qs = PromoRedemption.objects.filter(promo=promo).exclude(booking__status__in=_DEAD)
    return qs.filter(parent=parent).count() if parent is not None else qs.count()


def evaluate(code, parent, lessons_total_kobo, package_size, lock=False):
    """Validate a code for this parent and basket. Returns (promo, discount_kobo); raises ValidationError with a friendly reason."""
    def bad(msg):
        raise ValidationError({"promo_code": msg})

    qs = PromoCode.objects.select_for_update() if lock else PromoCode.objects
    promo = qs.filter(code=normalise(code)).first()
    now = timezone.now()
    if promo is None or not promo.is_active:
        bad("This code isn't valid.")
    if promo.valid_from and promo.valid_from > now:
        bad("This code isn't active yet.")
    if promo.valid_until and promo.valid_until < now:
        bad("This code has expired.")
    if promo.packages_only and package_size == 1:
        bad("This code only applies to lesson packages, not single trial lessons.")
    if lessons_total_kobo < promo.min_spend_kobo:
        bad(f"This code needs a booking of at least {naira(promo.min_spend_kobo)}.")
    if promo.first_booking_only and parent.bookings.exclude(status__in=_UNPAID).exists():
        bad("This code is for your first booking only.")
    if promo.max_uses is not None and _uses(promo) >= promo.max_uses:
        bad("This code has been fully redeemed.")
    if _uses(promo, parent) >= promo.max_uses_per_parent:
        bad("You've already used this code.")
    discount = percent_of(lessons_total_kobo, promo.value) if promo.kind == PromoCode.Kind.PERCENT else promo.value
    if promo.max_discount_kobo:
        discount = min(discount, promo.max_discount_kobo)
    return promo, max(0, min(discount, lessons_total_kobo))


def record_redemption(booking):
    if booking.promo_id and booking.discount_kobo:
        PromoRedemption.objects.create(promo_id=booking.promo_id, parent=booking.parent, booking=booking, discount_kobo=booking.discount_kobo)


def fund_discount(booking):
    """Promotions expense pays the discount into the parent's wallet just before the booking is reserved in escrow."""
    if booking.discount_kobo:
        ledger.transfer(f"promo:{booking.pk}", "promo", f"Promo {booking.promo.code} on booking #{booking.pk}",
                        ledger.platform(AccountKind.PROMOTIONS), ledger.wallet(booking.parent), booking.discount_kobo, booking=booking)


def claw_back_discount(booking, lessons_refunded):
    """When lessons of a discounted booking are refunded to the wallet, take back the matching share of the discount
    so a promo can't be turned into withdrawable wallet credit."""
    if not booking.discount_kobo or lessons_refunded <= 0:
        return 0
    amount = booking.discount_kobo * lessons_refunded // booking.package_size
    amount = min(amount, ledger.balance(ledger.wallet(booking.parent)))
    if amount > 0:
        ledger.transfer(f"promo-reverse:{booking.pk}:{lessons_refunded}", "promo_reversal", f"Promo reversed for cancelled lessons (booking #{booking.pk})",
                        ledger.wallet(booking.parent), ledger.platform(AccountKind.PROMOTIONS), amount, booking=booking)
    return amount


# --- Referrals ------------------------------------------------------------

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I confusion when read aloud or typed


def referral_code_for(user):
    if not user.referral_code:
        from accounts.models import User

        while True:
            code = "".join(secrets.choice(_ALPHABET) for _ in range(8))
            if not User.objects.filter(referral_code=code).exists():
                break
        user.referral_code = code
        user.save(update_fields=["referral_code"])
    return user.referral_code


def find_referrer(code):
    from accounts.models import User

    code = normalise(code)
    if not code:
        return None
    u = User.objects.filter(referral_code=code, is_active=True, suspended_at__isnull=True).first()
    return u if u and not u.is_staff_member else None


@transaction.atomic
def grant_referral_reward(booking):
    """Called when a non-trial booking completes. Pays both sides once, the first time a referred family completes a package."""
    from accounts.models import Role

    referred = booking.parent.user
    referrer = referred.referred_by
    if (not config.get("referrals_enabled") or booking.is_trial or referrer is None or referrer.pk == referred.pk
            or referrer.suspended_at or not referrer.is_active or referrer.is_staff_member):
        return None
    if ReferralReward.objects.filter(referred=referred).exists():
        return None
    amount = config.get("referral_credit_kobo")
    if not amount:
        return None
    promos = ledger.platform(AccountKind.PROMOTIONS)
    ledger.transfer(f"referral:{referred.pk}:referred", "referral", f"Referral credit for {referred.get_full_name()}", promos, ledger.wallet(booking.parent), amount)
    if referrer.role == Role.PARENT:
        referrer_acc = ledger.wallet(referrer.parent_profile)
        where = "your wallet"
    else:
        referrer_acc = ledger.earnings(referrer.tutor_profile)
        where = "your earnings (paid out in the next weekly run)"
    ledger.transfer(f"referral:{referred.pk}:referrer", "referral", f"Referral credit: {referred.get_full_name()} completed a package", promos, referrer_acc, amount)
    reward = ReferralReward.objects.create(referrer=referrer, referred=referred, booking=booking, amount_kobo=amount)
    notify(referred, "referral_reward", {"amount": naira(amount), "detail": f"Thanks for joining through a friend — we've added {naira(amount)} to your wallet."})
    notify(referrer, "referral_reward", {"amount": naira(amount), "detail": f"{referred.first_name} completed their first package, so we've added {naira(amount)} to {where}."})
    return reward
