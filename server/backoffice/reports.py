"""
ADM-07: pilot reports — the PRD section 20 success metrics against their pilot targets,
weekly trends, parent cohort retention and fill rate by area.

Built for pilot scale (thousands of rows): grouping happens in Python on local dates so it
behaves the same on SQLite and MySQL (no __date lookups, see core/dates.py).
"""
from collections import defaultdict
from datetime import timedelta
from statistics import median

from django.db.models import Count, Sum
from django.utils import timezone

from bookings.models import Booking, BookingStatus, Lesson, LessonStatus
from core.dates import day_start
from matching.models import LessonRequest
from payments import ledger
from payments.models import AccountKind, LedgerEntry, Payout
from trust.models import Incident, Review

PAID = [BookingStatus.OFFERED, BookingStatus.ACTIVE, BookingStatus.COMPLETED, BookingStatus.REASSIGNING, BookingStatus.REPLACED]
DELIVERED = [LessonStatus.COMPLETED, LessonStatus.CONFIRMED]
FILL_WINDOW = timedelta(hours=48)


def _pct(num, den):
    return round(100 * num / den, 1) if den else None


def _metric(key, label, value, target, unit, n, higher_is_better=True, target_label=None, hint=""):
    if value is None:
        ok = None
    elif isinstance(target, tuple):
        ok = target[0] <= value <= target[1]
    else:
        ok = value >= target if higher_is_better else value <= target
    if target_label is None:
        target_label = f"{target[0]}–{target[1]}{unit}" if isinstance(target, tuple) else f"{'≥' if higher_is_better else '≤'} {target}{unit}"
    return {"key": key, "label": label, "value": value, "unit": unit, "target": target_label, "on_target": ok, "n": n, "hint": hint}


def _was_filled(req, bookings_by_request):
    return any(b.created_at - req.created_at <= FILL_WINDOW for b in bookings_by_request.get(req.pk, ()))


def scorecard(since, now):
    # Fill rate: requests old enough to judge (48h) that got a paid booking within 48 hours.
    reqs = list(LessonRequest.objects.filter(created_at__gte=since, created_at__lte=now - FILL_WINDOW).only("id", "created_at"))
    by_req = defaultdict(list)
    for b in Booking.objects.filter(request__in=[r.pk for r in reqs], status__in=PAID).only("id", "request_id", "created_at"):
        by_req[b.request_id].append(b)
    filled = sum(1 for r in reqs if _was_filled(r, by_req))

    shortlist_hours = [
        (pub - created).total_seconds() / 3600
        for created, pub in LessonRequest.objects.filter(created_at__gte=since, shortlist_published_at__isnull=False).values_list("created_at", "shortlist_published_at")
    ]

    # Trial → package: completed trials, converted if the same child booked a paid package afterwards.
    trials = list(Booking.objects.filter(is_trial=True, status=BookingStatus.COMPLETED, created_at__gte=since).only("id", "child_id", "created_at"))
    converted = sum(1 for t in trials if Booking.objects.filter(child_id=t.child_id, is_trial=False, status__in=PAID, created_at__gt=t.created_at).exists())

    # Renewal: packages that finished in the period, renewed if a follow-on package with the same tutor was paid.
    finished = list(Booking.objects.filter(is_trial=False, status=BookingStatus.COMPLETED, lessons__scheduled_end__gte=since).distinct()
                    .only("id", "child_id", "tutor_id", "created_at"))
    renewed = sum(1 for b in finished if Booking.objects.filter(child_id=b.child_id, tutor_id=b.tutor_id, is_trial=False, status__in=PAID,
                                                                created_at__gt=b.created_at).exists())

    lessons = Lesson.objects.filter(scheduled_start__gte=since, scheduled_end__lte=now).exclude(status=LessonStatus.CANCELLED)
    n_lessons = lessons.count()
    delivered = lessons.filter(status__in=DELIVERED).count()
    no_shows = lessons.filter(status=LessonStatus.NO_SHOW).count()

    payouts = list(Payout.objects.filter(created_at__gte=since).exclude(status=Payout.Status.CANCELLED).only("status", "created_at", "approved_at"))
    on_time = sum(1 for p in payouts if p.status == Payout.Status.COMPLETED and p.approved_at
                  and timezone.localdate(p.approved_at) == timezone.localdate(p.created_at))

    ratings = list(Review.objects.filter(direction="parent_to_tutor", is_hidden=False, created_at__gte=since).values_list("rating", flat=True))

    revenue = LedgerEntry.objects.filter(account=ledger.platform(AccountKind.PLATFORM_REVENUE), created_at__gte=since).aggregate(c=Sum("credit_kobo"), d=Sum("debit_kobo"))
    revenue_kobo = (revenue["c"] or 0) - (revenue["d"] or 0)
    confirmed = Lesson.objects.filter(confirmed_at__gte=since).aggregate(s=Sum("amount_kobo"), n=Count("id"))
    gross_kobo = confirmed["s"] or 0

    serious = Incident.objects.filter(created_at__gte=since, severity__in=["urgent", "high"])
    late_ack = sum(1 for i in serious.only("created_at", "acknowledged_at")
                   if (i.acknowledged_at or now) - i.created_at > timedelta(hours=24))

    return [
        _metric("fill_rate", "Fill rate", _pct(filled, len(reqs)), 80, "%", len(reqs), hint="Requests with a paid booking within 48 hours"),
        _metric("time_to_shortlist", "Time to shortlist", round(median(shortlist_hours), 1) if shortlist_hours else None, 24, " h",
                len(shortlist_hours), higher_is_better=False, hint="Median, request to published shortlist"),
        _metric("trial_conversion", "Trial → package", _pct(converted, len(trials)), 50, "%", len(trials), hint="Completed trials followed by a paid package"),
        _metric("renewal_rate", "Package renewal", _pct(renewed, len(finished)), 65, "%", len(finished), hint="Finished packages renewed with the same tutor"),
        _metric("lesson_completion", "Lesson completion", _pct(delivered, n_lessons), 95, "%", n_lessons, hint="Past lessons delivered (cancellations excluded)"),
        _metric("no_show_rate", "Tutor no-shows", _pct(no_shows, n_lessons), 2, "%", n_lessons, higher_is_better=False),
        _metric("payout_on_time", "Payouts on time", _pct(on_time, len(payouts)), 100, "%", len(payouts), target_label="100%",
                hint="Batches approved and paid the day they were created"),
        _metric("avg_rating", "Average rating", round(sum(ratings) / len(ratings), 2) if ratings else None, 4.5, " / 5", len(ratings),
                hint="Parents rating tutors"),
        _metric("take_rate", "Take rate", _pct(revenue_kobo, gross_kobo), (18, 22), "%", confirmed["n"], hint="Platform revenue ÷ confirmed lesson value"),
        _metric("safety_late", "Serious incidents not acknowledged in 24 h", late_ack, 0, "", serious.count(), higher_is_better=False,
                target_label="0", hint=f"{serious.count()} urgent/high incidents in the period"),
    ]


def weekly(weeks, now):
    """Per local week (Monday start): requests, paid bookings, delivered lessons, GMV and 48h fill rate."""
    today = timezone.localdate(now)
    first_monday = today - timedelta(days=today.weekday(), weeks=weeks - 1)
    start = day_start(first_monday)
    rows = {first_monday + timedelta(weeks=i): {"requests": 0, "filled": 0, "judged": 0, "bookings": 0, "lessons": 0, "gmv_kobo": 0} for i in range(weeks)}

    def week_of(dt):
        d = timezone.localdate(dt)
        return d - timedelta(days=d.weekday())

    reqs = list(LessonRequest.objects.filter(created_at__gte=start).only("id", "created_at"))
    by_req = defaultdict(list)
    for b in Booking.objects.filter(request__in=[r.pk for r in reqs], status__in=PAID).only("id", "request_id", "created_at"):
        by_req[b.request_id].append(b)
    for r in reqs:
        row = rows[week_of(r.created_at)]
        row["requests"] += 1
        if now - r.created_at >= FILL_WINDOW:
            row["judged"] += 1
            row["filled"] += _was_filled(r, by_req)
    for created in Booking.objects.filter(created_at__gte=start, status__in=PAID).values_list("created_at", flat=True):
        rows[week_of(created)]["bookings"] += 1
    for when, amount in Lesson.objects.filter(scheduled_start__gte=start, scheduled_start__lte=now, status__in=DELIVERED).values_list("scheduled_start", "amount_kobo"):
        row = rows[week_of(when)]
        row["lessons"] += 1
        row["gmv_kobo"] += amount
    return [{"week": wk.isoformat(), **{k: v for k, v in r.items() if k not in ("filled", "judged")}, "fill_rate": _pct(r["filled"], r["judged"])}
            for wk, r in sorted(rows.items())]


def _month_index(d):
    return d.year * 12 + d.month - 1


def cohorts(months, now):
    """Parent retention: cohort = month of first delivered lesson; cell = % of the cohort with a delivered lesson in month +k."""
    current = _month_index(timezone.localdate(now))
    active = defaultdict(set)  # parent_id -> {month index}
    for parent_id, when in Lesson.objects.filter(status__in=DELIVERED, scheduled_start__lte=now).values_list("booking__parent_id", "scheduled_start"):
        active[parent_id].add(_month_index(timezone.localdate(when)))
    groups = defaultdict(list)
    for parent_id, ms in active.items():
        first = min(ms)
        if first > current - months:
            groups[first].append(ms)
    out = []
    for first in sorted(groups):
        members = groups[first]
        span = current - first + 1
        out.append({
            "cohort": f"{first // 12}-{first % 12 + 1:02d}", "size": len(members),
            "retention": [_pct(sum(1 for ms in members if first + k in ms), len(members)) for k in range(span)],
        })
    return out


def by_area(since, now):
    reqs = list(LessonRequest.objects.filter(created_at__gte=since, created_at__lte=now - FILL_WINDOW, is_online=False).select_related("area").only("id", "created_at", "area__name"))
    by_req = defaultdict(list)
    for b in Booking.objects.filter(request__in=[r.pk for r in reqs], status__in=PAID).only("id", "request_id", "created_at"):
        by_req[b.request_id].append(b)
    agg = defaultdict(lambda: [0, 0])
    for r in reqs:
        agg[r.area.name][0] += 1
        agg[r.area.name][1] += _was_filled(r, by_req)
    rows = [{"area": a, "requests": n, "filled": f, "fill_rate": _pct(f, n)} for a, (n, f) in agg.items()]
    return sorted(rows, key=lambda r: -r["requests"])[:15]


def pilot_report(days=30, weeks=12, months=6):
    now = timezone.now()
    since = now - timedelta(days=days)
    return {
        "generated_at": now, "days": days,
        "scorecard": scorecard(since, now),
        "weekly": weekly(weeks, now),
        "cohorts": cohorts(months, now),
        "areas": by_area(since, now),
    }
