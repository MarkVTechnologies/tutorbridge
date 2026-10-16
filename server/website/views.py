from django.db.models import Count, Min, Q
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from core import config
from core.models import LGA, Area, Curriculum, Level, State, Subject
from tutors.models import TutorProfile, TutorStatus
from website.models import FAQ, BlogPost, ContactMessage


@api_view(["GET"])
@permission_classes([AllowAny])
def reference_data(request):
    """Lookups the client needs for forms."""
    return Response({
        "levels": list(Level.objects.values("id", "code", "name", "min_rate_kobo", "max_rate_kobo")),
        "curricula": list(Curriculum.objects.values("id", "code", "name")),
        "subjects": list(Subject.objects.filter(is_active=True).values("id", "slug", "name")),
        "states": list(State.objects.values("id", "name")),
        "lgas": list(LGA.objects.values("id", "name", "state_id")),
        "areas": list(Area.objects.filter(is_active=True).values("id", "name", "slug", "lga_id")),
        "config": {
            "package_sizes": config.get("package_sizes"),
            "lesson_durations_minutes": config.get("lesson_durations_minutes"),
            "matching_fee_kobo": config.get("matching_fee_kobo"),
            "late_cancel_notice_hours": config.get("late_cancel_notice_hours"),
            "late_cancel_tutor_pct": config.get("late_cancel_tutor_pct"),
            "dispute_window_hours": config.get("dispute_window_hours"),
            "booking_accept_hours": config.get("booking_accept_hours"),
        },
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def faqs(request):
    qs = FAQ.objects.filter(is_published=True)
    if request.query_params.get("audience"):
        qs = qs.filter(audience__in=[request.query_params["audience"], "general"])
    return Response(list(qs.values("id", "audience", "question", "answer")))


@api_view(["GET"])
@permission_classes([AllowAny])
def blog(request):
    return Response(list(BlogPost.objects.filter(is_published=True).values("slug", "title", "excerpt", "published_at")[:50]))


@api_view(["GET"])
@permission_classes([AllowAny])
def blog_post(request, slug):
    p = get_object_or_404(BlogPost, slug=slug, is_published=True)
    return Response({"slug": p.slug, "title": p.title, "body": p.body, "published_at": p.published_at})


class ContactThrottle(AnonRateThrottle):
    rate = "5/hour"


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([ContactThrottle])
def contact(request):
    d = request.data
    if not (d.get("name") and d.get("email") and d.get("message")):
        return Response({"detail": "Name, email and message are required."}, status=400)
    ContactMessage.objects.create(name=d["name"][:120], email=d["email"][:254], phone=(d.get("phone") or "")[:20],
                                  topic=(d.get("topic") or "general")[:40], message=d["message"][:5000])
    return Response({"detail": "Thanks — we'll get back to you within one working day."}, status=201)


@api_view(["GET"])
@permission_classes([AllowAny])
def seo_page(request, subject_slug, area_slug):
    """WEB-02: data for "<Subject> home tutor in <Area>" landing pages."""
    subject = get_object_or_404(Subject, slug=subject_slug, is_active=True)
    area = get_object_or_404(Area, slug=area_slug, is_active=True)
    tutors = TutorProfile.objects.filter(status=TutorStatus.ACTIVE, subjects__subject=subject).filter(Q(areas__area=area) | Q(home_area=area)).distinct()
    stats = tutors.aggregate(n=Count("id", distinct=True), min_rate=Min("hourly_rate_kobo"))
    return Response({"subject": subject.name, "area": area.name, "tutor_count": stats["n"], "from_rate_kobo": stats["min_rate"]})


@api_view(["GET"])
@permission_classes([AllowAny])
def seo_index(request):
    """All subject × area combinations that have at least one active tutor (for the sitemap)."""
    rows = (
        TutorProfile.objects.filter(status=TutorStatus.ACTIVE)
        .values("subjects__subject__slug", "subjects__subject__name", "areas__area__slug", "areas__area__name")
        .distinct()
    )
    return Response([
        {"subject": r["subjects__subject__slug"], "subject_name": r["subjects__subject__name"], "area": r["areas__area__slug"], "area_name": r["areas__area__name"]}
        for r in rows if r["subjects__subject__slug"] and r["areas__area__slug"]
    ])


class GeoThrottle(UserRateThrottle):
    rate = "30/min"


@api_view(["GET"])
@throttle_classes([GeoThrottle])
def geo_search(request):
    """Address autocomplete for signed-in users. Each result includes the nearest TutorBridge neighbourhood, if any."""
    from core.geo import nearest_area, search

    results = []
    for r in search(request.query_params.get("q", "")):
        area = nearest_area(r["lat"], r["lng"])
        results.append({**r, "area_id": area.pk if area else None, "area_name": area.name if area else None})
    return Response(results)

