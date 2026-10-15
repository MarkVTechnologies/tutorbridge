"""
Booking and lesson lifecycle (BKG-*, LSN-*), with the cancellation and
dispute policies of section 4.4. All money movements go through
payments.services so the ledger stays the single source of truth.
"""
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from bookings.models import Booking, BookingStatus, EscrowStatus, Lesson, LessonStatus
from core import config
from core.audit import audit
from matching.engine import _minutes, _parse_time, week_dates
from messaging.notify import notify
from payments import ledger
from payments import services as pay

ACTIVE_LESSON_STATES = [LessonStatus.SCHEDULED, LessonStatus.IN_PROGRESS]
HOLDING_BOOKING_STATES = [BookingStatus.AWAITING_PAYMENT, BookingStatus.OFFERED, BookingStatus.ACTIVE, BookingStatus.REASSIGNING]


def commission_for(tutor):
    by_tier = config.get("commission_pct_by_tier") or {}
    return Decimal(str(by_tier.get(tutor.tier, config.get("commission_pct_standard"))))


def lesson_price(hourly_rate_kobo, minutes):
    return int(round(hourly_rate_kobo * minutes / 60))


def quote(*, parent, tutor, package_size, lesson_minutes, request=None):
    """Price a booking. Matching fee applies to a request's first (trial) booking and is credited against its first package."""
    if package_size not in config.get("package_sizes"):
        raise ValidationError({"package_size": "Unsupported package size."})
    if lesson_minutes not in config.get("lesson_durations_minutes"):
        raise ValidationError({"lesson_minutes": "Unsupported lesson duration."})
    price = lesson_price(tutor.hourly_rate_kobo, lesson_minutes)
    fee = config.get("matching_fee_kobo")
    matching_fee = matching_credit = 0
    if request is not None:
        paid_before = Booking.objects.filter(request=request).exclude(status__in=[BookingStatus.AWAITING_PAYMENT, BookingStatus.CANCELLED])
        fee_paid = paid_before.filter(matching_fee_kobo__gt=0).exists()
        credited = paid_before.filter(matching_credit_kobo__gt=0).exists()
        if package_size == 1 and not fee_paid:
            matching_fee = fee
        elif package_size > 1 and fee_paid and not credited:
            matching_credit = fee
    total = price * package_size + matching_fee - matching_credit
    return {
        "hourly_rate_kobo": tutor.hourly_rate_kobo,
        "lesson_price_kobo": price,
        "package_size": package_size,
        "lessons_total_kobo": price * package_size,
        "matching_fee_kobo": matching_fee,
        "matching_credit_kobo": matching_credit,
        "total_kobo": total,
        "commission_pct": commission_for(tutor),
        "wallet_balance_kobo": ledger.balance(ledger.wallet(parent)),
    }


def find_conflicts(tutor, slots, exclude_booking=None):
    """BKG-02: no overlapping lessons for a tutor, including a travel buffer either side."""
    buffer = timedelta(minutes=config.get("travel_buffer_minutes"))
    stale_unpaid = timezone.now() - timedelta(hours=1)
    qs = Lesson.objects.filter(tutor=tutor, status__in=ACTIVE_LESSON_STATES, booking__status__in=HOLDING_BOOKING_STATES).exclude(
        booking__status=BookingStatus.AWAITING_PAYMENT, booking__created_at__lt=stale_unpaid
    )
    if exclude_booking is not None:
        qs = qs.exclude(booking=exclude_booking)
    conflicts = []
    for start, end in slots:
        if qs.filter(scheduled_start__lt=end + buffer, scheduled_end__gt=start - buffer).exists():
            conflicts.append(start)
    blocked = set(tutor.blocked_dates.values_list("date", flat=True))
    conflicts += [start for start, _ in slots if timezone.localtime(start).date() in blocked]
    return conflicts


def check_availability(tutor, schedule, lesson_minutes):
    slots = list(tutor.availability.all())
    for slot in schedule:
        start = _minutes(_parse_time(slot["start"]))
        if not any(s.weekday == int(slot["weekday"]) and _minutes(s.start_time) <= start and _minutes(s.end_time) >= start + lesson_minutes for s in slots):
            raise ValidationError({"schedule": f"The tutor is not available on weekday {slot['weekday']} at {slot['start']}."})


@transaction.atomic
def create_booking(*, parent, tutor, child, subjects, package_size, lesson_minutes, schedule, start_date, request=None, address="", area=None, is_online=False):
    from tutors.models import TutorStatus

    if tutor.status != TutorStatus.ACTIVE or tutor.user.suspended_at:
        raise ValidationError("This tutor is not currently available.")
    if child.parent_id != parent.pk:
        raise ValidationError("Child not found.")
    if not schedule:
        raise ValidationError({"schedule": "Choose at least one weekly slot."})
    if start_date < timezone.localdate():
        raise ValidationError({"start_date": "Start date cannot be in the past."})
    check_availability(tutor, schedule, lesson_minutes)
    q = quote(parent=parent, tutor=tutor, package_size=package_size, lesson_minutes=lesson_minutes, request=request)
    slots = week_dates(start_date, schedule, package_size, lesson_minutes)
    slots = [s for s in slots if s[0] > timezone.now()]
    if len(slots) < package_size:
        raise ValidationError({"schedule": "Could not fit all lessons into the schedule."})
    conflicts = find_conflicts(tutor, slots)
    if conflicts:
        when = ", ".join(timezone.localtime(c).strftime("%a %d %b %H:%M") for c in conflicts[:3])
        raise ValidationError({"schedule": f"The tutor is already booked around: {when}."})

    booking = Booking.objects.create(
        parent=parent, tutor=tutor, child=child, request=request, is_trial=package_size == 1,
        package_size=package_size, lesson_minutes=lesson_minutes, schedule=schedule, start_date=start_date,
        hourly_rate_kobo=q["hourly_rate_kobo"], lesson_price_kobo=q["lesson_price_kobo"], commission_pct=q["commission_pct"],
        matching_fee_kobo=q["matching_fee_kobo"], matching_credit_kobo=q["matching_credit_kobo"], total_kobo=q["total_kobo"],
        address=address, area=area, is_online=is_online,
    )
    booking.subjects.set(subjects)
    _create_lessons(booking, slots)
    return booking


def _create_lessons(booking, slots):
    lessons = []
    for start, end in slots:
        lesson = Lesson(booking=booking, tutor=booking.tutor, scheduled_start=start, scheduled_end=end, amount_kobo=booking.lesson_price_kobo)
        lesson.set_codes()
        lessons.append(lesson)
    Lesson.objects.bulk_create(lessons)


def pay_from_wallet(booking):
    """Pay a booking entirely from wallet credit, if the balance covers it."""
    # total_kobo already nets off any matching credit, which reserve_booking adds to the wallet first.
    if ledger.balance(ledger.wallet(booking.parent)) < booking.total_kobo:
        raise ValidationError("Your wallet balance does not cover this booking.")
    fund_booking(booking)


@transaction.atomic
def fund_booking(booking):
    """Called once the parent's money is in their wallet: reserve it in escrow and offer the booking to the tutor."""
    booking = Booking.objects.select_for_update().get(pk=booking.pk)
    if booking.status != BookingStatus.AWAITING_PAYMENT:
        return booking
    pay.reserve_booking(booking)
    hours = config.get("booking_accept_hours")
    booking.status = BookingStatus.OFFERED
    booking.offer_expires_at = timezone.now() + timedelta(hours=hours)
    booking.save(update_fields=["status", "offer_expires_at"])
    _offer_notify(booking)
    if booking.request_id:
        from matching.models import Match, MatchStatus, RequestStatus

        booking.request.status = RequestStatus.BOOKED
        booking.request.save(update_fields=["status"])
        Match.objects.filter(request_id=booking.request_id, tutor=booking.tutor).update(status=MatchStatus.BOOKED)
    return booking


def _offer_notify(booking):
    hours = config.get("booking_accept_hours")
    notify(booking.tutor.user, "booking_offer", {
        "hours": hours, "lessons": booking.package_size,
        "subjects": ", ".join(s.name for s in booking.subjects.all()),
    }, link=f"/tutor/bookings/{booking.pk}")


@transaction.atomic
def tutor_accept(booking, tutor):
    booking = Booking.objects.select_for_update().get(pk=booking.pk)
    if booking.tutor_id != tutor.pk or booking.status != BookingStatus.OFFERED:
        raise ValidationError("This booking is no longer available.")
    booking.status, booking.accepted_at = BookingStatus.ACTIVE, timezone.now()
    booking.save(update_fields=["status", "accepted_at"])
    from messaging.models import Thread

    Thread.objects.get_or_create(booking=booking)
    first = booking.lessons.order_by("scheduled_start").first()
    notify(booking.parent.user, "booking_confirmed", {
        "tutor_name": tutor.user.display_name,
        "first_lesson": timezone.localtime(first.scheduled_start).strftime("%a %d %b, %H:%M") if first else "",
    }, link=f"/parent/bookings/{booking.pk}")
    return booking


@transaction.atomic
def tutor_decline(booking, tutor, reason=""):
    booking = Booking.objects.select_for_update().get(pk=booking.pk)
    if booking.tutor_id != tutor.pk or booking.status != BookingStatus.OFFERED:
        raise ValidationError("This booking is no longer available.")
    booking.cancel_reason = reason
    reassign(booking)
    return booking


def _next_tutor(booking):
    """Next shortlisted tutor who can take the same slots at the same or lower rate."""
    if not booking.request_id:
        return None
    from matching.models import Match, MatchStatus
    from tutors.models import TutorStatus

    excluded = set(booking.declined_tutor_ids) | {booking.tutor_id}
    matches = Match.objects.filter(request=booking.request, in_shortlist=True).exclude(status__in=[MatchStatus.DECLINED, MatchStatus.WITHDRAWN]).exclude(tutor_id__in=excluded).select_related("tutor").order_by("rank", "-score")
    slots = [(l.scheduled_start, l.scheduled_end) for l in booking.lessons.filter(status=LessonStatus.SCHEDULED)]
    for m in matches:
        t = m.tutor
        if t.status != TutorStatus.ACTIVE or t.hourly_rate_kobo > booking.hourly_rate_kobo:
            continue
        try:
            check_availability(t, booking.schedule, booking.lesson_minutes)
        except ValidationError:
            continue
        if not find_conflicts(t, slots):
            return t
    return None


@transaction.atomic
def reassign(booking):
    """BKG-03: offer to the next shortlisted tutor; reprice down to their rate and return any difference to the wallet."""
    previous = booking.tutor
    booking.declined_tutor_ids = sorted(set(booking.declined_tutor_ids) | {previous.pk})
    nxt = _next_tutor(booking)
    if nxt is None:
        booking.status = BookingStatus.REASSIGNING
        booking.offer_expires_at = None
        booking.save(update_fields=["status", "offer_expires_at", "declined_tutor_ids", "cancel_reason"])
        notify(booking.parent.user, "booking_unfilled", link=f"/parent/bookings/{booking.pk}")
        _alert_ops(f"Booking #{booking.pk} needs a tutor", "No shortlisted tutor could take this booking.")
        return booking
    new_price = lesson_price(nxt.hourly_rate_kobo, booking.lesson_minutes)
    lessons = booking.lessons.filter(status=LessonStatus.SCHEDULED)
    diff = (booking.lesson_price_kobo - new_price) * lessons.count()
    if diff > 0:
        pay.escrow_to_wallet(booking, diff, f"reprice:{booking.pk}:{nxt.pk}", f"Rate difference returned (booking #{booking.pk})")
    lessons.update(tutor=nxt, amount_kobo=new_price)
    booking.tutor = nxt
    booking.hourly_rate_kobo, booking.lesson_price_kobo = nxt.hourly_rate_kobo, new_price
    booking.commission_pct = commission_for(nxt)
    booking.status = BookingStatus.OFFERED
    booking.offer_expires_at = timezone.now() + timedelta(hours=config.get("booking_accept_hours"))
    booking.save()
    notify(booking.parent.user, "booking_reassigned", {"tutor_name": nxt.user.display_name}, link=f"/parent/bookings/{booking.pk}")
    _offer_notify(booking)
    return booking


@transaction.atomic
def cancel_booking(booking, by_user, reason=""):
    """Cancel all future lessons, returning escrow to the wallet (staff, or parent before acceptance)."""
    booking = Booking.objects.select_for_update().get(pk=booking.pk)
    for lesson in booking.lessons.filter(status=LessonStatus.SCHEDULED):
        lesson.status, lesson.cancelled_at, lesson.cancelled_by, lesson.cancel_reason = LessonStatus.CANCELLED, timezone.now(), "staff" if by_user.is_staff_member else "parent", reason[:255]
        lesson.escrow_status = EscrowStatus.REFUNDED
        lesson.save()
        if booking.status != BookingStatus.AWAITING_PAYMENT:
            pay.refund_lesson(lesson, 0, "booking cancelled")
    booking.status, booking.cancel_reason = BookingStatus.CANCELLED, reason
    booking.save(update_fields=["status", "cancel_reason"])
    audit(by_user, "booking.cancel", "booking", booking.pk, reason=reason)
    return booking


@transaction.atomic
def replace_tutor(booking, new_tutor, by_user, reason=""):
    """BKG-07: move remaining package balance to a new booking with a new tutor."""
    booking = Booking.objects.select_for_update().get(pk=booking.pk)
    if booking.status not in (BookingStatus.ACTIVE, BookingStatus.REASSIGNING, BookingStatus.OFFERED):
        raise ValidationError("This booking cannot be transferred.")
    remaining = list(booking.lessons.filter(status=LessonStatus.SCHEDULED, scheduled_start__gt=timezone.now()))
    if not remaining:
        raise ValidationError("No remaining lessons to transfer.")
    balance = sum(l.amount_kobo for l in remaining)
    for l in remaining:
        l.status, l.escrow_status, l.cancelled_at, l.cancelled_by, l.cancel_reason = LessonStatus.CANCELLED, EscrowStatus.REFUNDED, timezone.now(), "staff", "Tutor replaced"
        l.save()
    new_price = lesson_price(new_tutor.hourly_rate_kobo, booking.lesson_minutes)
    count = min(len(remaining), balance // new_price) if new_price else 0
    if count < 1:
        raise ValidationError("Remaining balance does not cover a lesson with this tutor.")
    check_availability(new_tutor, booking.schedule, booking.lesson_minutes)
    slots = week_dates(timezone.localdate() + timedelta(days=1), booking.schedule, count, booking.lesson_minutes)
    if find_conflicts(new_tutor, slots):
        raise ValidationError("The new tutor is not free for this schedule.")
    new = Booking.objects.create(
        parent=booking.parent, tutor=new_tutor, child=booking.child, request=booking.request, is_trial=False,
        package_size=count, lesson_minutes=booking.lesson_minutes, schedule=booking.schedule, start_date=slots[0][0].date(),
        hourly_rate_kobo=new_tutor.hourly_rate_kobo, lesson_price_kobo=new_price, commission_pct=commission_for(new_tutor),
        total_kobo=new_price * count, address=booking.address, area=booking.area, is_online=booking.is_online,
        replaces=booking, status=BookingStatus.OFFERED,
        offer_expires_at=timezone.now() + timedelta(hours=config.get("booking_accept_hours")),
    )
    new.subjects.set(booking.subjects.all())
    _create_lessons(new, slots)
    pay.move_escrow(booking, new, new_price * count, f"Package balance moved from booking #{booking.pk} to #{new.pk}")
    pay.escrow_to_wallet(booking, balance - new_price * count, f"replace-rest:{booking.pk}", "Unused balance after tutor replacement")
    booking.status = BookingStatus.REPLACED
    booking.save(update_fields=["status"])
    audit(by_user, "booking.replace_tutor", "booking", booking.pk, after={"new_booking": new.pk, "tutor": new_tutor.pk}, reason=reason)
    _offer_notify(new)
    return new


# --- Lessons --------------------------------------------------------------


def _lock_lesson(lesson):
    return Lesson.objects.select_for_update().select_related("booking", "booking__parent__user", "tutor__user").get(pk=lesson.pk)


MAX_CODE_ATTEMPTS = 5


def _verify_code(lesson_pk, which, code):
    """Check a lesson code. Wrong attempts are counted in their own committed update, so a later rollback can't erase them."""
    lesson = Lesson.objects.get(pk=lesson_pk)
    if lesson.code_attempts >= MAX_CODE_ATTEMPTS:
        raise ValidationError("Too many wrong codes. Contact support to unlock this lesson.")
    if not lesson.check_code(which, code):
        Lesson.objects.filter(pk=lesson_pk).update(code_attempts=F("code_attempts") + 1)
        left = MAX_CODE_ATTEMPTS - lesson.code_attempts - 1
        who = "today's check-in code" if which == "in" else "the check-out code"
        hint = f" {left} attempt{'s' if left != 1 else ''} left." if left <= 2 else ""
        raise ValidationError(f"That code is not correct. Ask the parent for {who}.{hint}")


def check_in(lesson, tutor, code, lat=None, lng=None):
    if lesson.tutor_id != tutor.pk:
        raise ValidationError("This lesson is not yours to check in.")
    _verify_code(lesson.pk, "in", code)
    return _check_in(lesson, tutor, lat, lng)


@transaction.atomic
def _check_in(lesson, tutor, lat, lng):
    lesson = _lock_lesson(lesson)
    if lesson.tutor_id != tutor.pk or lesson.booking.status != BookingStatus.ACTIVE:
        raise ValidationError("This lesson is not yours to check in.")
    if lesson.status != LessonStatus.SCHEDULED:
        raise ValidationError("This lesson has already started or is closed.")
    now = timezone.now()
    if now < lesson.scheduled_start - timedelta(minutes=30):
        raise ValidationError("You can check in from 30 minutes before the lesson starts.")
    lesson.status, lesson.checkin_at = LessonStatus.IN_PROGRESS, now
    lesson.late_minutes = max(0, int((now - lesson.scheduled_start).total_seconds() // 60))
    if lat is not None and lng is not None and tutor.location_consent:
        lesson.checkin_lat, lesson.checkin_lng = round(Decimal(str(lat)), 6), round(Decimal(str(lng)), 6)
    lesson.code_attempts = 0
    lesson.save()
    notify(lesson.booking.parent.user, "tutor_checked_in", {"tutor_name": tutor.user.display_name, "time": timezone.localtime(now).strftime("%H:%M")})
    return lesson


def check_out(lesson, tutor, code, topics, homework="", observations=""):
    if lesson.tutor_id != tutor.pk:
        raise ValidationError("This lesson is not yours.")
    if not (topics or "").strip():
        raise ValidationError({"topics": "A lesson note is required: what did you cover?"})
    _verify_code(lesson.pk, "out", code)
    return _check_out(lesson, tutor, topics, homework, observations)


@transaction.atomic
def _check_out(lesson, tutor, topics, homework, observations):
    lesson = _lock_lesson(lesson)
    if lesson.status != LessonStatus.IN_PROGRESS:
        raise ValidationError("Check in before checking out.")
    now = timezone.now()
    lesson.status, lesson.checkout_at = LessonStatus.COMPLETED, now
    lesson.note_topics, lesson.note_homework, lesson.note_observations = topics.strip(), homework.strip(), observations.strip()
    lesson.save()
    notify(lesson.booking.parent.user, "tutor_checked_out", {
        "tutor_name": tutor.user.display_name, "time": timezone.localtime(now).strftime("%H:%M"),
        "topics": lesson.note_topics, "homework": lesson.note_homework or "None",
    }, link=f"/parent/lessons/{lesson.pk}")
    return lesson


@transaction.atomic
def confirm_lesson(lesson, by_user=None, auto=False):
    """Parent confirms (or the 48h window passes): release escrow to tutor earnings."""
    lesson = _lock_lesson(lesson)
    if lesson.status != LessonStatus.COMPLETED:
        if auto:
            return lesson
        raise ValidationError("Only completed lessons can be confirmed.")
    pay.release_lesson(lesson)
    lesson.status, lesson.escrow_status, lesson.confirmed_at = LessonStatus.CONFIRMED, EscrowStatus.RELEASED, timezone.now()
    lesson.save(update_fields=["status", "escrow_status", "confirmed_at"])
    tutor = lesson.tutor
    tutor.lessons_completed += 1
    tutor.hours_taught += Decimal(str(round(lesson.duration_hours, 1)))
    tutor.save(update_fields=["lessons_completed", "hours_taught"])
    _maybe_complete_booking(lesson.booking)
    return lesson


def _maybe_complete_booking(booking):
    open_states = [LessonStatus.SCHEDULED, LessonStatus.IN_PROGRESS, LessonStatus.COMPLETED, LessonStatus.DISPUTED]
    if booking.status == BookingStatus.ACTIVE and not booking.lessons.filter(status__in=open_states).exists():
        booking.status = BookingStatus.COMPLETED
        booking.save(update_fields=["status"])


@transaction.atomic
def cancel_lesson(lesson, by_user, reason=""):
    """BKG-04 with section 4.4 policy: ≥24h notice → full credit; <24h → tutor gets late-cancellation share."""
    lesson = _lock_lesson(lesson)
    if lesson.status != LessonStatus.SCHEDULED:
        raise ValidationError("Only upcoming lessons can be cancelled.")
    is_parent = by_user.pk == lesson.booking.parent.user_id
    is_tutor = by_user.pk == lesson.tutor.user_id
    if not (is_parent or is_tutor or by_user.is_staff_member):
        raise ValidationError("Not allowed.")
    notice = lesson.scheduled_start - timezone.now()
    late = notice < timedelta(hours=config.get("late_cancel_notice_hours"))
    tutor_pct = config.get("late_cancel_tutor_pct") if (is_parent and late) else 0
    pay.refund_lesson(lesson, tutor_pct, reason or "cancelled")
    lesson.status, lesson.cancelled_at = LessonStatus.CANCELLED, timezone.now()
    lesson.cancelled_by = "parent" if is_parent else "tutor" if is_tutor else "staff"
    lesson.cancel_reason = reason[:255]
    lesson.escrow_status = EscrowStatus.REFUNDED if not tutor_pct else EscrowStatus.RELEASED
    lesson.save()
    when = timezone.localtime(lesson.scheduled_start).strftime("%a %d %b %H:%M")
    if is_parent:
        lesson.booking.parent.cancellation_count += 1
        lesson.booking.parent.save(update_fields=["cancellation_count"])
        detail = f"{tutor_pct}% of the lesson fee was paid to the tutor (late cancellation); the rest is in your wallet." if tutor_pct else "The full lesson fee is back in your wallet."
        notify(lesson.tutor.user, "lesson_cancelled", {"when": when, "detail": "The parent cancelled this lesson."})
        notify(by_user, "lesson_cancelled", {"when": when, "detail": detail})
    else:
        notify(lesson.booking.parent.user, "lesson_cancelled", {"when": when, "detail": "The full lesson fee is back in your wallet."})
        if is_tutor and late:
            from trust.services import add_strike

            add_strike(lesson.tutor, "late_cancel", lesson=lesson)
    _maybe_complete_booking(lesson.booking)
    return lesson


@transaction.atomic
def reschedule_lesson(lesson, by_user, new_start):
    lesson = _lock_lesson(lesson)
    if lesson.status != LessonStatus.SCHEDULED:
        raise ValidationError("Only upcoming lessons can be rescheduled.")
    if by_user.pk not in (lesson.booking.parent.user_id, lesson.tutor.user_id) and not by_user.is_staff_member:
        raise ValidationError("Not allowed.")
    if lesson.scheduled_start - timezone.now() < timedelta(hours=config.get("late_cancel_notice_hours")):
        raise ValidationError("Lessons can only be rescheduled with at least 24 hours' notice.")
    if new_start <= timezone.now() + timedelta(hours=2):
        raise ValidationError("Choose a time at least 2 hours from now.")
    end = new_start + (lesson.scheduled_end - lesson.scheduled_start)
    if _has_other_conflict(lesson, new_start, end):
        raise ValidationError("The tutor is not free at that time.")
    lesson.scheduled_start, lesson.scheduled_end = new_start, end
    lesson.reminder_sent = False
    lesson.save(update_fields=["scheduled_start", "scheduled_end", "reminder_sent"])
    return lesson


def _has_other_conflict(lesson, start, end):
    buffer = timedelta(minutes=config.get("travel_buffer_minutes"))
    others = Lesson.objects.filter(tutor=lesson.tutor, status__in=ACTIVE_LESSON_STATES, booking__status__in=HOLDING_BOOKING_STATES,
                                   scheduled_start__lt=end + buffer, scheduled_end__gt=start - buffer).exclude(pk=lesson.pk)
    blocked = lesson.tutor.blocked_dates.filter(date=timezone.localtime(start).date()).exists()
    return others.exists() or blocked


# --- Scheduled jobs -------------------------------------------------------


def expire_offers():
    n = 0
    for booking in Booking.objects.filter(status=BookingStatus.OFFERED, offer_expires_at__lt=timezone.now()):
        with transaction.atomic():
            b = Booking.objects.select_for_update().get(pk=booking.pk)
            if b.status == BookingStatus.OFFERED and b.offer_expires_at < timezone.now():
                b.cancel_reason = "Tutor did not respond in time"
                reassign(b)
                n += 1
    return n


def expire_unpaid():
    cutoff = timezone.now() - timedelta(hours=2)
    n = 0
    for b in Booking.objects.filter(status=BookingStatus.AWAITING_PAYMENT, created_at__lt=cutoff):
        b.lessons.filter(status=LessonStatus.SCHEDULED).update(status=LessonStatus.CANCELLED, cancel_reason="Unpaid", escrow_status=EscrowStatus.REFUNDED)
        b.status, b.cancel_reason = BookingStatus.CANCELLED, "Payment not completed"
        b.save(update_fields=["status", "cancel_reason"])
        n += 1
    return n


def send_reminders():
    """Lesson reminders ~3 hours ahead, with the parent's check-in code (MSG-05)."""
    now = timezone.now()
    qs = Lesson.objects.filter(status=LessonStatus.SCHEDULED, reminder_sent=False, booking__status=BookingStatus.ACTIVE,
                               scheduled_start__gt=now, scheduled_start__lte=now + timedelta(hours=3)).select_related("booking__parent__user", "tutor__user", "booking__area")
    for lesson in qs:
        when = timezone.localtime(lesson.scheduled_start).strftime("%a %H:%M")
        notify(lesson.booking.parent.user, "lesson_reminder", {"when": when, "code": lesson.checkin_code})
        notify(lesson.tutor.user, "lesson_reminder_tutor", {"when": when, "area": lesson.booking.area.name if lesson.booking.area else "online"})
        lesson.reminder_sent = True
        lesson.save(update_fields=["reminder_sent"])


def detect_late_and_no_shows():
    """LSN-05: alert parent + ops when a tutor is late; record a no-show after the configured threshold."""
    now = timezone.now()
    late_after = timedelta(minutes=config.get("late_arrival_minutes"))
    no_show_after = timedelta(minutes=config.get("no_show_minutes"))
    base = Lesson.objects.filter(status=LessonStatus.SCHEDULED, booking__status=BookingStatus.ACTIVE).select_related("booking__parent__user", "tutor__user")
    for lesson in base.filter(scheduled_start__lt=now - late_after, late_alert_sent=False):
        notify(lesson.booking.parent.user, "tutor_late", {"tutor_name": lesson.tutor.user.display_name, "when": timezone.localtime(lesson.scheduled_start).strftime("%H:%M")})
        _alert_ops(f"Tutor late: lesson #{lesson.pk}", f"{lesson.tutor.user.get_full_name()} has not checked in.")
        lesson.late_alert_sent = True
        lesson.save(update_fields=["late_alert_sent"])
    for lesson in base.filter(scheduled_start__lt=now - no_show_after):
        mark_no_show(lesson)


@transaction.atomic
def mark_no_show(lesson, by_user=None):
    """Tutor no-show: full credit to the parent and a strike for the tutor (section 4.4)."""
    lesson = _lock_lesson(lesson)
    if lesson.status != LessonStatus.SCHEDULED:
        return lesson
    pay.refund_lesson(lesson, 0, "tutor no-show")
    lesson.status, lesson.escrow_status = LessonStatus.NO_SHOW, EscrowStatus.REFUNDED
    lesson.save(update_fields=["status", "escrow_status"])
    from trust.services import add_strike

    add_strike(lesson.tutor, "no_show", lesson=lesson, by_user=by_user)
    notify(lesson.booking.parent.user, "no_show", {"when": timezone.localtime(lesson.scheduled_start).strftime("%a %d %b %H:%M")})
    _maybe_complete_booking(lesson.booking)
    return lesson


def auto_confirm():
    """LSN-04: auto-confirm completed lessons once the dispute window has passed with no dispute."""
    window = timedelta(hours=config.get("dispute_window_hours"))
    n = 0
    for lesson in Lesson.objects.filter(status=LessonStatus.COMPLETED, checkin_at__isnull=False, scheduled_end__lt=timezone.now() - window):
        confirm_lesson(lesson, auto=True)
        n += 1
    # A tutor who checked in but never checked out: close it so the lesson can be confirmed or disputed.
    stale = timezone.now() - timedelta(hours=6)
    for lesson in Lesson.objects.filter(status=LessonStatus.IN_PROGRESS, scheduled_end__lt=stale):
        lesson.status = LessonStatus.COMPLETED
        lesson.checkout_at = lesson.scheduled_end
        lesson.note_observations = (lesson.note_observations + "\n[Auto-closed: tutor did not check out]").strip()
        lesson.save(update_fields=["status", "checkout_at", "note_observations"])
    return n


def _alert_ops(title, detail):
    from accounts.models import Role, User

    for u in User.objects.filter(role__in=[Role.OPS], is_active=True):
        notify(u, "finance_alert", {"title": title, "detail": detail}, force_channels=("inapp",))
