import re

from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts.permissions import IsTutor
from core.throttles import OTPThrottle
from tutors.services import check
from vetting import services
from vetting.kyc import verify_identity
from vetting.models import CheckStatus, CheckType, DocType, Document, InterviewSlot, Question, Reference, TestAttempt
from vetting.storage import absolute_path, delete_file, save_upload

TUTOR_DOC_TYPES = {DocType.CV, DocType.DEGREE, DocType.NCE, DocType.TRCN, DocType.CERTIFICATE, DocType.POLICE, DocType.PROOF_OF_ADDRESS}


class DocumentSerializer(serializers.ModelSerializer):
    doc_type_display = serializers.CharField(source="get_doc_type_display", read_only=True)

    class Meta:
        model = Document
        fields = ["id", "doc_type", "doc_type_display", "original_name", "content_type", "size", "status", "review_note", "created_at"]


@api_view(["GET", "POST"])
@permission_classes([IsTutor])
def documents(request):
    if request.method == "POST":
        doc_type = request.data.get("doc_type")
        if doc_type not in TUTOR_DOC_TYPES:
            return Response({"doc_type": "Unknown document type."}, status=400)
        if "file" not in request.FILES:
            return Response({"file": "Choose a file."}, status=400)
        doc = save_upload(request.FILES["file"], request.user, doc_type)
        tutor = request.user.tutor_profile
        if doc_type == DocType.POLICE:
            c = check(tutor, CheckType.BACKGROUND)
            c.status = CheckStatus.SUBMITTED
            c.save(update_fields=["status"])
        return Response(DocumentSerializer(doc).data, status=201)
    docs = request.user.documents.filter(doc_type__in=TUTOR_DOC_TYPES).order_by("-created_at")
    return Response(DocumentSerializer(docs, many=True).data)


@api_view(["DELETE"])
@permission_classes([IsTutor])
def delete_document(request, pk):
    doc = get_object_or_404(Document, pk=pk, owner=request.user, status="pending")
    delete_file(doc)
    doc.delete()
    return Response(status=204)


@api_view(["GET"])
def download_document(request, pk):
    """Permission-checked file serving: owner, or staff with the right permission."""
    doc = get_object_or_404(Document, pk=pk)
    u = request.user
    allowed = doc.owner_id == u.pk
    if u.is_staff_member and request.session.get("2fa_ok"):
        allowed = allowed or u.has_perm_code("vetting.view") or (doc.doc_type == DocType.EVIDENCE and u.has_perm_code("disputes.view"))
    if not allowed:
        raise Http404
    resp = FileResponse(open(absolute_path(doc), "rb"), content_type=doc.content_type)
    resp["Content-Disposition"] = f'inline; filename="{doc.doc_type}-{doc.pk}{absolute_path(doc).suffix}"'
    resp["Cache-Control"] = "private, no-store"
    return resp


@api_view(["GET", "POST"])
@permission_classes([IsTutor])
@throttle_classes([OTPThrottle])
def identity(request):
    tutor = request.user.tutor_profile
    c = check(tutor, CheckType.IDENTITY)
    if request.method == "GET":
        return Response({"status": c.status, "notes": c.notes if c.status == CheckStatus.FAILED else ""})
    if c.status in (CheckStatus.PASSED, CheckStatus.MANUAL_REVIEW, CheckStatus.SUBMITTED):
        return Response({"detail": "Your identity check is already in progress or complete."}, status=400)
    nin = re.sub(r"\D", "", request.data.get("nin", ""))
    if len(nin) != 11:
        return Response({"nin": "Your NIN has 11 digits."}, status=400)
    if "selfie" not in request.FILES:
        return Response({"selfie": "Take a clear selfie."}, status=400)
    selfie = save_upload(request.FILES["selfie"], request.user, DocType.SELFIE)
    provider, result = verify_identity(nin, absolute_path(selfie), request.user.first_name, request.user.last_name)
    c.provider, c.reference, c.status = provider, result.reference, result.status
    c.result = {**result.details, "selfie_document": selfie.pk, "nin": nin}
    c.save()
    return Response({"status": c.status})


# --- Subject tests (TUT-09) -----------------------------------------------


@api_view(["GET"])
@permission_classes([IsTutor])
def tests(request):
    tutor = request.user.tutor_profile
    out = []
    for ts in tutor.subjects.select_related("subject", "level"):
        attempts = TestAttempt.objects.filter(tutor=tutor, subject=ts.subject, level=ts.level).order_by("-started_at")
        available = Question.objects.filter(subject=ts.subject, level=ts.level, is_active=True).count() >= 5
        out.append({
            "subject": ts.subject_id, "subject_name": ts.subject.name, "level": ts.level_id, "level_name": ts.level.name,
            "best_score": ts.test_score, "passed": ts.verified, "attempts": attempts.count(), "available": available,
        })
    return Response(out)


@api_view(["POST"])
@permission_classes([IsTutor])
def start_test(request):
    from core.models import Level, Subject

    tutor = request.user.tutor_profile
    attempt = services.start_test(tutor, get_object_or_404(Subject, pk=request.data.get("subject")), get_object_or_404(Level, pk=request.data.get("level")))
    qs = {q.id: q for q in Question.objects.filter(id__in=attempt.question_ids)}
    return Response({
        "id": attempt.pk, "deadline": attempt.deadline,
        "questions": [{"id": qid, "text": qs[qid].text, "options": qs[qid].options} for qid in attempt.question_ids],
    })


@api_view(["POST"])
@permission_classes([IsTutor])
def submit_test(request, pk):
    attempt = get_object_or_404(TestAttempt, pk=pk, tutor=request.user.tutor_profile)
    attempt = services.submit_test(attempt, {str(k): v for k, v in (request.data.get("answers") or {}).items()})
    return Response({"score_pct": attempt.score_pct, "passed": attempt.passed})


# --- Interviews (TUT-10) --------------------------------------------------


@api_view(["GET"])
@permission_classes([IsTutor])
def interview_slots(request):
    tutor = request.user.tutor_profile
    mine = InterviewSlot.objects.filter(tutor=tutor).order_by("-starts_at").first()
    free = InterviewSlot.objects.filter(tutor__isnull=True, starts_at__gt=timezone.now()).order_by("starts_at")[:30]
    fmt = lambda s: {"id": s.pk, "starts_at": s.starts_at, "duration_minutes": s.duration_minutes}  # noqa: E731
    return Response({
        "booked": {**fmt(mine), "meeting_link": mine.meeting_link, "outcome": mine.outcome} if mine else None,
        "available": [fmt(s) for s in free],
    })


@api_view(["POST"])
@permission_classes([IsTutor])
def book_interview(request, pk):
    tutor = request.user.tutor_profile
    with transaction.atomic():
        if InterviewSlot.objects.filter(tutor=tutor, outcome="").exists():
            return Response({"detail": "You already have an interview booked."}, status=400)
        updated = InterviewSlot.objects.filter(pk=pk, tutor__isnull=True, starts_at__gt=timezone.now()).update(tutor=tutor)
        if not updated:
            return Response({"detail": "That slot was just taken. Please pick another."}, status=409)
        c = check(tutor, CheckType.INTERVIEW)
        c.status = CheckStatus.SUBMITTED
        c.save(update_fields=["status"])
    services.interview_booked(InterviewSlot.objects.select_related("officer").get(pk=pk))
    return Response({"detail": "Interview booked."})


# --- References & guarantor (TUT-11) --------------------------------------


class ReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reference
        fields = ["id", "kind", "name", "email", "phone", "relationship", "organisation", "is_professional", "submitted_at", "call_verified"]
        read_only_fields = ["submitted_at", "call_verified"]


@api_view(["GET", "POST"])
@permission_classes([IsTutor])
def references(request):
    tutor = request.user.tutor_profile
    if request.method == "POST":
        s = ReferenceSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        if tutor.references.filter(kind=s.validated_data["kind"]).count() >= (3 if s.validated_data["kind"] == "referee" else 1):
            return Response({"detail": "You have already added the maximum number."}, status=400)
        ref = services.add_reference(tutor, s.validated_data)
        return Response(ReferenceSerializer(ref).data, status=201)
    return Response(ReferenceSerializer(tutor.references.all(), many=True).data)


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def reference_form(request, token):
    ref = Reference.objects.filter(token_hash=Reference.hash_token(token)).select_related("tutor__user").first()
    if not ref or ref.submitted_at:
        return Response({"detail": "This link is invalid or has already been used."}, status=404)
    if request.method == "GET":
        return Response({"kind": ref.kind, "name": ref.name, "tutor_name": ref.tutor.user.get_full_name()})
    response = {k: str(request.data.get(k, ""))[:2000] for k in ("known_for", "capacity", "character", "teaching_ability", "concerns", "would_trust_with_children")}
    services.submit_reference(token, response)
    if ref.kind == "guarantor" and "id_document" in request.FILES:
        ref.id_document = save_upload(request.FILES["id_document"], ref.tutor.user, DocType.GUARANTOR_ID)
        ref.save(update_fields=["id_document"])
    return Response({"detail": "Thank you. Your response has been recorded."})


# --- Safeguarding (TUT-12) ------------------------------------------------


@api_view(["GET", "POST"])
@permission_classes([IsTutor])
def safeguarding(request):
    tutor = request.user.tutor_profile
    if request.method == "POST":
        services.safeguarding_submit(tutor, {str(k): v for k, v in (request.data.get("answers") or {}).items()},
                                     request.data.get("signature", ""), request.data.get("location_consent", False))
    return Response({
        "pages": services.SAFEGUARDING_PAGES,
        "quiz": [{"q": q["q"], "options": q["options"]} for q in services.SAFEGUARDING_QUIZ],
        "agreement_version": services.AGREEMENT_VERSION,
        "completed_at": tutor.safeguarding_completed_at,
        "agreement_signed_at": tutor.agreement_signed_at,
    })
