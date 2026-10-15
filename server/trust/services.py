from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Avg, Count
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from bookings.models import Booking, BookingStatus, EscrowStatus, Lesson, LessonStatus
from core import config
from core.audit import audit
from messaging.notify import notify, notify_address
from trust.models import Dispute, DisputeStatus, Incident, Review, Strike


def add_strike(tutor, reason, lesson=None, by_user=None, notes=""):
    """SAF-05: three strikes trigger a review (tutor suspended pending investigation)."""
    Strike.objects.create(tutor=tutor, reason=reason, lesson=lesson, issued_by=by_user, notes=notes)
    tutor.strikes = tutor.strike_records.count()
    tutor.save(update_fields=["strikes"])
    if tutor.strikes >= config.get("strikes_for_review"):
        from accounts.models import Role, User

        for u in User.objects.filter(role__in=[Role.SAFETY, Role.SUPER], is_active=True):
            notify(u, "finance_alert", {"title": f"Tutor #{tutor.pk} reached {tutor.strikes} strikes", "detail": f"{tutor.user.get_full_name()} needs review."}, force_channels=("inapp", "email"))


@transaction.atomic
def raise_dispute(lesson, user, reason, description):
    """SAF-01: within the dispute window, before confirmation; freezes the lesson's payout."""
    lesson = Lesson.objects.select_for_update().get(pk=lesson.pk)
    if lesson.booking.parent.user_id != user.pk and lesson.tutor.user_id != user.pk:
        raise ValidationError("Not your lesson.")
    if lesson.status not in (LessonStatus.COMPLETED, LessonStatus.IN_PROGRESS):
        raise ValidationError("Only completed lessons that haven't been confirmed yet can be disputed.")
    window = timedelta(hours=config.get("dispute_window_hours"))
    if timezone.now() > lesson.scheduled_end + window:
        raise ValidationError("The 48-hour dispute window for this lesson has closed.")
    if hasattr(lesson, "dispute"):
        raise ValidationError("A dispute is already open for this lesson.")
    dispute = Dispute.objects.create(lesson=lesson, raised_by=user, reason=reason, description=description)
    lesson.status = LessonStatus.DISPUTED
    lesson.save(update_fields=["status"])
    return dispute


@transaction.atomic
def resolve_dispute(dispute, staff, resolution, notes="", refund_kobo=0, request=None):
    """SAF-02: refund / partial / reject. Money moves out of escrow accordingly."""
    from bookings.services import _maybe_complete_booking
    from payments import services as pay

    dispute = Dispute.objects.select_for_update().get(pk=dispute.pk)
    if dispute.status == DisputeStatus.RESOLVED:
        raise ValidationError("Already resolved.")
    lesson = dispute.lesson
    if resolution == "refund":
        pay.refund_lesson(lesson, 0, f"dispute #{dispute.pk} upheld")
        lesson.status, lesson.escrow_status = LessonStatus.CANCELLED, EscrowStatus.REFUNDED
        refund_kobo = lesson.amount_kobo
    elif resolution == "partial":
        if not 0 < refund_kobo < lesson.amount_kobo:
            raise ValidationError({"refund_kobo": "Partial refund must be between zero and the lesson amount."})
        pay.partial_refund_lesson(lesson, refund_kobo, f"dispute #{dispute.pk} partial")
        lesson.status, lesson.escrow_status = LessonStatus.CONFIRMED, EscrowStatus.RELEASED
        lesson.confirmed_at = timezone.now()
    elif resolution == "reject":
        pay.release_lesson(lesson)
        lesson.status, lesson.escrow_status, lesson.confirmed_at = LessonStatus.CONFIRMED, EscrowStatus.RELEASED, timezone.now()
        refund_kobo = 0
    else:
        raise ValidationError({"resolution": "Unknown resolution."})
    lesson.save()
    dispute.status, dispute.resolution, dispute.refund_kobo = DisputeStatus.RESOLVED, resolution, refund_kobo
    dispute.notes, dispute.resolved_by, dispute.resolved_at = notes, staff, timezone.now()
    dispute.save()
    _maybe_complete_booking(lesson.booking)
    audit(staff, "dispute.resolve", "dispute", dispute.pk, after={"resolution": resolution, "refund_kobo": refund_kobo}, reason=notes, request=request)
    when = timezone.localtime(lesson.scheduled_start).strftime("%a %d %b")
    for u in (lesson.booking.parent.user, lesson.tutor.user):
        notify(u, "dispute_update", {"when": when, "status": f"resolved ({dispute.get_resolution_display()})", "notes": notes})
    return dispute


def report_incident(reporter, description, severity="urgent", lesson=None, booking=None, subject_user=None):
    """SAF-03: urgent report alerting the on-call safety officer by SMS and email immediately."""
    if lesson and not booking:
        booking = lesson.booking
    if booking and not subject_user:
        subject_user = booking.tutor.user if reporter.pk == booking.parent.user_id else booking.parent.user
    incident = Incident.objects.create(reporter=reporter, description=description, severity=severity, lesson=lesson, booking=booking, subject_user=subject_user)
    ctx = {"id": incident.pk, "reporter": reporter.get_full_name(), "role": reporter.role, "severity": severity, "description": description[:200]}
    from accounts.models import Role, User

    # On-call contact (env) plus every active safety officer. Sent synchronously via the queue's next tick (≤1 minute).
    notify_address(email=settings.SAFETY_OFFICER_EMAIL, phone=settings.SAFETY_OFFICER_PHONE or None, event="safety_alert", context=ctx)
    for officer in User.objects.filter(role__in=[Role.SAFETY], is_active=True):
        notify(officer, "safety_alert", ctx, link=f"/staff/incidents/{incident.pk}")
    return incident


@transaction.atomic
def suspend_user(user, staff, reason, ban=False, request=None):
    """SAF-04: suspend / ban; suspended tutors are hidden and their future bookings reassigned."""
    from accounts.models import Role
    from tutors.models import TutorStatus
    from tutors.services import set_status

    user.suspended_at, user.suspension_reason = timezone.now(), reason
    user.save(update_fields=["suspended_at", "suspension_reason"])
    if user.role == Role.TUTOR:
        tutor = user.tutor_profile
        set_status(tutor, TutorStatus.BANNED if ban else TutorStatus.SUSPENDED, staff, reason)
        from bookings.services import reassign

        for booking in Booking.objects.filter(tutor=tutor, status__in=[BookingStatus.OFFERED, BookingStatus.ACTIVE]):
            if booking.status == BookingStatus.OFFERED:
                reassign(booking)
            else:
                booking.status = BookingStatus.REASSIGNING
                booking.save(update_fields=["status"])
                notify(booking.parent.user, "booking_unfilled", link=f"/parent/bookings/{booking.pk}")
    from django.contrib.sessions.models import Session

    for s in Session.objects.filter(expire_date__gt=timezone.now()):
        if s.get_decoded().get("_auth_user_id") == str(user.pk):
            s.delete()
    audit(staff, "user.ban" if ban else "user.suspend", "user", user.pk, reason=reason, request=request)
    notify(user, "account_suspended", {"reason": reason})


def reinstate_user(user, staff, reason, request=None):
    from accounts.models import Role
    from tutors.models import TutorStatus
    from tutors.services import set_status

    user.suspended_at, user.suspension_reason = None, ""
    user.save(update_fields=["suspended_at", "suspension_reason"])
    if user.role == Role.TUTOR:
        set_status(user.tutor_profile, TutorStatus.ACTIVE, staff, reason)
    audit(staff, "user.reinstate", "user", user.pk, reason=reason, request=request)


def submit_review(booking, author, rating, comment=""):
    """REV-01/02/03: only verified, completed bookings (at least one confirmed lesson) can be reviewed."""
    if not 1 <= int(rating) <= 5:
        raise ValidationError({"rating": "Rating must be 1 to 5."})
    if not booking.lessons.filter(status=LessonStatus.CONFIRMED).exists():
        raise ValidationError("You can review once at least one lesson has been confirmed.")
    if author.pk == booking.parent.user_id:
        direction = "parent_to_tutor"
    elif author.pk == booking.tutor.user_id:
        direction = "tutor_to_parent"
    else:
        raise ValidationError("Not your booking.")
    period = "trial" if booking.is_trial else timezone.localdate().strftime("%Y-%m")
    review, created = Review.objects.get_or_create(booking=booking, direction=direction, period=period,
                                                   defaults={"author": author, "rating": rating, "comment": comment})
    if not created:
        raise ValidationError("You have already left a review for this period.")
    if direction == "parent_to_tutor":
        recompute_rating(booking.tutor)
    return review


def recompute_rating(tutor):
    agg = Review.objects.filter(booking__tutor=tutor, direction="parent_to_tutor", is_hidden=False).aggregate(a=Avg("rating"), c=Count("id"))
    tutor.rating_avg, tutor.rating_count = round(agg["a"] or 0, 2), agg["c"]
    tutor.save(update_fields=["rating_avg", "rating_count"])


def recompute_reliability(tutor, days=90):
    """REV-04: punctuality, no-shows, tutor cancellations and acceptance rate."""
    since = timezone.now() - timedelta(days=days)
    lessons = Lesson.objects.filter(tutor=tutor, scheduled_start__gte=since, scheduled_start__lt=timezone.now())
    late_limit = config.get("late_arrival_minutes")
    attended = lessons.filter(checkin_at__isnull=False)
    n_att = attended.count()
    n_on_time = attended.filter(late_minutes__lte=late_limit).count()
    n_noshow = lessons.filter(status=LessonStatus.NO_SHOW).count()
    n_tcancel = lessons.filter(status=LessonStatus.CANCELLED, cancelled_by="tutor").count()
    n_total = n_att + n_noshow + n_tcancel
    bookings = Booking.objects.filter(created_at__gte=since)
    accepted = bookings.filter(tutor=tutor, accepted_at__isnull=False).count()
    declined = sum(1 for ids in bookings.values_list("declined_tutor_ids", flat=True) if tutor.pk in (ids or []))
    if n_total == 0 and accepted + declined == 0:
        return tutor.reliability_score
    punctuality = n_on_time / n_att if n_att else 1
    no_show_ok = 1 - (n_noshow / n_total if n_total else 0)
    cancel_ok = 1 - (n_tcancel / n_total if n_total else 0)
    acceptance = accepted / (accepted + declined) if accepted + declined else 1
    score = round(100 * (0.35 * punctuality + 0.35 * no_show_ok + 0.15 * cancel_ok + 0.15 * acceptance))
    tutor.reliability_score = max(0, min(100, score))
    tutor.save(update_fields=["reliability_score"])
    return tutor.reliability_score


def recompute_tier(tutor):
    """TUT-15: Verified → Gold → Elite from hours, rating and reliability."""
    rules = config.get("tier_rules")
    tier = "verified"
    for name in ("gold", "elite"):
        r = rules.get(name, {})
        if float(tutor.hours_taught) >= r.get("min_hours", 1e9) and float(tutor.rating_avg) >= r.get("min_rating", 6) and tutor.reliability_score >= r.get("min_reliability", 101):
            tier = name
    if tier != tutor.tier:
        tutor.tier = tier
        tutor.save(update_fields=["tier"])
    return tier


def nightly_reputation():
    from tutors.models import TutorProfile, TutorStatus

    for tutor in TutorProfile.objects.filter(status__in=[TutorStatus.ACTIVE, TutorStatus.APPROVED]):
        recompute_rating(tutor)
        recompute_reliability(tutor)
        recompute_tier(tutor)


def parent_rating_summary(parent):
    """Aggregate of private tutor→parent ratings, shown to tutors only in aggregate (REV-02)."""
    agg = Review.objects.filter(booking__parent=parent, direction="tutor_to_parent", is_hidden=False).aggregate(a=Avg("rating"), c=Count("id"))
    return {"rating_avg": round(agg["a"], 1) if agg["a"] else None, "rating_count": agg["c"], "cancellations": parent.cancellation_count}
