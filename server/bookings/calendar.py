"""
BKG-05: private iCalendar feed of a user's lessons.

Calendar apps sync feeds through third-party servers, so the feed carries only
what's needed to plan the day: subject, child/tutor first name and area. Never
check-in codes or full addresses.
"""
import secrets
from datetime import timedelta
from datetime import timezone as dt_timezone

from django.conf import settings
from django.utils import timezone

from bookings.models import BookingStatus, Lesson, LessonStatus


def ensure_token(user, reset=False):
    if reset or not user.calendar_token:
        user.calendar_token = secrets.token_urlsafe(32)
        user.save(update_fields=["calendar_token"])
    return user.calendar_token


def _esc(text):
    return str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line):
    """RFC 5545: lines longer than 75 octets continue on the next line, indented by one space."""
    out, raw = [], line.encode("utf-8")
    while len(raw) > 75:
        cut = 75
        while cut > 0 and (raw[cut] & 0xC0) == 0x80:  # don't split a UTF-8 character
            cut -= 1
        out.append(raw[:cut].decode("utf-8"))
        raw = b" " + raw[cut:]
    out.append(raw.decode("utf-8"))
    return "\r\n".join(out)


def _dt(value):
    """UTC timestamp in iCalendar basic format; calendar apps convert to the viewer's zone."""
    return value.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def lessons_for(user):
    from accounts.models import Role

    since = timezone.now() - timedelta(days=60)
    qs = Lesson.objects.filter(scheduled_start__gte=since).select_related("booking__child", "booking__area", "tutor__user", "booking__parent").prefetch_related("booking__subjects")
    if user.role == Role.PARENT:
        return qs.filter(booking__parent__user=user, booking__status__in=[BookingStatus.OFFERED, BookingStatus.ACTIVE, BookingStatus.COMPLETED, BookingStatus.REPLACED, BookingStatus.CANCELLED])
    if user.role == Role.TUTOR:
        return qs.filter(tutor__user=user, booking__accepted_at__isnull=False)
    return qs.none()


def build_ics(user):
    from accounts.models import Role

    is_parent = user.role == Role.PARENT
    now = _dt(timezone.now())
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//TutorBridge//Lessons//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:{_esc('TutorBridge lessons')}", "X-WR-TIMEZONE:Africa/Lagos", "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
             "X-PUBLISHED-TTL:PT1H"]
    for lesson in lessons_for(user):
        b = lesson.booking
        subjects = ", ".join(s.name for s in b.subjects.all())
        if is_parent:
            summary = f"{subjects} with {lesson.tutor.user.display_name} ({b.child.first_name})"
            link = f"{settings.SITE_URL}/parent/bookings/{b.pk}"
        else:
            summary = f"{b.child.first_name} ({b.child.class_name}) · {subjects}"
            link = f"{settings.SITE_URL}/tutor/lessons/{lesson.pk}"
        cancelled = lesson.status in (LessonStatus.CANCELLED, LessonStatus.NO_SHOW)
        lines += [
            "BEGIN:VEVENT",
            f"UID:lesson-{lesson.pk}@tutorbridge",
            f"DTSTAMP:{now}",
            f"DTSTART:{_dt(lesson.scheduled_start)}",
            f"DTEND:{_dt(lesson.scheduled_end)}",
            f"SUMMARY:{_esc(('Cancelled: ' if cancelled else '') + summary)}",
            f"LOCATION:{_esc('Online' if b.is_online else (b.area.name + ', Lagos' if b.area else 'Lagos'))}",
            f"DESCRIPTION:{_esc('Lesson details and check-in: ' + link)}",
            f"URL:{link}",
            f"STATUS:{'CANCELLED' if cancelled else 'CONFIRMED'}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
