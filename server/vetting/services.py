import random
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from core import config
from core.audit import audit
from messaging.notify import notify_address
from tutors.services import check, maybe_activate
from vetting.models import CheckStatus, CheckType, Question, Reference, TestAttempt

QUESTIONS_PER_TEST = 20

# TUT-12: safeguarding course content (short pages + quiz). Edit here or move to the CMS later.
SAFEGUARDING_PAGES = [
    {"title": "Why safeguarding matters", "body": "You will often be the only non-family adult with a child. Families trust TutorBridge because every tutor follows the same clear rules. Breaking them ends your time on the platform."},
    {"title": "Where lessons happen", "body": "Lessons take place in a common area of the home (living or dining room), never in a bedroom. An adult must be present in the house for the whole lesson. If no adult is home, do not start the lesson; contact support."},
    {"title": "Contact and boundaries", "body": "No private contact with the child outside lessons: no phone numbers, social media, gifts or meetings. Do not take photos or videos of the child. Physical contact is limited to what is appropriate and necessary (e.g. a handshake)."},
    {"title": "Recognising and reporting concerns", "body": "If a child tells you something worrying, listen, don't promise secrecy, and report it to the TutorBridge safety team the same day using the safety button. If a child is in immediate danger, call 112 first."},
    {"title": "Your own safety", "body": "If you ever feel unsafe in a home, leave and use the safety button. You will still be paid for a lesson you had to leave for safety reasons once our team reviews the report."},
]
SAFEGUARDING_QUIZ = [
    {"q": "Where should a home lesson take place?", "options": ["The child's bedroom", "A common area of the home", "Anywhere quiet"], "answer": 1},
    {"q": "You arrive and no adult is home. What do you do?", "options": ["Start the lesson anyway", "Wait outside and contact support", "Take the child to a café"], "answer": 1},
    {"q": "A student asks for your WhatsApp number. You should:", "options": ["Share it", "Politely decline; use in-app messages with the parent", "Give it to the child's friend"], "answer": 1},
    {"q": "May you take a photo of the child's work showing their face?", "options": ["Yes", "No"], "answer": 1},
    {"q": "A child discloses something worrying. You should:", "options": ["Promise to keep it secret", "Report it to the safety team the same day", "Ignore it"], "answer": 1},
]
AGREEMENT_VERSION = "2026-10"


def start_test(tutor, subject, level):
    if not tutor.subjects.filter(subject=subject, level=level).exists():
        raise ValidationError("Add this subject and level to your profile first.")
    if TestAttempt.objects.filter(tutor=tutor, subject=subject, level=level, passed=True).exists():
        raise ValidationError("You have already passed this test.")
    recent = TestAttempt.objects.filter(tutor=tutor, subject=subject, level=level, started_at__gte=timezone.now() - timedelta(days=7))
    if recent.count() >= 2:
        raise ValidationError("You can attempt each test twice per week.")
    open_attempt = recent.filter(submitted_at__isnull=True, deadline__gt=timezone.now()).first()
    if open_attempt:
        return open_attempt
    ids = list(Question.objects.filter(subject=subject, level=level, is_active=True).values_list("id", flat=True))
    if len(ids) < 5:
        raise ValidationError("This test is not available yet. Our team has been notified.")
    random.shuffle(ids)
    return TestAttempt.objects.create(
        tutor=tutor, subject=subject, level=level, question_ids=ids[:QUESTIONS_PER_TEST],
        deadline=timezone.now() + timedelta(minutes=config.get("test_duration_minutes")),
    )


@transaction.atomic
def submit_test(attempt, answers):
    attempt = TestAttempt.objects.select_for_update().get(pk=attempt.pk)
    if attempt.submitted_at:
        raise ValidationError("This test has already been submitted.")
    late = timezone.now() > attempt.deadline + timedelta(seconds=30)
    questions = {q.id: q for q in Question.objects.filter(id__in=attempt.question_ids)}
    correct = 0 if late else sum(1 for qid in attempt.question_ids if str(qid) in answers and int(answers[str(qid)]) == questions[qid].correct_index)
    score = round(100 * correct / len(attempt.question_ids))
    attempt.answers, attempt.submitted_at, attempt.score_pct = answers, timezone.now(), score
    attempt.passed = score >= config.get("test_pass_mark_pct")
    attempt.save()
    ts = attempt.tutor.subjects.get(subject=attempt.subject, level=attempt.level)
    ts.test_score = max(ts.test_score or 0, score)
    ts.verified = ts.verified or attempt.passed
    ts.save(update_fields=["test_score", "verified"])
    subjects = list(attempt.tutor.subjects.all())
    c = check(attempt.tutor, CheckType.SUBJECT_TEST)
    if all(s.verified for s in subjects):
        c.status = CheckStatus.PASSED
    elif any(s.test_score is not None for s in subjects):
        c.status = CheckStatus.SUBMITTED
    c.result = {s.subject.name + " / " + s.level.name: s.test_score for s in subjects}
    c.save()
    return attempt


def safeguarding_submit(tutor, answers, signature, location_consent=False):
    if any(int(answers.get(str(i), -1)) != q["answer"] for i, q in enumerate(SAFEGUARDING_QUIZ)):
        raise ValidationError("Some answers are not right. Please review the course and try again.")
    full = tutor.user.get_full_name().lower()
    if signature.strip().lower() != full:
        raise ValidationError({"signature": f"Type your full name exactly as registered ({tutor.user.get_full_name()}) to sign."})
    now = timezone.now()
    tutor.safeguarding_completed_at = tutor.safeguarding_completed_at or now
    tutor.agreement_signed_at, tutor.agreement_signature, tutor.agreement_version = now, signature.strip(), AGREEMENT_VERSION
    tutor.location_consent = bool(location_consent)
    tutor.save()
    c = check(tutor, CheckType.SAFEGUARDING)
    c.status, c.result = CheckStatus.PASSED, {"agreement_version": AGREEMENT_VERSION, "signed_at": now.isoformat()}
    c.save()
    return tutor


def add_reference(tutor, data):
    ref = Reference(tutor=tutor, **data)
    token = ref.issue_token()
    ref.save()
    link = f"{settings.SITE_URL}/reference/{token}"
    notify_address(email=ref.email, event="referee_request", context={"name": ref.name, "tutor_name": tutor.user.get_full_name(), "link": link})
    return ref


def submit_reference(token, response):
    ref = Reference.objects.filter(token_hash=Reference.hash_token(token), submitted_at__isnull=True).first()
    if not ref:
        raise ValidationError("This link is invalid or has already been used.")
    ref.response, ref.submitted_at = response, timezone.now()
    ref.save(update_fields=["response", "submitted_at"])
    return ref


def decide_check(tutor, check_type, status, staff, notes="", extra=None, request=None):
    """Vetting officer passes/fails an individual check (TUT-13 checklist)."""
    c = check(tutor, check_type)
    before = c.status
    c.status, c.notes, c.reviewer, c.reviewed_at = status, notes, staff, timezone.now()
    if extra:
        c.result = {**(c.result or {}), **extra}
    if check_type == CheckType.BACKGROUND and status == CheckStatus.PASSED:
        valid_until = timezone.localdate() + timedelta(days=30 * config.get("reverification_months"))
        c.expires_at = valid_until
        tutor.background_valid_until = valid_until
        tutor.save(update_fields=["background_valid_until"])
    c.save()
    audit(staff, "vetting.check", "tutor", tutor.pk, before={check_type: before}, after={check_type: status}, reason=notes, request=request)
    if check_type == CheckType.BACKGROUND:
        maybe_activate(tutor, staff)
    return c


# --- Interview notifications (TUT-10) --------------------------------------


def _interview_ctx(slot):
    return {
        "when": timezone.localtime(slot.starts_at).strftime("%a %d %b, %H:%M"),
        "minutes": slot.duration_minutes,
        "link": slot.meeting_link or "We'll email you the meeting link before the interview.",
    }


def interview_booked(slot):
    from messaging.notify import notify

    ctx = _interview_ctx(slot)
    notify(slot.tutor.user, "interview_booked", ctx, link="/tutor/onboarding?step=interview")
    notify(slot.officer, "interview_booked_officer", {**ctx, "tutor_name": slot.tutor.user.get_full_name()}, link=f"/staff/vetting/{slot.tutor_id}",
           force_channels=("inapp",))


def send_interview_reminders():
    """Run every 5 minutes: remind tutors 24 hours and 1 hour before their interview (once each)."""
    from messaging.notify import notify

    from vetting.models import InterviewSlot

    now = timezone.now()
    upcoming = InterviewSlot.objects.filter(tutor__isnull=False, outcome="", starts_at__gt=now).select_related("tutor__user")
    sent = 0
    for slot in upcoming.filter(starts_at__lte=now + timedelta(hours=1), reminded_1h=False):
        notify(slot.tutor.user, "interview_soon", _interview_ctx(slot), link="/tutor/onboarding?step=interview")
        slot.reminded_1h = slot.reminded_24h = True
        slot.save(update_fields=["reminded_1h", "reminded_24h"])
        sent += 1
    for slot in upcoming.filter(starts_at__lte=now + timedelta(hours=24), reminded_24h=False):
        notify(slot.tutor.user, "interview_reminder", _interview_ctx(slot), link="/tutor/onboarding?step=interview")
        slot.reminded_24h = True
        slot.save(update_fields=["reminded_24h"])
        sent += 1
    return sent

