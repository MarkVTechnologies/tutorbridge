from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts.permissions import IsTutor
from core.models import Area
from tutors.models import AvailabilitySlot, BlockedDate, TutorArea, TutorProfile, TutorStatus, TutorSubject
from tutors.serializers import (
    AvailabilitySlotSerializer,
    BlockedDateSerializer,
    TutorOwnProfileSerializer,
    TutorPublicSerializer,
    TutorSubjectSerializer,
)
from tutors.services import onboarding_progress, rate_band, submit_application
from vetting.storage import absolute_path, save_upload


def _tutor(request):
    return request.user.tutor_profile


EDITABLE_STATES = {TutorStatus.APPLIED, TutorStatus.UNDER_REVIEW, TutorStatus.INTERVIEW, TutorStatus.APPROVED, TutorStatus.ACTIVE}


@api_view(["GET", "PATCH"])
@permission_classes([IsTutor])
def my_profile(request):
    tutor = _tutor(request)
    if request.method == "PATCH":
        if tutor.status not in EDITABLE_STATES:
            return Response({"detail": "Your profile cannot be edited right now."}, status=403)
        s = TutorOwnProfileSerializer(tutor, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
    data = TutorOwnProfileSerializer(tutor).data
    data["progress"] = onboarding_progress(tutor)
    data["rate_band"] = rate_band(tutor)
    return Response(data)


@api_view(["POST"])
@permission_classes([IsTutor])
def upload_photo(request):
    tutor = _tutor(request)
    f = request.FILES.get("file")
    if not f:
        return Response({"file": "Choose a photo."}, status=400)
    doc = save_upload(f, request.user, "photo")
    if doc.content_type == "application/pdf":
        doc.delete()
        return Response({"file": "Your photo must be a JPG or PNG."}, status=400)
    tutor.photo = doc
    tutor.save(update_fields=["photo"])
    return Response(TutorOwnProfileSerializer(tutor).data)


@api_view(["PUT"])
@permission_classes([IsTutor])
def set_subjects(request):
    """Replace the subjects × levels matrix. Body: {"items": [{"subject": id, "level": id}], "curricula": [ids]}."""
    tutor = _tutor(request)
    items = request.data.get("items", [])
    with transaction.atomic():
        keep = []
        for it in items:
            ts, _ = TutorSubject.objects.get_or_create(tutor=tutor, subject_id=it["subject"], level_id=it["level"])
            keep.append(ts.pk)
        TutorSubject.objects.filter(tutor=tutor).exclude(pk__in=keep).delete()
        if "curricula" in request.data:
            tutor.curricula.set(request.data["curricula"])
    return Response(TutorSubjectSerializer(tutor.subjects.select_related("subject", "level"), many=True).data)


@api_view(["PUT"])
@permission_classes([IsTutor])
def set_areas(request):
    """Body: {"home_area": id, "areas": [ids], "max_travel_km": n}."""
    tutor = _tutor(request)
    area_ids = [int(a) for a in request.data.get("areas", [])]
    if not area_ids:
        return Response({"areas": "Choose at least one area."}, status=400)
    with transaction.atomic():
        if request.data.get("home_area"):
            tutor.home_area = get_object_or_404(Area, pk=request.data["home_area"])
        if request.data.get("max_travel_km"):
            tutor.max_travel_km = max(1, min(50, int(request.data["max_travel_km"])))
        tutor.save(update_fields=["home_area", "max_travel_km"])
        TutorArea.objects.filter(tutor=tutor).exclude(area_id__in=area_ids).delete()
        for aid in area_ids:
            TutorArea.objects.get_or_create(tutor=tutor, area_id=aid)
    return Response(TutorOwnProfileSerializer(tutor).data)


@api_view(["PUT"])
@permission_classes([IsTutor])
def set_availability(request):
    """Replace the weekly grid. Body: {"slots": [{"weekday": 0, "start_time": "16:00", "end_time": "19:00"}]}."""
    tutor = _tutor(request)
    s = AvailabilitySlotSerializer(data=request.data.get("slots", []), many=True)
    s.is_valid(raise_exception=True)
    with transaction.atomic():
        AvailabilitySlot.objects.filter(tutor=tutor).delete()
        AvailabilitySlot.objects.bulk_create([AvailabilitySlot(tutor=tutor, **d) for d in s.validated_data])
    return Response(AvailabilitySlotSerializer(tutor.availability.all(), many=True).data)


class BlockedDateList(generics.ListCreateAPIView):
    serializer_class = BlockedDateSerializer
    permission_classes = [IsTutor]
    pagination_class = None

    def get_queryset(self):
        return BlockedDate.objects.filter(tutor=self.request.user.tutor_profile).order_by("date")

    def perform_create(self, serializer):
        serializer.save(tutor=self.request.user.tutor_profile)


class BlockedDateDetail(generics.DestroyAPIView):
    serializer_class = BlockedDateSerializer
    permission_classes = [IsTutor]

    def get_queryset(self):
        return BlockedDate.objects.filter(tutor=self.request.user.tutor_profile)


@api_view(["POST"])
@permission_classes([IsTutor])
def submit(request):
    if not request.user.is_verified:
        return Response({"detail": "Verify your email and phone number first."}, status=403)
    tutor = submit_application(_tutor(request))
    return Response(TutorOwnProfileSerializer(tutor).data)


# --- Public ---------------------------------------------------------------


@api_view(["GET"])
@permission_classes([AllowAny])
def search(request):
    """REQ-05: browse and filter Active tutors by subject, level, area, rate, rating and gender."""
    qs = (
        TutorProfile.objects.filter(status=TutorStatus.ACTIVE, user__suspended_at__isnull=True)
        .select_related("user", "home_area")
        .prefetch_related("subjects__subject", "subjects__level", "curricula", "areas__area", "checks")
    )
    p = request.query_params
    if p.get("subject"):
        qs = qs.filter(subjects__subject__slug=p["subject"])
    if p.get("level"):
        qs = qs.filter(subjects__level__code=p["level"])
    if p.get("area"):
        qs = qs.filter(Q(areas__area__slug=p["area"]) | Q(home_area__slug=p["area"]))
    if p.get("max_rate"):
        qs = qs.filter(hourly_rate_kobo__lte=int(p["max_rate"]))
    if p.get("min_rating"):
        qs = qs.filter(rating_avg__gte=p["min_rating"])
    if p.get("gender") in ("female", "male"):
        qs = qs.filter(user__gender=p["gender"])
    if p.get("online") == "1":
        qs = qs.filter(offers_online=True)
    order = {"rating": "-rating_avg", "rate": "hourly_rate_kobo", "experience": "-hours_taught"}.get(p.get("sort"), "-rating_avg")
    qs = qs.distinct().order_by(order, "-reliability_score")
    paginator = PageNumberPagination()
    page = paginator.paginate_queryset(qs, request)
    return paginator.get_paginated_response(TutorPublicSerializer(page, many=True).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def public_profile(request, pk):
    tutor = get_object_or_404(TutorProfile.objects.select_related("user"), pk=pk, status=TutorStatus.ACTIVE)
    data = TutorPublicSerializer(tutor).data
    from trust.models import Review

    data["reviews"] = [
        {"rating": r.rating, "comment": r.comment, "author": r.author.first_name, "created_at": r.created_at}
        for r in Review.objects.filter(booking__tutor=tutor, direction="parent_to_tutor", is_hidden=False).select_related("author")[:20]
    ]
    return Response(data)


@api_view(["GET"])
@permission_classes([AllowAny])
def photo(request, pk):
    """Profile photos are public for Active tutors; otherwise only the tutor and staff can see them."""
    tutor = get_object_or_404(TutorProfile, pk=pk)
    if not tutor.photo_id:
        raise Http404
    u = request.user
    allowed = tutor.status == TutorStatus.ACTIVE or (u.is_authenticated and (u.pk == tutor.user_id or u.is_staff_member))
    if not allowed:
        raise Http404
    resp = FileResponse(open(absolute_path(tutor.photo), "rb"), content_type=tutor.photo.content_type)
    resp["Cache-Control"] = "private, max-age=3600"
    return resp

