"""
Matching engine (section 12, REQ-03).

Hard filters run first; a transparent weighted score (weights tunable in the
admin console) ranks what remains.
"""
import math
from datetime import date, datetime, time, timedelta

from django.db.models import Avg, Q

from core import config
from tutors.models import TutorProfile, TutorStatus


def haversine_km(lat1, lng1, lat2, lng2):
    if None in (lat1, lng1, lat2, lng2):
        return None
    lat1, lng1, lat2, lng2 = map(lambda v: math.radians(float(v)), (lat1, lng1, lat2, lng2))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def _parse_time(value):
    return value if isinstance(value, time) else datetime.strptime(value, "%H:%M").time()


def _minutes(t):
    return t.hour * 60 + t.minute


def availability_overlap(tutor, schedule, lesson_minutes):
    """Fraction (0..1) of requested weekly slots fully covered by the tutor's availability grid."""
    if not schedule:
        return 0.0
    slots = list(tutor.availability.all())
    covered = 0
    for slot in schedule:
        start = _minutes(_parse_time(slot["start"]))
        end = start + lesson_minutes
        if any(s.weekday == int(slot["weekday"]) and _minutes(s.start_time) <= start and _minutes(s.end_time) >= end for s in slots):
            covered += 1
    return covered / len(schedule)


def distance_km(tutor, request):
    """Straight-line km from the lesson address (or its neighbourhood centre) to the tutor's home (or their area's centre)."""
    lat = request.lat if request.lat is not None else request.area.lat
    lng = request.lng if request.lng is not None else request.area.lng
    if tutor.home_lat is not None and tutor.home_lng is not None:
        return haversine_km(lat, lng, tutor.home_lat, tutor.home_lng)
    home = tutor.home_area
    if home is None:
        return None
    return haversine_km(lat, lng, home.lat, home.lng)


def candidates(request):
    """Hard filters (section 12)."""
    subjects = list(request.subjects.all())
    level = request.child.level
    qs = (
        TutorProfile.objects.filter(status=TutorStatus.ACTIVE, user__suspended_at__isnull=True)
        .filter(Q(background_valid_until__gte=date.today()))
        .select_related("user", "home_area")
        .prefetch_related("availability", "areas", "curricula", "subjects")
    )
    for subject in subjects:
        qs = qs.filter(subjects__subject=subject, subjects__level=level)
    prefs = request.preferences or {}
    if prefs.get("gender") in ("female", "male"):
        qs = qs.filter(user__gender=prefs["gender"])
    if prefs.get("special_needs") or request.child.special_needs:
        qs = qs.filter(accepts_special_needs=True)
    if request.is_online:
        qs = qs.filter(offers_online=True)
    curriculum = request.child.curriculum
    qs = qs.filter(curricula=curriculum)
    return qs.distinct()


def score_tutor(tutor, request, weights=None):
    weights = weights or config.get("match_weights")
    min_avail = config.get("match_min_availability_pct") / 100

    overlap = availability_overlap(tutor, request.schedule, request.lesson_minutes)
    if overlap < min_avail:
        return None, {"rejected": "availability"}

    serves_area = request.is_online or any(a.area_id == request.area_id for a in tutor.areas.all())
    dist = distance_km(tutor, request)
    if not serves_area and (dist is None or dist > tutor.max_travel_km):
        return None, {"rejected": "distance"}

    distance_score = 1.0 if request.is_online else (1.0 if dist is None else max(0.0, 1 - dist / max(tutor.max_travel_km, 1)))
    if serves_area:
        distance_score = max(distance_score, 0.7)

    rating_score = float(tutor.rating_avg) / 5 if tutor.rating_count else 0.8  # neutral prior for new tutors
    reliability_score = tutor.reliability_score / 100

    budget = request.budget_max_kobo
    if not budget or tutor.hourly_rate_kobo <= budget:
        rate_score = 1.0
    else:
        over = (tutor.hourly_rate_kobo - budget) / budget
        rate_score = max(0.0, 1 - over * 2)  # 50% over budget scores zero

    subject_ids = [s.id for s in request.subjects.all()]
    test = tutor.subjects.filter(subject_id__in=subject_ids, level=request.child.level).aggregate(a=Avg("test_score"))["a"]
    test_score = (test or 0) / 100

    parts = {
        "availability": overlap,
        "distance": distance_score,
        "rating": rating_score,
        "reliability": reliability_score,
        "rate_fit": rate_score,
        "test_score": test_score,
    }
    total_weight = sum(weights.values()) or 1
    score = sum(parts[k] * weights.get(k, 0) for k in parts) / total_weight * 100

    # Temporary visibility boost so new tutors can earn their first reviews.
    if tutor.lessons_completed < config.get("new_tutor_boost_lessons"):
        score += config.get("new_tutor_boost")
        parts["new_tutor_boost"] = True

    breakdown = {k: round(v, 3) for k, v in parts.items() if not isinstance(v, bool)}
    breakdown["distance_km"] = round(dist, 1) if dist is not None else None
    breakdown["new_tutor_boost"] = parts.get("new_tutor_boost", False)
    return round(min(score, 100), 2), breakdown


def rank(request, limit=20):
    results = []
    for tutor in candidates(request):
        score, breakdown = score_tutor(tutor, request)
        if score is not None:
            results.append((tutor, score, breakdown))
    results.sort(key=lambda r: r[1], reverse=True)
    return results[:limit]


def run_matching(request):
    """Create/refresh suggested matches for a request. Ops reviews before publishing (REQ-04)."""
    from matching.models import Match, MatchStatus, RequestStatus

    ranked = rank(request)
    for i, (tutor, score, breakdown) in enumerate(ranked):
        Match.objects.update_or_create(
            request=request, tutor=tutor,
            defaults={"score": score, "breakdown": breakdown, "rank": i + 1},
        )
    if request.requested_tutor_id and not any(t.pk == request.requested_tutor_id for t, _, _ in ranked):
        # Parent asked for a specific tutor who failed a filter: still show them to ops, flagged.
        Match.objects.get_or_create(request=request, tutor_id=request.requested_tutor_id,
                                    defaults={"score": 0, "breakdown": {"note": "Requested by parent; failed one or more filters"}, "rank": 99})
    if request.status == RequestStatus.SUBMITTED:
        request.status = RequestStatus.MATCHING
        request.save(update_fields=["status"])
    return Match.objects.filter(request=request).exclude(status=MatchStatus.WITHDRAWN)


def week_dates(start_date, schedule, count, lesson_minutes):
    """Expand recurring weekly slots into `count` lesson datetimes starting on/after start_date."""
    from django.utils import timezone

    tz = timezone.get_current_timezone()
    out = []
    day = start_date
    slots = sorted(schedule, key=lambda s: (int(s["weekday"]), s["start"]))
    guard = 0
    while len(out) < count and guard < 400:
        for slot in slots:
            if day.weekday() == int(slot["weekday"]):
                start = timezone.make_aware(datetime.combine(day, _parse_time(slot["start"])), tz)
                out.append((start, start + timedelta(minutes=lesson_minutes)))
                if len(out) >= count:
                    break
        day += timedelta(days=1)
        guard += 1
    return out
