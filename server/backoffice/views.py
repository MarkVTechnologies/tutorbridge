"""
Staff console API (ADM-*, TUT-13, REQ-04, OUT-03, SAF-*). Every endpoint is
gated by a granular permission (AUTH-08) and requires a 2FA'd session (AUTH-06).
"""
import csv
from datetime import timedelta

import pyotp
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from accounts.models import STAFF_ROLES, Role, User
from accounts.permissions import ALL_PERMISSIONS, staff_perm
from bookings import services as booking_services
from bookings.models import Booking, BookingStatus, Lesson, LessonStatus
from bookings.serializers import LessonSerializer
from core import config
from core.audit import audit
from core.dates import day_start, parse_date
from core.models import AuditLog, Level, Subject
from matching.engine import run_matching
from matching.models import LessonRequest, Match, MatchStatus, RequestStatus
from matching.serializers import StaffMatchSerializer
from messaging.models import Message, Thread
from messaging.notify import notify
from parents.models import ParentProfile
from payments import ledger
from payments import services as pay
from payments.models import (
    AccountKind,
    LedgerAccount,
    LedgerEntry,
    Payment,
    Payout,
    PayoutItem,
    ReconciliationRun,
)
from trust import services as trust
from trust.models import Dispute, DisputeStatus, Incident, Review
from tutors import services as tutor_services
from tutors.models import TutorProfile, TutorStatus
from tutors.serializers import TutorOwnProfileSerializer
from vetting import services as vetting_services
from vetting.models import (
    CheckStatus,
    CheckType,
    Document,
    InterviewSlot,
    Question,
    Reference,
    TestAttempt,
)


def _paginate(request, qs, fn):
    p = PageNumberPagination()
    page = p.paginate_queryset(qs, request)
    return p.get_paginated_response([fn(o) for o in page])


def _require_fresh_2fa(request):
    """Sensitive finance actions need a TOTP code in the request itself (section 14)."""
    code = str(request.data.get("totp", ""))
    if not (request.user.totp_enabled and pyotp.TOTP(request.user.totp_secret).verify(code, valid_window=1)):
        raise PermissionDenied("Enter a current code from your authenticator app.")


def _user_brief(u):
    return {"id": u.pk, "name": u.get_full_name(), "email": u.email, "phone": u.phone, "role": u.role, "suspended": bool(u.suspended_at)}


# --- Dashboard (ADM-01, ADM-07) -------------------------------------------


@api_view(["GET"])
@permission_classes([staff_perm("users.view")])
def dashboard(request):
    now = timezone.now()
    month_ago = now - timedelta(days=30)
    revenue = ledger.platform(AccountKind.PLATFORM_REVENUE)
    gmv = Payment.objects.filter(status=Payment.Status.SUCCESS, verified_at__gte=month_ago).aggregate(s=Sum("amount_kobo"))["s"] or 0
    rev_30 = LedgerEntry.objects.filter(account=revenue, created_at__gte=month_ago).aggregate(c=Sum("credit_kobo"), d=Sum("debit_kobo"))
    payable = sum(ledger.balance(a) for a in LedgerAccount.objects.filter(kind=AccountKind.TUTOR_EARNINGS))
    reqs_30 = LessonRequest.objects.filter(created_at__gte=month_ago)
    filled = reqs_30.filter(bookings__status__in=[BookingStatus.ACTIVE, BookingStatus.COMPLETED, BookingStatus.OFFERED]).distinct().count()
    lessons_30 = Lesson.objects.filter(scheduled_start__gte=month_ago, scheduled_start__lt=now)
    delivered = lessons_30.filter(status__in=[LessonStatus.CONFIRMED, LessonStatus.COMPLETED]).count()
    no_shows = lessons_30.filter(status=LessonStatus.NO_SHOW).count()
    trials = Booking.objects.filter(is_trial=True, created_at__gte=now - timedelta(days=60), status=BookingStatus.COMPLETED)
    converted = sum(1 for t in trials if Booking.objects.filter(request=t.request, is_trial=False, created_at__gt=t.created_at).exclude(status=BookingStatus.AWAITING_PAYMENT).exists()) if trials else 0
    return Response({
        "active_parents": ParentProfile.objects.filter(bookings__status=BookingStatus.ACTIVE).distinct().count(),
        "active_tutors": TutorProfile.objects.filter(status=TutorStatus.ACTIVE).count(),
        "tutors_in_vetting": TutorProfile.objects.filter(status__in=[TutorStatus.UNDER_REVIEW, TutorStatus.INTERVIEW, TutorStatus.APPROVED]).count(),
        "open_requests": LessonRequest.objects.filter(status__in=[RequestStatus.SUBMITTED, RequestStatus.MATCHING]).count(),
        "requests_past_sla": LessonRequest.objects.filter(status__in=[RequestStatus.SUBMITTED, RequestStatus.MATCHING], sla_due_at__lt=now).count(),
        "active_bookings": Booking.objects.filter(status=BookingStatus.ACTIVE).count(),
        "bookings_needing_tutor": Booking.objects.filter(status=BookingStatus.REASSIGNING).count(),
        "gmv_30d_kobo": gmv,
        "revenue_30d_kobo": (rev_30["c"] or 0) - (rev_30["d"] or 0),
        "payouts_due_kobo": payable,
        "open_disputes": Dispute.objects.exclude(status=DisputeStatus.RESOLVED).count(),
        "open_incidents": Incident.objects.exclude(status=DisputeStatus.RESOLVED).count(),
        "fill_rate_30d": round(filled / reqs_30.count() * 100, 1) if reqs_30.count() else None,
        "lesson_completion_30d": round(delivered / lessons_30.count() * 100, 1) if lessons_30.count() else None,
        "no_show_rate_30d": round(no_shows / lessons_30.count() * 100, 1) if lessons_30.count() else None,
        "trial_conversion_60d": round(converted / trials.count() * 100, 1) if trials else None,
    })


# --- Vetting (TUT-13) -----------------------------------------------------


@api_view(["GET"])
@permission_classes([staff_perm("vetting.view")])
def vetting_queue(request):
    status = request.query_params.get("status")
    qs = TutorProfile.objects.select_related("user").order_by("submitted_at", "created_at")
    qs = qs.filter(status=status) if status else qs.filter(status__in=[TutorStatus.UNDER_REVIEW, TutorStatus.INTERVIEW, TutorStatus.APPROVED])
    if request.query_params.get("q"):
        q = request.query_params["q"]
        qs = qs.filter(Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q) | Q(user__email__icontains=q))

    def row(t):
        checks = {c.check_type: c.status for c in t.checks.all()}
        return {"id": t.pk, "user": _user_brief(t.user), "status": t.status, "submitted_at": t.submitted_at,
                "checks_passed": sum(1 for v in checks.values() if v == CheckStatus.PASSED), "checks_total": len(CheckType.choices),
                "needs_attention": sum(1 for v in checks.values() if v in (CheckStatus.SUBMITTED, CheckStatus.MANUAL_REVIEW))}

    return _paginate(request, qs, row)


@api_view(["GET"])
@permission_classes([staff_perm("vetting.view")])
def vetting_detail(request, pk):
    return Response(_vetting_json(pk))


def _vetting_json(pk):
    t = get_object_or_404(TutorProfile.objects.select_related("user"), pk=pk)
    checks = {c.check_type: c for c in t.checks.select_related("reviewer")}
    return {
        "profile": TutorOwnProfileSerializer(t).data,
        "user": {**_user_brief(t.user), "gender": t.user.gender, "email_verified": bool(t.user.email_verified_at), "phone_verified": bool(t.user.phone_verified_at)},
        "progress": tutor_services.onboarding_progress(t),
        "checks": [{
            "type": ct, "label": label, "status": checks[ct].status if ct in checks else CheckStatus.PENDING,
            "provider": checks[ct].provider if ct in checks else "", "result": checks[ct].result if ct in checks else None,
            "notes": checks[ct].notes if ct in checks else "", "reviewer": checks[ct].reviewer.get_full_name() if ct in checks and checks[ct].reviewer else None,
            "reviewed_at": checks[ct].reviewed_at if ct in checks else None,
        } for ct, label in CheckType.choices],
        "documents": [{"id": d.pk, "doc_type": d.doc_type, "label": d.get_doc_type_display(), "name": d.original_name, "status": d.status,
                       "review_note": d.review_note, "created_at": d.created_at, "url": f"/api/vetting/documents/{d.pk}/file/"}
                      for d in Document.objects.filter(owner=t.user).order_by("doc_type", "-created_at")],
        "references": [{"id": r.pk, "kind": r.kind, "name": r.name, "email": r.email, "phone": r.phone, "relationship": r.relationship,
                        "organisation": r.organisation, "is_professional": r.is_professional, "submitted_at": r.submitted_at,
                        "response": r.response, "call_verified": r.call_verified, "call_notes": r.call_notes,
                        "id_document": f"/api/vetting/documents/{r.id_document_id}/file/" if r.id_document_id else None} for r in t.references.all()],
        "tests": [{"subject": a.subject.name, "level": a.level.name, "score_pct": a.score_pct, "passed": a.passed, "submitted_at": a.submitted_at}
                  for a in TestAttempt.objects.filter(tutor=t).select_related("subject", "level").order_by("-started_at")],
        "interviews": [{"id": s.pk, "starts_at": s.starts_at, "officer": s.officer.get_full_name(), "meeting_link": s.meeting_link, "outcome": s.outcome, "notes": s.notes}
                       for s in InterviewSlot.objects.filter(tutor=t).select_related("officer")],
        "history": [{"from": h.from_status, "to": h.to_status, "by": h.changed_by.get_full_name() if h.changed_by else "system", "reason": h.reason, "at": h.created_at}
                    for h in t.status_history.select_related("changed_by")],
        "approval_blockers": tutor_services.approval_blockers(t),
        "strikes": [{"reason": s.reason, "notes": s.notes, "at": s.created_at} for s in t.strike_records.all()],
    }


@api_view(["POST"])
@permission_classes([staff_perm("vetting.review")])
def vetting_check(request, pk):
    t = get_object_or_404(TutorProfile, pk=pk)
    ct, status = request.data.get("check_type"), request.data.get("status")
    if ct not in CheckType.values or status not in (CheckStatus.PASSED, CheckStatus.FAILED, CheckStatus.MANUAL_REVIEW):
        raise ValidationError("Invalid check or status.")
    if status == CheckStatus.FAILED and not request.data.get("notes"):
        raise ValidationError({"notes": "Give a reason."})
    vetting_services.decide_check(t, ct, status, request.user, request.data.get("notes", ""), request=request)
    return Response(_vetting_json(pk))


@api_view(["POST"])
@permission_classes([staff_perm("vetting.review")])
def review_document(request, pk):
    d = get_object_or_404(Document, pk=pk)
    status = request.data.get("status")
    if status not in ("accepted", "rejected"):
        raise ValidationError("status must be accepted or rejected")
    d.status, d.review_note, d.reviewed_by, d.reviewed_at = status, (request.data.get("note") or "")[:255], request.user, timezone.now()
    d.save()
    audit(request.user, "document.review", "document", d.pk, after={"status": status}, reason=d.review_note, request=request)
    return Response({"id": d.pk, "status": d.status})


@api_view(["POST"])
@permission_classes([staff_perm("vetting.review")])
def reference_verify(request, pk):
    r = get_object_or_404(Reference, pk=pk)
    r.call_verified, r.call_notes = bool(request.data.get("call_verified")), (request.data.get("call_notes") or "")
    r.save(update_fields=["call_verified", "call_notes"])
    audit(request.user, "reference.call", "reference", r.pk, after={"verified": r.call_verified}, reason=r.call_notes, request=request)
    return Response({"id": r.pk, "call_verified": r.call_verified})


@api_view(["POST"])
@permission_classes([staff_perm("vetting.decide")])
def vetting_decision(request, pk):
    """Move a tutor through Under review → Interview → Approved, or Reject — always with a reason."""
    t = get_object_or_404(TutorProfile, pk=pk)
    decision, reason = request.data.get("decision"), (request.data.get("reason") or "").strip()
    if not reason:
        raise ValidationError({"reason": "A reason is required for every decision."})
    if decision == "interview":
        tutor_services.set_status(t, TutorStatus.INTERVIEW, request.user, reason)
    elif decision == "approve":
        tutor_services.approve(t, request.user, reason)
    elif decision == "reject":
        tutor_services.set_status(t, TutorStatus.REJECTED, request.user, reason)
    elif decision == "under_review":
        tutor_services.set_status(t, TutorStatus.UNDER_REVIEW, request.user, reason)
    else:
        raise ValidationError({"decision": "Unknown decision."})
    return Response(_vetting_json(pk))


@api_view(["GET", "POST"])
@permission_classes([staff_perm("vetting.review")])
def interview_slots(request):
    if request.method == "POST":
        from django.utils.dateparse import parse_datetime

        start = parse_datetime(request.data.get("starts_at", ""))
        if not start or start < timezone.now():
            raise ValidationError({"starts_at": "Choose a future date and time."})
        s = InterviewSlot.objects.create(officer=request.user, starts_at=start, duration_minutes=int(request.data.get("duration_minutes", 30)),
                                         meeting_link=request.data.get("meeting_link", ""))
        return Response({"id": s.pk}, status=201)
    qs = InterviewSlot.objects.filter(starts_at__gte=timezone.now() - timedelta(days=14)).select_related("officer", "tutor__user")
    return Response([{"id": s.pk, "starts_at": s.starts_at, "duration_minutes": s.duration_minutes, "officer": s.officer.get_full_name(),
                      "meeting_link": s.meeting_link, "tutor": {"id": s.tutor_id, "name": s.tutor.user.get_full_name()} if s.tutor_id else None,
                      "outcome": s.outcome} for s in qs])


@api_view(["POST"])
@permission_classes([staff_perm("vetting.review")])
def interview_outcome(request, pk):
    s = get_object_or_404(InterviewSlot, pk=pk, tutor__isnull=False)
    outcome = request.data.get("outcome")
    if outcome not in ("pass", "fail", "no_show"):
        raise ValidationError({"outcome": "pass, fail or no_show"})
    s.outcome, s.notes = outcome, request.data.get("notes", "")
    s.save(update_fields=["outcome", "notes"])
    status = {"pass": CheckStatus.PASSED, "fail": CheckStatus.FAILED, "no_show": CheckStatus.PENDING}[outcome]
    vetting_services.decide_check(s.tutor, CheckType.INTERVIEW, status, request.user, s.notes, request=request)
    if outcome == "no_show":
        s.tutor = None  # free the tutor to rebook
        s.save(update_fields=["tutor"])
    return Response({"id": s.pk, "outcome": s.outcome})


@api_view(["GET", "POST"])
@permission_classes([staff_perm("vetting.review")])
def questions(request):
    if request.method == "POST":
        d = request.data
        opts = d.get("options") or []
        if len(opts) < 2 or not 0 <= int(d.get("correct_index", -1)) < len(opts):
            raise ValidationError("Provide at least two options and a valid correct_index.")
        q = Question.objects.create(subject_id=d["subject"], level_id=d["level"], text=d["text"], options=opts, correct_index=int(d["correct_index"]))
        audit(request.user, "question.create", "question", q.pk, request=request)
        return Response({"id": q.pk}, status=201)
    qs = Question.objects.select_related("subject", "level")
    if request.query_params.get("subject"):
        qs = qs.filter(subject_id=request.query_params["subject"])
    if request.query_params.get("level"):
        qs = qs.filter(level_id=request.query_params["level"])
    return _paginate(request, qs.order_by("subject__name", "level__order", "id"), lambda q: {
        "id": q.pk, "subject": q.subject.name, "level": q.level.name, "text": q.text, "options": q.options, "correct_index": q.correct_index, "is_active": q.is_active})


@api_view(["PATCH"])
@permission_classes([staff_perm("vetting.review")])
def question_detail(request, pk):
    q = get_object_or_404(Question, pk=pk)
    for f in ("text", "options", "correct_index", "is_active"):
        if f in request.data:
            setattr(q, f, request.data[f])
    q.save()
    return Response({"id": q.pk})


# --- Requests & matching (REQ-04) -----------------------------------------


@api_view(["GET"])
@permission_classes([staff_perm("requests.view")])
def requests_list(request):
    qs = LessonRequest.objects.select_related("parent__user", "child", "area", "assigned_officer").prefetch_related("subjects")
    status = request.query_params.get("status")
    qs = qs.filter(status=status) if status else qs.filter(status__in=[RequestStatus.SUBMITTED, RequestStatus.MATCHING])
    return _paginate(request, qs.order_by("sla_due_at"), lambda r: {
        "id": r.pk, "parent": r.parent.user.get_full_name(), "child": f"{r.child.first_name} ({r.child.class_name})",
        "subjects": [s.name for s in r.subjects.all()], "area": r.area.name, "status": r.status, "sla_due_at": r.sla_due_at,
        "overdue": bool(r.sla_due_at and r.sla_due_at < timezone.now() and r.status in (RequestStatus.SUBMITTED, RequestStatus.MATCHING)),
        "assigned_to": r.assigned_officer.get_full_name() if r.assigned_officer else None, "created_at": r.created_at,
        "candidates": r.matches.count(),
    })


def _request_json(r):
    return {
        "id": r.pk, "status": r.status, "parent": _user_brief(r.parent.user),
        "child": {"name": r.child.first_name, "class_name": r.child.class_name, "level": r.child.level.name, "curriculum": r.child.curriculum.name,
                  "special_needs": r.child.special_needs, "learning_notes": r.child.learning_notes},
        "subjects": [s.name for s in r.subjects.all()], "goals": r.goals, "schedule": r.schedule, "lesson_minutes": r.lesson_minutes,
        "start_date": r.start_date, "area": r.area.name, "address": r.address, "budget_min_kobo": r.budget_min_kobo, "budget_max_kobo": r.budget_max_kobo,
        "preferences": r.preferences, "is_online": r.is_online, "sla_due_at": r.sla_due_at, "ops_notes": r.ops_notes,
        "shortlist_published_at": r.shortlist_published_at,
        "matches": StaffMatchSerializer(r.matches.select_related("tutor__user").prefetch_related("tutor__subjects__subject", "tutor__subjects__level", "tutor__checks").exclude(status=MatchStatus.WITHDRAWN), many=True).data,
    }


@api_view(["GET", "PATCH"])
@permission_classes([staff_perm("requests.view")])
def request_detail(request, pk):
    r = get_object_or_404(LessonRequest, pk=pk)
    if request.method == "PATCH":
        if not request.user.has_perm_code("requests.match"):
            raise PermissionDenied()
        if "ops_notes" in request.data:
            r.ops_notes = request.data["ops_notes"]
        if request.data.get("assign_to_me"):
            r.assigned_officer = request.user
        if request.data.get("status") in RequestStatus.values:
            r.status = request.data["status"]
        r.save()
    return Response(_request_json(r))


@api_view(["POST"])
@permission_classes([staff_perm("requests.match")])
def request_rematch(request, pk):
    r = get_object_or_404(LessonRequest, pk=pk)
    run_matching(r)
    return Response(_request_json(r))


@api_view(["POST"])
@permission_classes([staff_perm("requests.match")])
def request_add_tutor(request, pk):
    from matching.engine import score_tutor

    r = get_object_or_404(LessonRequest, pk=pk)
    t = get_object_or_404(TutorProfile, pk=request.data.get("tutor"), status=TutorStatus.ACTIVE)
    score, breakdown = score_tutor(t, r)
    Match.objects.update_or_create(request=r, tutor=t, defaults={"score": score or 0, "breakdown": {**breakdown, "added_by_ops": True}, "rank": 50, "status": MatchStatus.SUGGESTED})
    return Response(_request_json(r))


@api_view(["PATCH"])
@permission_classes([staff_perm("requests.match")])
def match_update(request, pk):
    m = get_object_or_404(Match, pk=pk)
    if "in_shortlist" in request.data:
        m.in_shortlist = bool(request.data["in_shortlist"])
    if "rank" in request.data:
        m.rank = int(request.data["rank"])
    if request.data.get("withdraw"):
        m.status, m.in_shortlist = MatchStatus.WITHDRAWN, False
    m.save()
    return Response(_request_json(m.request))


@api_view(["POST"])
@permission_classes([staff_perm("requests.match")])
def match_invite(request, pk):
    """REQ-07: invite a tutor to confirm interest before the shortlist goes to the parent."""
    m = get_object_or_404(Match.objects.select_related("request__area"), pk=pk)
    m.status = MatchStatus.INVITED
    m.save(update_fields=["status"])
    r = m.request
    notify(m.tutor.user, "request_invite", {"subjects": ", ".join(s.name for s in r.subjects.all()), "area": r.area.name}, link="/tutor/invitations")
    return Response(_request_json(r))


@api_view(["POST"])
@permission_classes([staff_perm("requests.match")])
def request_publish(request, pk):
    r = get_object_or_404(LessonRequest, pk=pk)
    shortlisted = r.matches.filter(in_shortlist=True).exclude(status__in=[MatchStatus.DECLINED, MatchStatus.WITHDRAWN])
    if not shortlisted.exists():
        raise ValidationError("Add at least one tutor to the shortlist first.")
    with transaction.atomic():
        for i, m in enumerate(shortlisted.order_by("rank", "-score")):
            m.rank = i + 1
            m.save(update_fields=["rank"])
        r.status, r.shortlist_published_at = RequestStatus.SHORTLIST_READY, timezone.now()
        r.assigned_officer = r.assigned_officer or request.user
        r.save()
        audit(request.user, "request.publish_shortlist", "request", r.pk, after={"tutors": list(shortlisted.values_list("tutor_id", flat=True))}, request=request)
    notify(r.parent.user, "shortlist_ready", {"child_name": r.child.first_name, "link": f"/parent/requests/{r.pk}"}, link=f"/parent/requests/{r.pk}")
    return Response(_request_json(r))


# --- Bookings -------------------------------------------------------------


@api_view(["GET"])
@permission_classes([staff_perm("bookings.view")])
def bookings_list(request):
    qs = Booking.objects.select_related("parent__user", "tutor__user", "child")
    if request.query_params.get("status"):
        qs = qs.filter(status=request.query_params["status"])
    return _paginate(request, qs, lambda b: {
        "id": b.pk, "status": b.status, "parent": b.parent.user.get_full_name(), "tutor": b.tutor.user.get_full_name(), "child": b.child.first_name,
        "package_size": b.package_size, "total_kobo": b.total_kobo, "created_at": b.created_at, "offer_expires_at": b.offer_expires_at,
    })


@api_view(["GET"])
@permission_classes([staff_perm("bookings.view")])
def booking_detail(request, pk):
    return Response(_booking_json(request, pk))


def _booking_json(request, pk):
    b = get_object_or_404(Booking.objects.select_related("parent__user", "tutor__user", "child"), pk=pk)
    lessons = b.lessons.select_related("booking__parent", "tutor__user", "booking__child")
    return {
        "id": b.pk, "status": b.status, "parent": _user_brief(b.parent.user), "tutor": {**_user_brief(b.tutor.user), "tutor_id": b.tutor_id},
        "child": b.child.first_name, "subjects": [s.name for s in b.subjects.all()], "package_size": b.package_size, "lesson_minutes": b.lesson_minutes,
        "schedule": b.schedule, "total_kobo": b.total_kobo, "commission_pct": str(b.commission_pct), "escrow_balance_kobo": ledger.balance(ledger.escrow(b)),
        "address": b.address, "request": b.request_id, "declined_tutor_ids": b.declined_tutor_ids, "replaces": b.replaces_id,
        "lessons": [{**LessonSerializer(l, context={"request": request}).data, "checkin_lat": l.checkin_lat, "checkin_lng": l.checkin_lng, "checkin_distance_m": l.checkin_distance_m} for l in lessons],
    }


@api_view(["POST"])
@permission_classes([staff_perm("bookings.manage")])
def booking_action(request, pk, op):
    b = get_object_or_404(Booking, pk=pk)
    reason = request.data.get("reason", "")
    if op == "cancel":
        booking_services.cancel_booking(b, request.user, reason or "Cancelled by operations")
    elif op == "reassign":
        booking_services.reassign(b)
    elif op == "replace":
        new = booking_services.replace_tutor(b, get_object_or_404(TutorProfile, pk=request.data.get("tutor"), status=TutorStatus.ACTIVE), request.user, reason)
        return Response({"new_booking": new.pk})
    else:
        raise ValidationError("Unknown action.")
    return Response(_booking_json(request, pk))


@api_view(["POST"])
@permission_classes([staff_perm("bookings.manage")])
def lesson_no_show(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    booking_services.mark_no_show(lesson, by_user=request.user)
    audit(request.user, "lesson.no_show", "lesson", lesson.pk, request=request)
    return Response({"status": "no_show"})


@api_view(["POST"])
@permission_classes([staff_perm("bookings.manage")])
def lesson_unlock_codes(request, pk):
    """Reset a lesson's wrong-code counter after support has confirmed who is at the door."""
    lesson = get_object_or_404(Lesson, pk=pk)
    before = lesson.code_attempts
    Lesson.objects.filter(pk=pk).update(code_attempts=0)
    audit(request.user, "lesson.unlock_codes", "lesson", pk, before={"code_attempts": before}, after={"code_attempts": 0},
          reason=request.data.get("reason", ""), request=request)
    return Response({"code_attempts": 0})


# --- Finance (OUT-*, PAY-09) ----------------------------------------------


@api_view(["GET"])
@permission_classes([staff_perm("finance.view")])
def finance_summary(request):
    totals = {}
    for kind, label in AccountKind.choices:
        totals[kind] = {"label": label, "balance_kobo": sum(ledger.balance(a) for a in LedgerAccount.objects.filter(kind=kind))}
    d, c = ledger.trial_balance()
    return Response({"accounts": totals, "trial_balance": {"debits_kobo": d, "credits_kobo": c, "balanced": d == c},
                     "last_reconciliation": ReconciliationRun.objects.order_by("-created_at").values("run_date", "checked", "mismatches", "created_at").first()})


@api_view(["GET"])
@permission_classes([staff_perm("finance.view")])
def finance_payments(request):
    qs = Payment.objects.select_related("parent__user")
    if request.query_params.get("status"):
        qs = qs.filter(status=request.query_params["status"])
    return _paginate(request, qs, lambda p: {"reference": p.reference, "parent": p.parent.user.get_full_name(), "amount_kobo": p.amount_kobo,
                                             "fee_kobo": p.fee_kobo, "status": p.status, "gateway": p.gateway, "channel": p.channel,
                                             "booking": p.booking_id, "created_at": p.created_at, "verified_at": p.verified_at})


def _payout_json(p):
    return {"id": p.pk, "status": p.status, "total_kobo": p.total_kobo, "created_at": p.created_at,
            "created_by": p.created_by.get_full_name() if p.created_by else "system (weekly run)",
            "approved_by": p.approved_by.get_full_name() if p.approved_by else None, "approved_at": p.approved_at,
            "items": [{"id": i.pk, "tutor": i.tutor.user.get_full_name(), "tutor_id": i.tutor_id, "amount_kobo": i.amount_kobo, "bank": i.bank_snapshot,
                       "status": i.status, "failure_reason": i.failure_reason, "reference": i.transfer_reference} for i in p.items.select_related("tutor__user")]}


@api_view(["GET", "POST"])
@permission_classes([staff_perm("finance.view")])
def payouts(request):
    if request.method == "POST":
        if not request.user.has_perm_code("payouts.create"):
            raise PermissionDenied()
        return Response(_payout_json(pay.create_payout_batch(request.user)), status=201)
    return _paginate(request, Payout.objects.all(), lambda p: {k: v for k, v in _payout_json(p).items() if k != "items"} | {"items": p.items.count()})


@api_view(["GET"])
@permission_classes([staff_perm("finance.view")])
def payout_detail(request, pk):
    return Response(_payout_json(get_object_or_404(Payout, pk=pk)))


@api_view(["POST"])
@permission_classes([staff_perm("payouts.approve")])
def payout_approve(request, pk):
    _require_fresh_2fa(request)
    payout = get_object_or_404(Payout, pk=pk)
    try:
        pay.approve_payout(payout, request.user, request=request)
    except PermissionError as e:
        raise PermissionDenied(str(e)) from e
    except ValueError as e:
        raise ValidationError(str(e)) from e
    return Response(_payout_json(Payout.objects.get(pk=pk)))


@api_view(["POST"])
@permission_classes([staff_perm("payouts.create")])
def payout_item_action(request, pk, op):
    item = get_object_or_404(PayoutItem, pk=pk)
    if op == "remove" and item.status == PayoutItem.Status.PENDING and item.payout.status == Payout.Status.DRAFT:
        item.status = PayoutItem.Status.REMOVED
        item.save(update_fields=["status"])
        item.payout.total_kobo -= item.amount_kobo
        item.payout.save(update_fields=["total_kobo"])
    elif op == "retry" and item.status == PayoutItem.Status.FAILED:
        _require_fresh_2fa(request)
        # Funds went back to earnings on failure; move them out again under a new reference.
        old_ref = item.transfer_reference
        item.transfer_reference = pay.new_reference("PO")
        item.status, item.failure_reason = PayoutItem.Status.PENDING, ""
        item.save()
        ledger.transfer(f"payout:{item.transfer_reference}", "payout", f"Payout retry (was {old_ref})", ledger.earnings(item.tutor),
                        ledger.platform(AccountKind.PAYOUTS_IN_TRANSIT), item.amount_kobo, payout_item=item, user=request.user)
        pay.send_transfer(item)
    else:
        raise ValidationError("Action not allowed for this item.")
    audit(request.user, f"payout_item.{op}", "payout_item", item.pk, request=request)
    return Response(_payout_json(item.payout))


@api_view(["POST"])
@permission_classes([staff_perm("refunds.process")])
def wallet_refund(request, parent_id):
    _require_fresh_2fa(request)
    parent = get_object_or_404(ParentProfile, pk=parent_id)
    amount = int(request.data.get("amount_kobo", 0))
    if amount <= 0:
        raise ValidationError({"amount_kobo": "Enter an amount."})
    try:
        txn = pay.wallet_cash_refund(parent, amount, request.user, request=request)
    except ledger.InsufficientFunds as e:
        raise ValidationError("Wallet balance is lower than this amount.") from e
    return Response({"reference": txn.reference})


@api_view(["POST"])
@permission_classes([staff_perm("finance.view")])
def run_reconciliation(request):
    run = pay.reconcile()
    return Response({"run_date": run.run_date, "checked": run.checked, "mismatches": run.mismatches})


# --- Safety: incidents, disputes, suspensions (SAF-*) ---------------------


@api_view(["GET"])
@permission_classes([staff_perm("safety.view")])
def incidents(request):
    qs = Incident.objects.select_related("reporter", "subject_user", "assignee")
    if request.query_params.get("status"):
        qs = qs.filter(status=request.query_params["status"])
    return _paginate(request, qs, lambda i: {
        "id": i.pk, "severity": i.severity, "status": i.status, "reporter": _user_brief(i.reporter),
        "subject_user": _user_brief(i.subject_user) if i.subject_user else None, "lesson": i.lesson_id, "booking": i.booking_id,
        "description": i.description, "assignee": i.assignee.get_full_name() if i.assignee else None, "actions_taken": i.actions_taken,
        "acknowledged_at": i.acknowledged_at, "resolved_at": i.resolved_at, "created_at": i.created_at,
    })


@api_view(["PATCH"])
@permission_classes([staff_perm("safety.act")])
def incident_update(request, pk):
    i = get_object_or_404(Incident, pk=pk)
    before = {"status": i.status}
    if request.data.get("acknowledge") and not i.acknowledged_at:
        i.acknowledged_at, i.assignee = timezone.now(), request.user
        i.status = DisputeStatus.INVESTIGATING
    if "actions_taken" in request.data:
        i.actions_taken = request.data["actions_taken"]
    if request.data.get("resolve"):
        if not i.actions_taken:
            raise ValidationError({"actions_taken": "Record the actions taken before resolving."})
        i.status, i.resolved_at = DisputeStatus.RESOLVED, timezone.now()
    i.save()
    audit(request.user, "incident.update", "incident", i.pk, before=before, after={"status": i.status}, request=request)
    return Response({"id": i.pk, "status": i.status})


@api_view(["GET"])
@permission_classes([staff_perm("disputes.view")])
def disputes(request):
    qs = Dispute.objects.select_related("lesson__booking__parent__user", "lesson__tutor__user", "raised_by", "assignee")
    status = request.query_params.get("status")
    qs = qs.filter(status=status) if status else qs.exclude(status=DisputeStatus.RESOLVED)
    return _paginate(request, qs.order_by("created_at"), lambda d: {
        "id": d.pk, "status": d.status, "reason": d.reason, "description": d.description, "raised_by": _user_brief(d.raised_by),
        "lesson": LessonSerializer(d.lesson, context={"request": request}).data, "parent": d.lesson.booking.parent.user.get_full_name(),
        "tutor": d.lesson.tutor.user.get_full_name(), "assignee": d.assignee.get_full_name() if d.assignee else None,
        "resolution": d.resolution, "refund_kobo": d.refund_kobo, "notes": d.notes, "created_at": d.created_at,
        "evidence": [f"/api/vetting/documents/{e.pk}/file/" for e in d.evidence.all()],
    })


@api_view(["POST"])
@permission_classes([staff_perm("disputes.resolve")])
def dispute_action(request, pk):
    d = get_object_or_404(Dispute, pk=pk)
    if request.data.get("assign_to_me"):
        d.assignee, d.status = request.user, DisputeStatus.INVESTIGATING
        d.save(update_fields=["assignee", "status"])
        return Response({"id": d.pk, "status": d.status})
    resolution = request.data.get("resolution")
    if resolution in ("refund", "partial") and not request.user.has_perm_code("refunds.process") and not request.user.has_perm_code("disputes.resolve"):
        raise PermissionDenied()
    trust.resolve_dispute(d, request.user, resolution, request.data.get("notes", ""), int(request.data.get("refund_kobo", 0) or 0), request=request)
    return Response({"id": d.pk, "status": "resolved"})


@api_view(["POST"])
@permission_classes([staff_perm("users.suspend")])
def user_suspend(request, pk):
    u = get_object_or_404(User, pk=pk)
    if u.is_staff_member:
        raise ValidationError("Staff accounts are managed in Staff settings.")
    reason = (request.data.get("reason") or "").strip()
    if not reason:
        raise ValidationError({"reason": "A reason is required."})
    op = request.data.get("op", "suspend")
    if op == "reinstate":
        trust.reinstate_user(u, request.user, reason, request=request)
    else:
        trust.suspend_user(u, request.user, reason, ban=op == "ban", request=request)
    return Response(_user_brief(u))


@api_view(["POST"])
@permission_classes([staff_perm("safety.act")])
def strike_add(request, tutor_id):
    t = get_object_or_404(TutorProfile, pk=tutor_id)
    trust.add_strike(t, request.data.get("reason", "policy_breach"), by_user=request.user, notes=request.data.get("notes", ""))
    audit(request.user, "strike.add", "tutor", t.pk, reason=request.data.get("notes", ""), request=request)
    return Response({"strikes": t.strike_records.count()})


@api_view(["GET"])
@permission_classes([staff_perm("messages.view")])
def thread_view(request, pk):
    """MSG-03: staff can read full conversations (including what was masked) for disputes and safety."""
    t = get_object_or_404(Thread, pk=pk)
    audit(request.user, "messages.view", "thread", t.pk, request=request)
    return Response([{"id": m.pk, "sender": m.sender.get_full_name(), "body": m.body, "original_body": m.original_body, "flagged": m.flagged,
                      "created_at": m.created_at} for m in t.messages.select_related("sender")])


@api_view(["GET"])
@permission_classes([staff_perm("messages.view")])
def flagged_messages(request):
    qs = Message.objects.filter(flagged=True).select_related("sender", "thread").order_by("-created_at")
    return _paginate(request, qs, lambda m: {"id": m.pk, "thread": m.thread_id, "sender": _user_brief(m.sender), "body": m.body,
                                             "original_body": m.original_body, "created_at": m.created_at})


# --- Reviews moderation (REV-03) ------------------------------------------


@api_view(["GET"])
@permission_classes([staff_perm("reviews.moderate")])
def reviews_list(request):
    qs = Review.objects.select_related("author", "booking__tutor__user", "booking__parent__user")
    return _paginate(request, qs, lambda r: {"id": r.pk, "direction": r.direction, "author": r.author.get_full_name(), "rating": r.rating,
                                             "comment": r.comment, "tutor": r.booking.tutor.user.get_full_name(), "is_hidden": r.is_hidden,
                                             "hidden_reason": r.hidden_reason, "created_at": r.created_at})


@api_view(["POST"])
@permission_classes([staff_perm("reviews.moderate")])
def review_visibility(request, pk):
    r = get_object_or_404(Review, pk=pk)
    hide = bool(request.data.get("hide"))
    if hide and not request.data.get("reason"):
        raise ValidationError({"reason": "A reason is required to hide a review."})
    r.is_hidden, r.hidden_reason, r.hidden_by = hide, request.data.get("reason", "") if hide else "", request.user if hide else None
    r.save()
    trust.recompute_rating(r.booking.tutor)
    audit(request.user, "review.hide" if hide else "review.unhide", "review", r.pk, reason=r.hidden_reason, request=request)
    return Response({"id": r.pk, "is_hidden": r.is_hidden})


# --- Users (ADM-03) & staff -----------------------------------------------


@api_view(["GET"])
@permission_classes([staff_perm("users.view")])
def users_list(request):
    qs = User.objects.all().order_by("-date_joined")
    p = request.query_params
    if p.get("role"):
        qs = qs.filter(role=p["role"])
    if p.get("q"):
        qs = qs.filter(Q(first_name__icontains=p["q"]) | Q(last_name__icontains=p["q"]) | Q(email__icontains=p["q"]) | Q(phone__icontains=p["q"]))
    if p.get("suspended") == "1":
        qs = qs.filter(suspended_at__isnull=False)
    return _paginate(request, qs, lambda u: {**_user_brief(u), "date_joined": u.date_joined, "last_login": u.last_login, "verified": u.is_verified})


@api_view(["GET"])
@permission_classes([staff_perm("users.view")])
def user_detail(request, pk):
    u = get_object_or_404(User, pk=pk)
    out = {**_user_brief(u), "gender": u.gender, "date_joined": u.date_joined, "last_login": u.last_login, "email_verified_at": u.email_verified_at,
           "phone_verified_at": u.phone_verified_at, "suspension_reason": u.suspension_reason, "totp_enabled": u.totp_enabled,
           "extra_permissions": u.extra_permissions}
    if u.role == Role.PARENT and hasattr(u, "parent_profile"):
        p = u.parent_profile
        out["parent"] = {"id": p.pk, "area": p.area.name if p.area else None, "wallet_kobo": ledger.balance(ledger.wallet(p)),
                         "bookings": p.bookings.count(), "cancellations": p.cancellation_count}
    if u.role == Role.TUTOR and hasattr(u, "tutor_profile"):
        t = u.tutor_profile
        out["tutor"] = {"id": t.pk, "status": t.status, "tier": t.tier, "rating_avg": t.rating_avg, "reliability_score": t.reliability_score,
                        "earnings_kobo": ledger.balance(ledger.earnings(t)), "strikes": t.strikes}
    out["activity"] = list(AuditLog.objects.filter(Q(actor=u) | Q(entity_type="user", entity_id=str(u.pk))).values("action", "entity_type", "entity_id", "reason", "created_at", "ip")[:100])
    return Response(out)


@api_view(["GET", "POST"])
@permission_classes([staff_perm("staff.manage")])
def staff_accounts(request):
    if request.method == "POST":
        d = request.data
        if d.get("role") not in {r.value for r in STAFF_ROLES}:
            raise ValidationError({"role": "Choose a staff role."})
        from accounts.phone import normalise_phone

        phone = normalise_phone(d.get("phone"))
        if not phone:
            raise ValidationError({"phone": "Invalid phone."})
        extra = [p for p in d.get("extra_permissions", []) if p in ALL_PERMISSIONS]
        u = User.objects.create_user(email=d["email"], phone=phone, password=d["password"], first_name=d["first_name"], last_name=d["last_name"],
                                     role=d["role"], extra_permissions=extra, email_verified_at=timezone.now(), phone_verified_at=timezone.now())
        audit(request.user, "staff.create", "user", u.pk, after={"role": u.role, "extra_permissions": extra}, request=request)
        return Response(_user_brief(u), status=201)
    return Response([{**_user_brief(u), "extra_permissions": u.extra_permissions, "totp_enabled": u.totp_enabled, "last_login": u.last_login}
                     for u in User.objects.filter(role__in=[r.value for r in STAFF_ROLES]).order_by("role", "first_name")])


@api_view(["PATCH"])
@permission_classes([staff_perm("staff.manage")])
def staff_update(request, pk):
    u = get_object_or_404(User, pk=pk, role__in=[r.value for r in STAFF_ROLES])
    before = {"role": u.role, "extra_permissions": u.extra_permissions, "is_active": u.is_active}
    if "extra_permissions" in request.data:
        u.extra_permissions = [p for p in request.data["extra_permissions"] if p in ALL_PERMISSIONS]
    if request.data.get("role") in {r.value for r in STAFF_ROLES}:
        u.role = request.data["role"]
    if "is_active" in request.data and u.pk != request.user.pk:
        u.is_active = bool(request.data["is_active"])
    u.save()
    audit(request.user, "staff.update", "user", u.pk, before=before, after={"role": u.role, "extra_permissions": u.extra_permissions, "is_active": u.is_active}, request=request)
    return Response(_user_brief(u))


# --- Configuration (ADM-02) -----------------------------------------------


@api_view(["GET", "PUT"])
@permission_classes([staff_perm("users.view")])
def settings_view(request):
    if request.method == "PUT":
        if not request.user.has_perm_code("settings.manage"):
            raise PermissionDenied()
        for key, value in request.data.items():
            try:
                config.set_value(key, value, request.user)
            except KeyError as e:
                raise ValidationError({key: "Unknown setting."}) from e
    return Response(config.all_settings())


@api_view(["PATCH"])
@permission_classes([staff_perm("settings.manage")])
def level_update(request, pk):
    lv = get_object_or_404(Level, pk=pk)
    before = {"min": lv.min_rate_kobo, "max": lv.max_rate_kobo}
    lv.min_rate_kobo = int(request.data.get("min_rate_kobo", lv.min_rate_kobo))
    lv.max_rate_kobo = int(request.data.get("max_rate_kobo", lv.max_rate_kobo))
    if lv.min_rate_kobo > lv.max_rate_kobo:
        raise ValidationError("Minimum must be below maximum.")
    lv.save()
    audit(request.user, "rate_band.update", "level", lv.pk, before=before, after={"min": lv.min_rate_kobo, "max": lv.max_rate_kobo}, request=request)
    return Response({"id": lv.pk, "min_rate_kobo": lv.min_rate_kobo, "max_rate_kobo": lv.max_rate_kobo})


@api_view(["POST"])
@permission_classes([staff_perm("settings.manage")])
def subject_create(request):
    from django.utils.text import slugify

    name = (request.data.get("name") or "").strip()
    if not name:
        raise ValidationError({"name": "Required."})
    s, _ = Subject.objects.get_or_create(slug=slugify(name), defaults={"name": name})
    audit(request.user, "subject.create", "subject", s.pk, request=request)
    return Response({"id": s.pk, "name": s.name, "slug": s.slug}, status=201)


@api_view(["POST"])
@permission_classes([staff_perm("settings.manage")])
def area_create(request):
    from django.utils.text import slugify

    from core.models import LGA, Area

    lga = get_object_or_404(LGA, pk=request.data.get("lga"))
    name = (request.data.get("name") or "").strip()
    a = Area.objects.create(lga=lga, name=name, slug=slugify(name), lat=request.data.get("lat"), lng=request.data.get("lng"))
    audit(request.user, "area.create", "area", a.pk, request=request)
    return Response({"id": a.pk, "name": a.name, "slug": a.slug}, status=201)


# --- Audit log (ADM-04) & exports (ADM-05) --------------------------------


@api_view(["GET"])
@permission_classes([staff_perm("audit.view")])
def audit_log(request):
    qs = AuditLog.objects.select_related("actor")
    p = request.query_params
    if p.get("entity_type"):
        qs = qs.filter(entity_type=p["entity_type"])
    if p.get("entity_id"):
        qs = qs.filter(entity_id=p["entity_id"])
    if p.get("action"):
        qs = qs.filter(action__startswith=p["action"])
    return _paginate(request, qs, lambda a: {"id": a.pk, "actor": a.actor.get_full_name() if a.actor else "system", "action": a.action,
                                             "entity_type": a.entity_type, "entity_id": a.entity_id, "before": a.before, "after": a.after,
                                             "reason": a.reason, "ip": a.ip, "created_at": a.created_at})


EXPORTS = {
    "payments": (["reference", "parent", "amount_kobo", "fee_kobo", "status", "gateway", "channel", "created_at", "verified_at"],
                 lambda: Payment.objects.select_related("parent__user"),
                 lambda p: [p.reference, p.parent.user.get_full_name(), p.amount_kobo, p.fee_kobo, p.status, p.gateway, p.channel, p.created_at, p.verified_at]),
    "ledger": (["transaction", "kind", "description", "account", "debit_kobo", "credit_kobo", "created_at"],
               lambda: LedgerEntry.objects.select_related("transaction", "account"),
               lambda e: [e.transaction.reference, e.transaction.kind, e.transaction.description, str(e.account), e.debit_kobo, e.credit_kobo, e.created_at]),
    "payouts": (["payout", "tutor", "amount_kobo", "bank", "last4", "status", "reference", "updated_at"],
                lambda: PayoutItem.objects.select_related("tutor__user"),
                lambda i: [i.payout_id, i.tutor.user.get_full_name(), i.amount_kobo, i.bank_snapshot.get("bank_name"), i.bank_snapshot.get("last4"), i.status, i.transfer_reference, i.updated_at]),
    "bookings": (["id", "status", "parent", "tutor", "child", "package_size", "total_kobo", "commission_pct", "created_at"],
                 lambda: Booking.objects.select_related("parent__user", "tutor__user", "child"),
                 lambda b: [b.pk, b.status, b.parent.user.get_full_name(), b.tutor.user.get_full_name(), b.child.first_name, b.package_size, b.total_kobo, b.commission_pct, b.created_at]),
    "lessons": (["id", "booking", "tutor", "scheduled_start", "status", "escrow_status", "amount_kobo", "checkin_at", "checkout_at", "late_minutes"],
                lambda: Lesson.objects.select_related("tutor__user"),
                lambda l: [l.pk, l.booking_id, l.tutor.user.get_full_name(), l.scheduled_start, l.status, l.escrow_status, l.amount_kobo, l.checkin_at, l.checkout_at, l.late_minutes]),
    "users": (["id", "name", "email", "phone", "role", "date_joined", "verified", "suspended"],
              lambda: User.objects.all(),
              lambda u: [u.pk, u.get_full_name(), u.email, u.phone, u.role, u.date_joined, u.is_verified, bool(u.suspended_at)]),
}


@api_view(["GET"])
@permission_classes([staff_perm("reports.export")])
def export_csv(request, name):
    if name not in EXPORTS:
        raise ValidationError("Unknown export.")
    headers, qs_fn, row_fn = EXPORTS[name]
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="tutorbridge-{name}-{timezone.localdate()}.csv"'
    resp.write("﻿")  # BOM so Excel opens UTF-8 correctly
    w = csv.writer(resp)
    w.writerow(headers)
    qs = qs_fn()
    if request.query_params.get("from"):
        since = parse_date(request.query_params["from"])
        if since is None:
            raise ValidationError({"from": "Use YYYY-MM-DD."})
        qs = qs.filter(created_at__gte=day_start(since)) if hasattr(qs.model, "created_at") else qs
    for obj in qs.iterator():
        w.writerow(["'" + str(v) if isinstance(v, str) and v[:1] in "=+-@" else v for v in row_fn(obj)])  # CSV-injection guard
    audit(request.user, "export", "export", name, request=request)
    return resp


# --- Promo codes (PAY-10) ------------------------------------------------------

PROMO_FIELDS = ["description", "kind", "value", "max_discount_kobo", "min_spend_kobo", "first_booking_only", "packages_only",
                "valid_from", "valid_until", "max_uses", "max_uses_per_parent", "is_active"]


def _promo_json(p):
    from payments.models import PromoRedemption

    uses = PromoRedemption.objects.filter(promo=p).exclude(booking__status="cancelled")
    return {"id": p.pk, "code": p.code, **{f: getattr(p, f) for f in PROMO_FIELDS}, "uses": uses.count(),
            "discount_given_kobo": sum(uses.values_list("discount_kobo", flat=True)), "created_at": p.created_at}


def _promo_clean(data, partial=False):
    from django.utils.dateparse import parse_datetime

    from payments.models import PromoCode

    out = {}
    for f in PROMO_FIELDS:
        if f not in data:
            continue
        v = data[f]
        if f in ("valid_from", "valid_until"):
            v = parse_datetime(v) if v else None
        elif f in ("max_discount_kobo", "max_uses") and v in ("", None):
            v = None
        out[f] = v
    kind = out.get("kind")
    if not partial and kind not in PromoCode.Kind.values:
        raise ValidationError({"kind": "Choose percent or fixed."})
    value = out.get("value")
    if value is not None:
        value = int(value)
        if value <= 0 or (kind == "percent" and value > 100):
            raise ValidationError({"value": "Percent must be 1-100; fixed amounts must be positive."})
        out["value"] = value
    return out


@api_view(["GET", "POST"])
@permission_classes([staff_perm("promos.manage")])
def promos(request):
    from payments.models import PromoCode
    from payments.promotions import normalise

    if request.method == "POST":
        code = normalise(request.data.get("code"))
        if not code or not code.replace("-", "").isalnum():
            raise ValidationError({"code": "Use letters, numbers and dashes only."})
        if PromoCode.objects.filter(code=code).exists():
            raise ValidationError({"code": "That code already exists."})
        p = PromoCode.objects.create(code=code, created_by=request.user, **_promo_clean(request.data))
        audit(request.user, "promo.create", "promo", p.pk, after={"code": p.code, "kind": p.kind, "value": p.value, "max_uses": p.max_uses}, request=request)
        return Response(_promo_json(p), status=201)
    return Response([_promo_json(p) for p in PromoCode.objects.all()])


@api_view(["PATCH"])
@permission_classes([staff_perm("promos.manage")])
def promo_update(request, pk):
    from payments.models import PromoCode

    p = get_object_or_404(PromoCode, pk=pk)
    changes = _promo_clean(request.data, partial=True)
    for k, v in changes.items():
        setattr(p, k, v)
    p.save()
    audit(request.user, "promo.update", "promo", p.pk, after={k: str(v) for k, v in changes.items()}, request=request)
    return Response(_promo_json(p))


@api_view(["GET"])
@permission_classes([staff_perm("reports.view")])
def pilot_reports(request):
    """ADM-07: success metrics vs pilot targets, weekly trends, cohorts, fill rate by area. ?days=30|90|180, ?export=csv."""
    from backoffice.reports import pilot_report

    try:
        days = int(request.query_params.get("days", 30))
    except ValueError:
        raise ValidationError({"days": "Use a number of days."}) from None
    if days not in (7, 30, 90, 180, 365):
        raise ValidationError({"days": "Choose 7, 30, 90, 180 or 365."})
    report = pilot_report(days=days)
    if request.query_params.get("export") != "csv":
        return Response(report)
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="tutorbridge-pilot-report-{days}d-{timezone.localdate()}.csv"'
    resp.write("﻿")
    w = csv.writer(resp)
    w.writerow(["Metric", "Value", "Unit", "Target", "On target", "Sample size", "Definition"])
    for m in report["scorecard"]:
        w.writerow([m["label"], "" if m["value"] is None else m["value"], m["unit"].strip(), m["target"],
                    {True: "yes", False: "no", None: ""}[m["on_target"]], m["n"], m["hint"]])
    w.writerow([])
    w.writerow(["Week starting", "Requests", "Paid bookings", "Lessons delivered", "GMV (NGN)", "Fill rate %"])
    for r in report["weekly"]:
        w.writerow([r["week"], r["requests"], r["bookings"], r["lessons"], r["gmv_kobo"] / 100, "" if r["fill_rate"] is None else r["fill_rate"]])
    audit(request.user, "export", "export", "pilot_report", request=request)
    return resp


@api_view(["GET"])
@permission_classes([staff_perm("audit.view")])
def system_health(request):
    from core.health import checks

    return Response(checks())

