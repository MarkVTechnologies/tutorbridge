from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from core import config
from core.audit import audit
from messaging.notify import notify
from tutors.models import StatusChange, TutorProfile, TutorStatus
from vetting.models import REQUIRED_FOR_APPROVAL, CheckStatus, CheckType, DocType, InterviewSlot, VerificationCheck


def check(tutor, check_type):
    obj, _ = VerificationCheck.objects.get_or_create(tutor=tutor, check_type=check_type)
    return obj


def onboarding_progress(tutor: TutorProfile):
    """TUT-01: progress is derived from saved data, so the wizard can always resume."""
    docs = set(tutor.user.documents.values_list("doc_type", flat=True))
    checks = {c.check_type: c.status for c in tutor.checks.all()}
    refs = list(tutor.references.all())
    subjects = list(tutor.subjects.all())

    def chk(t, *ok):
        return checks.get(t, CheckStatus.PENDING) in (ok or (CheckStatus.SUBMITTED, CheckStatus.MANUAL_REVIEW, CheckStatus.PASSED))

    steps = [
        ("profile", "Personal details", bool(tutor.headline and tutor.bio and tutor.photo_id)),
        ("subjects", "Subjects & levels", bool(subjects) and tutor.curricula.exists()),
        ("areas", "Areas you serve", bool(tutor.home_area_id) and tutor.areas.exists()),
        ("availability", "Weekly availability", tutor.availability.exists()),
        ("rate", "Hourly rate", rate_in_band(tutor)),
        ("documents", "Documents", "cv" in docs and bool(docs & {"degree", "nce"}) and "proof_of_address" in docs),
        ("identity", "NIN & selfie", chk(CheckType.IDENTITY)),
        ("bank", "Bank account", chk(CheckType.BANK, CheckStatus.PASSED, CheckStatus.MANUAL_REVIEW)),
        ("tests", "Subject tests", bool(subjects) and all(s.test_score is not None and s.verified for s in subjects)),
        ("interview", "Interview", InterviewSlot.objects.filter(tutor=tutor).exists() or chk(CheckType.INTERVIEW, CheckStatus.PASSED)),
        ("references", "Referees & guarantor",
         sum(1 for r in refs if r.kind == "referee") >= 2 and any(r.kind == "referee" and r.is_professional for r in refs) and any(r.kind == "guarantor" for r in refs)),
        ("safeguarding", "Safeguarding & agreement", bool(tutor.safeguarding_completed_at and tutor.agreement_signed_at)),
    ]
    done = sum(1 for _, _, ok in steps if ok)
    return {
        "steps": [{"key": k, "label": label, "done": ok} for k, label, ok in steps],
        "completed": done,
        "total": len(steps),
        "can_submit": done == len(steps),
        "police_certificate_uploaded": DocType.POLICE in docs,
    }


def rate_in_band(tutor):
    if not tutor.hourly_rate_kobo:
        return False
    levels = {s.level for s in tutor.subjects.all()}
    return bool(levels) and all(lv.min_rate_kobo <= tutor.hourly_rate_kobo <= lv.max_rate_kobo for lv in levels)


def rate_band(tutor):
    levels = {s.level for s in tutor.subjects.all()}
    if not levels:
        return None
    return {"min_kobo": max(lv.min_rate_kobo for lv in levels), "max_kobo": min(lv.max_rate_kobo for lv in levels)}


@transaction.atomic
def set_status(tutor, new_status, by_user=None, reason=""):
    old = tutor.status
    if old == new_status:
        return tutor
    tutor.status = new_status
    fields = ["status"]
    if new_status == TutorStatus.APPROVED:
        tutor.approved_at = timezone.now()
        tutor.reverify_due = date.today() + timedelta(days=30 * config.get("reverification_months"))
        fields += ["approved_at", "reverify_due"]
    tutor.save(update_fields=fields)
    StatusChange.objects.create(tutor=tutor, from_status=old, to_status=new_status, changed_by=by_user, reason=reason)
    audit(by_user, "tutor.status", "tutor", tutor.pk, before={"status": old}, after={"status": new_status}, reason=reason)
    if new_status == TutorStatus.ACTIVE and old != TutorStatus.SUSPENDED:
        notify(tutor.user, "tutor_approved")
    elif new_status in (TutorStatus.INTERVIEW, TutorStatus.REJECTED, TutorStatus.UNDER_REVIEW, TutorStatus.APPROVED):
        notify(tutor.user, "tutor_status", {"status": tutor.get_status_display(), "reason": reason})
    return tutor


def submit_application(tutor):
    progress = onboarding_progress(tutor)
    if not progress["can_submit"]:
        missing = [s["label"] for s in progress["steps"] if not s["done"]]
        raise ValidationError({"detail": "Please complete: " + ", ".join(missing)})
    if tutor.status not in (TutorStatus.APPLIED,):
        raise ValidationError({"detail": "Your application has already been submitted."})
    tutor.submitted_at = timezone.now()
    tutor.save(update_fields=["submitted_at"])
    for ct in (CheckType.CREDENTIALS, CheckType.REFERENCES, CheckType.GUARANTOR, CheckType.ADDRESS):
        c = check(tutor, ct)
        if c.status == CheckStatus.PENDING:
            c.status = CheckStatus.SUBMITTED
            c.save(update_fields=["status"])
    return set_status(tutor, TutorStatus.UNDER_REVIEW, tutor.user, "Application submitted")


def approval_blockers(tutor):
    statuses = {c.check_type: c.status for c in tutor.checks.all()}
    return [CheckType(t).label for t in REQUIRED_FOR_APPROVAL if statuses.get(t) != CheckStatus.PASSED]


def approve(tutor, staff, reason=""):
    blockers = approval_blockers(tutor)
    if blockers:
        raise ValidationError({"detail": "These checks have not passed yet: " + ", ".join(blockers)})
    set_status(tutor, TutorStatus.APPROVED, staff, reason or "All checks passed")
    maybe_activate(tutor, staff)
    return tutor


def maybe_activate(tutor, staff=None):
    """Approved tutors become Active (searchable) once the background check is valid (required before the first home visit)."""
    bg = tutor.checks.filter(check_type=CheckType.BACKGROUND, status=CheckStatus.PASSED).first()
    if tutor.status == TutorStatus.APPROVED and bg and tutor.background_valid_until and tutor.background_valid_until >= date.today():
        set_status(tutor, TutorStatus.ACTIVE, staff, "Background check valid")
    return tutor
