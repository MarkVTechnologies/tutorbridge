from datetime import datetime, timedelta

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.models import Role
from accounts.permissions import IsParent, IsVerifiedUser
from bookings import services
from bookings.models import Booking, BookingStatus, Lesson, LessonStatus
from bookings.serializers import (
    BookingSerializer,
    CreateBookingSerializer,
    LessonSerializer,
)
from core.dates import day_start, parse_date
from core.models import Area, Subject
from core.throttles import PaymentThrottle
from matching.models import LessonRequest, Match, MatchStatus
from payments import ledger
from payments import services as pay
from tutors.models import TutorProfile


def _booking_scope(user):
    if user.role == Role.PARENT:
        return Booking.objects.filter(parent__user=user)
    if user.role == Role.TUTOR:
        return Booking.objects.filter(tutor__user=user).exclude(status=BookingStatus.AWAITING_PAYMENT)
    return Booking.objects.none()


@api_view(["POST"])
@permission_classes([IsParent])
def quote(request):
    tutor = get_object_or_404(TutorProfile, pk=request.data.get("tutor"))
    req = LessonRequest.objects.filter(pk=request.data.get("request"), parent__user=request.user).first() if request.data.get("request") else None
    q = services.quote(parent=request.user.parent_profile, tutor=tutor, package_size=int(request.data.get("package_size", 1)),
                       lesson_minutes=int(request.data.get("lesson_minutes", 60)), request=req, promo_code=request.data.get("promo_code") or None)
    q.pop("commission_pct")  # internal
    q.pop("promo")
    return Response(q)


def _date_param(value):
    d = parse_date(value)
    if d is None:
        raise ValidationError("Dates must be YYYY-MM-DD.")
    return d


class BookingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = BookingSerializer

    def get_queryset(self):
        qs = _booking_scope(self.request.user).select_related("tutor__user", "parent__user", "child", "area").prefetch_related("subjects")
        status = self.request.query_params.get("status")
        return qs.filter(status=status) if status else qs

    def retrieve(self, request, *args, **kwargs):
        booking = self.get_object()
        data = self.get_serializer(booking).data
        data["lessons"] = LessonSerializer(booking.lessons.select_related("booking__parent", "tutor__user", "booking__child"), many=True, context={"request": request}).data
        if request.user.role == Role.TUTOR:
            from trust.services import parent_rating_summary

            data["parent_summary"] = parent_rating_summary(booking.parent)  # section 4.3: tutors see a parent's record
        return Response(data)

    @action(detail=False, methods=["post"], permission_classes=[IsParent, IsVerifiedUser], throttle_classes=[PaymentThrottle])
    def book(self, request):
        """Create a booking and pay: from wallet if it covers the total, otherwise via gateway checkout for the difference."""
        s = CreateBookingSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        parent = request.user.parent_profile
        tutor = get_object_or_404(TutorProfile, pk=d["tutor"])
        child = get_object_or_404(parent.children, pk=d["child"], is_active=True)
        req = get_object_or_404(LessonRequest, pk=d["request"], parent=parent) if d.get("request") else None
        if req is not None and not Match.objects.filter(request=req, tutor=tutor, in_shortlist=True).exclude(status__in=[MatchStatus.DECLINED, MatchStatus.WITHDRAWN]).exists():
            raise ValidationError("This tutor is not on your shortlist for this request.")
        subjects = list(Subject.objects.filter(pk__in=d["subjects"]))
        taught = set(tutor.subjects.filter(level=child.level).values_list("subject_id", flat=True))
        if not subjects or any(s.pk not in taught for s in subjects):
            raise ValidationError({"subjects": "The tutor doesn't teach all of these subjects at your child's level."})
        area = get_object_or_404(Area, pk=d["area"]) if d.get("area") else (req.area if req else parent.area)
        address = d.get("address") or (req.address if req else parent.address)
        if not d["is_online"] and not address:
            raise ValidationError({"address": "Enter the lesson address."})
        booking = services.create_booking(
            parent=parent, tutor=tutor, child=child, subjects=subjects, package_size=d["package_size"], lesson_minutes=d["lesson_minutes"],
            schedule=d["schedule"], start_date=d["start_date"], request=req, address=address, area=area, is_online=d["is_online"],
            promo_code=d.get("promo_code") or None,
            # Exact lesson location, when the parent picked their address from search (used for distance and check-in checks).
            lat=req.lat if req and req.lat is not None else (parent.lat if not req and address == parent.address else None),
            lng=req.lng if req and req.lng is not None else (parent.lng if not req and address == parent.address else None),
        )
        balance = ledger.balance(ledger.wallet(parent))
        due = booking.total_kobo - balance
        if due <= 0:
            services.pay_from_wallet(booking)
            booking.refresh_from_db()
            return Response({"booking": BookingSerializer(booking, context={"request": request}).data, "payment": None}, status=201)
        payment = pay.start_checkout(parent, due, booking=booking)
        return Response({"booking": BookingSerializer(booking, context={"request": request}).data,
                         "payment": {"reference": payment.reference, "amount_kobo": due, "authorization_url": payment.authorization_url}}, status=201)

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        booking = self.get_object()
        services.tutor_accept(booking, request.user.tutor_profile)
        booking.refresh_from_db()
        return Response(self.get_serializer(booking).data)

    @action(detail=True, methods=["post"])
    def decline(self, request, pk=None):
        booking = self.get_object()
        services.tutor_decline(booking, request.user.tutor_profile, request.data.get("reason", ""))
        return Response({"detail": "Declined."})

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        if request.user.pk != booking.parent.user_id:
            raise ValidationError("Not allowed.")
        if booking.status not in (BookingStatus.AWAITING_PAYMENT, BookingStatus.OFFERED, BookingStatus.REASSIGNING):
            raise ValidationError("Accepted bookings are cancelled lesson by lesson, or ask us for a replacement tutor.")
        services.cancel_booking(booking, request.user, request.data.get("reason", "Cancelled by parent"))
        return Response({"detail": "Booking cancelled. Any payment is back in your wallet."})

    @action(detail=True, methods=["post"], url_path="request-replacement")
    def request_replacement(self, request, pk=None):
        """BKG-07: parent asks for a new tutor; ops chooses and transfers the remaining balance."""
        booking = self.get_object()
        if request.user.pk != booking.parent.user_id or booking.status != BookingStatus.ACTIVE:
            raise ValidationError("Not allowed.")
        services._alert_ops(f"Replacement requested for booking #{booking.pk}", request.data.get("reason", ""))
        from core.audit import audit

        audit(request.user, "booking.replacement_requested", "booking", booking.pk, reason=request.data.get("reason", ""))
        return Response({"detail": "Thanks — our team will be in touch shortly with a replacement tutor."})

    @action(detail=True, methods=["post"], permission_classes=[IsParent, IsVerifiedUser], throttle_classes=[PaymentThrottle])
    def pay(self, request, pk=None):
        """Pay for a booking that's still awaiting payment (an unpaid renewal, or an abandoned checkout)."""
        booking = self.get_object()
        if booking.status != BookingStatus.AWAITING_PAYMENT:
            raise ValidationError("This booking doesn't need payment.")
        due = booking.total_kobo - ledger.balance(ledger.wallet(booking.parent))
        if due <= 0:
            services.pay_from_wallet(booking)
            booking.refresh_from_db()
            return Response({"booking": self.get_serializer(booking).data, "payment": None})
        payment = pay.start_checkout(booking.parent, due, booking=booking)
        return Response({"booking": self.get_serializer(booking).data,
                         "payment": {"reference": payment.reference, "amount_kobo": due, "authorization_url": payment.authorization_url}})

    @action(detail=True, methods=["patch"], url_path="auto-renew", permission_classes=[IsParent])
    def auto_renew(self, request, pk=None):
        booking = self.get_object()
        booking.auto_renew = bool(request.data.get("auto_renew"))
        booking.save(update_fields=["auto_renew"])
        return Response(self.get_serializer(booking).data)

    @action(detail=True, url_path="progress-report")
    def progress_report(self, request, pk=None):
        """LSN-06: monthly progress report PDF from lesson notes."""
        from core.pdf import progress_report_pdf

        booking = self.get_object()
        month = request.query_params.get("month") or timezone.localdate().strftime("%Y-%m")
        try:
            start = datetime.strptime(month, "%Y-%m")
        except ValueError as e:
            raise ValidationError({"month": "Use YYYY-MM."}) from e
        pdf = progress_report_pdf(booking, start.year, start.month)
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="progress-{booking.child.first_name}-{month}.pdf"'
        return resp


class LessonViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = LessonSerializer

    def get_queryset(self):
        u = self.request.user
        qs = Lesson.objects.filter(Q(booking__parent__user=u) | Q(tutor__user=u)).exclude(booking__status=BookingStatus.AWAITING_PAYMENT)
        if u.role == Role.TUTOR:
            qs = qs.filter(booking__accepted_at__isnull=False)
        p = self.request.query_params
        if p.get("upcoming") == "1":
            qs = qs.filter(status__in=[LessonStatus.SCHEDULED, LessonStatus.IN_PROGRESS], scheduled_end__gte=timezone.now() - timedelta(hours=6))
        if p.get("from"):
            qs = qs.filter(scheduled_start__gte=day_start(_date_param(p["from"])))
        if p.get("to"):
            qs = qs.filter(scheduled_start__lt=day_start(_date_param(p["to"]) + timedelta(days=1)))
        return qs.select_related("booking__parent__user", "tutor__user", "booking__child").order_by("scheduled_start")

    def _tutor_only(self):
        if self.request.user.role != Role.TUTOR:
            raise ValidationError("Only the tutor can do this.")
        return self.request.user.tutor_profile

    def _out(self, lesson):
        lesson.refresh_from_db()
        return Response(self.get_serializer(lesson).data)

    @action(detail=True, methods=["post"], url_path="check-in")
    def check_in(self, request, pk=None):
        lesson = services.check_in(self.get_object(), self._tutor_only(), request.data.get("code", ""), request.data.get("lat"), request.data.get("lng"))
        return self._out(lesson)

    @action(detail=True, methods=["post"], url_path="check-out")
    def check_out(self, request, pk=None):
        d = request.data
        lesson = services.check_out(self.get_object(), self._tutor_only(), d.get("code", ""), d.get("topics", ""), d.get("homework", ""), d.get("observations", ""))
        return self._out(lesson)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        lesson = self.get_object()
        if request.user.pk != lesson.booking.parent.user_id:
            raise ValidationError("Only the parent can confirm a lesson.")
        return self._out(services.confirm_lesson(lesson, request.user))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._out(services.cancel_lesson(self.get_object(), request.user, request.data.get("reason", "")))

    @action(detail=True, methods=["post"])
    def reschedule(self, request, pk=None):
        try:
            new_start = datetime.fromisoformat(request.data.get("start", ""))
        except ValueError as e:
            raise ValidationError({"start": "Invalid date/time."}) from e
        if timezone.is_naive(new_start):
            new_start = timezone.make_aware(new_start)
        return self._out(services.reschedule_lesson(self.get_object(), request.user, new_start))

    @action(detail=True, methods=["post"])
    def dispute(self, request, pk=None):
        from trust.services import raise_dispute

        reason, description = request.data.get("reason", ""), (request.data.get("description") or "").strip()
        if not reason or not description:
            raise ValidationError("Tell us what went wrong.")
        raise_dispute(self.get_object(), request.user, reason[:40], description)
        return self._out(self.get_object())

    @action(detail=True, methods=["post"], url_path="safety-report")
    def safety_report(self, request, pk=None):
        from trust.services import report_incident

        description = (request.data.get("description") or "").strip()
        if not description:
            raise ValidationError({"description": "Describe what is happening."})
        incident = report_incident(request.user, description, request.data.get("severity", "urgent"), lesson=self.get_object())
        return Response({"id": incident.pk, "detail": "Our safety team has been alerted and will contact you right away. If anyone is in immediate danger, call 112."})


# --- Calendar feed (BKG-05) ----------------------------------------------------


def _calendar_urls(user):
    from django.conf import settings

    url = f"{settings.SITE_URL}/api/calendar/{user.calendar_token}.ics"
    return {"url": url, "webcal": url.replace("https://", "webcal://").replace("http://", "webcal://")}


@api_view(["GET"])
def calendar_info(request):
    from bookings.calendar import ensure_token

    if request.user.role not in (Role.PARENT, Role.TUTOR):
        raise ValidationError("Calendar feeds are for parents and tutors.")
    ensure_token(request.user)
    return Response(_calendar_urls(request.user))


@api_view(["POST"])
def calendar_reset(request):
    """Issue a new private URL (e.g. if the old one was shared by mistake); the old one stops working."""
    from bookings.calendar import ensure_token

    if request.user.role not in (Role.PARENT, Role.TUTOR):
        raise ValidationError("Calendar feeds are for parents and tutors.")
    ensure_token(request.user, reset=True)
    return Response(_calendar_urls(request.user))


def calendar_feed(request, token):
    """Public by unguessable token (calendar apps can't log in)."""
    from django.http import Http404, HttpResponse

    from accounts.models import User
    from bookings.calendar import build_ics

    user = User.objects.filter(calendar_token=token, is_active=True, suspended_at__isnull=True).first() if token else None
    if user is None:
        raise Http404
    resp = HttpResponse(build_ics(user), content_type="text/calendar; charset=utf-8")
    resp["Content-Disposition"] = 'inline; filename="tutorbridge.ics"'
    resp["Cache-Control"] = "private, max-age=900"
    return resp

