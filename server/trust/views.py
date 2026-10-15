from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from bookings.models import Booking
from trust import services
from trust.models import Dispute, Review


@api_view(["GET", "POST"])
def reviews(request):
    if request.method == "POST":
        booking = get_object_or_404(Booking.objects.filter(Q(parent__user=request.user) | Q(tutor__user=request.user)), pk=request.data.get("booking"))
        r = services.submit_review(booking, request.user, int(request.data.get("rating", 0)), (request.data.get("comment") or "")[:2000])
        return Response({"id": r.pk, "rating": r.rating, "period": r.period}, status=201)
    qs = Review.objects.filter(author=request.user)
    if request.query_params.get("booking"):
        qs = qs.filter(booking_id=request.query_params["booking"])
    return Response([{"id": r.pk, "booking": r.booking_id, "rating": r.rating, "comment": r.comment, "period": r.period, "created_at": r.created_at} for r in qs])


@api_view(["POST"])
def incident(request):
    """Safety report not tied to a specific lesson (e.g. from a booking page or the account menu)."""
    description = (request.data.get("description") or "").strip()
    if not description:
        raise ValidationError({"description": "Describe what is happening."})
    booking = None
    if request.data.get("booking"):
        booking = get_object_or_404(Booking.objects.filter(Q(parent__user=request.user) | Q(tutor__user=request.user)), pk=request.data["booking"])
    i = services.report_incident(request.user, description, request.data.get("severity", "urgent"), booking=booking)
    return Response({"id": i.pk, "detail": "Our safety team has been alerted. If anyone is in immediate danger, call 112."}, status=201)


@api_view(["GET"])
def my_disputes(request):
    qs = Dispute.objects.filter(Q(lesson__booking__parent__user=request.user) | Q(lesson__tutor__user=request.user)).select_related("lesson")
    return Response([{
        "id": d.pk, "lesson": d.lesson_id, "lesson_date": d.lesson.scheduled_start, "reason": d.reason, "status": d.status,
        "resolution": d.resolution, "refund_kobo": d.refund_kobo, "notes": d.notes if d.status == "resolved" else "", "created_at": d.created_at,
    } for d in qs.order_by("-created_at")])
