"""
Notification dispatch (MSG-04, MSG-05, MSG-07).

`notify(user, "event_key", context)` renders the event template and queues
email/SMS/in-app notifications according to the event's channels and the
user's preferences. Delivery runs in the background job queue.
"""
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from core.jobs import enqueue, job_handler
from messaging.models import Notification, NotificationTemplate
from messaging.sms import send_sms

# event: (channels, subject, body, sms_body). Bodies use str.format with the context.
DEFAULT_TEMPLATES = {
    "verify_email": (("email",), "Verify your TutorBridge email", "Hi {first_name},\n\nConfirm your email address: {link}\n", ""),
    "phone_otp": (("sms",), "", "", "Your TutorBridge verification code is {code}. It expires in 10 minutes."),
    "bank_change_otp": (("sms",), "", "", "Your TutorBridge code to change your bank account is {code}. If this wasn't you, contact support now."),
    "password_reset": (("email",), "Reset your TutorBridge password", "Hi {first_name},\n\nReset your password (link valid for 30 minutes, single use): {link}\n\nIf you did not ask for this, ignore this email.", ""),
    "account_locked": (("email", "sms"), "Your account was locked", "Hi {first_name},\n\nWe locked your account for 15 minutes after 5 failed sign-in attempts. If this wasn't you, reset your password.", "TutorBridge: your account was locked for 15 min after 5 failed logins. Not you? Reset your password."),
    "tutor_status": (("email", "inapp"), "Your TutorBridge application: {status}", "Hi {first_name},\n\nYour application status is now: {status}.\n{reason}", ""),
    "tutor_approved": (("email", "sms", "inapp"), "Welcome to TutorBridge!", "Hi {first_name},\n\nCongratulations — you are approved and now visible to families.", "TutorBridge: you're approved! Families can now find you."),
    "referee_request": (("email",), "Reference request for {tutor_name}", "Hello {name},\n\n{tutor_name} has named you as a referee for TutorBridge. Please complete this short form: {link}", ""),
    "shortlist_ready": (("email", "sms", "inapp"), "Your tutor shortlist is ready", "Hi {first_name},\n\nWe have shortlisted tutors for {child_name}. View them: {link}", "TutorBridge: your tutor shortlist for {child_name} is ready. Log in to view."),
    "request_invite": (("email", "sms", "inapp"), "New lesson request near you", "Hi {first_name},\n\nYou've been invited to a lesson request ({subjects}, {area}). Respond in your dashboard.", "TutorBridge: new lesson request ({subjects}, {area}). Respond in your dashboard."),
    "booking_offer": (("email", "sms", "inapp"), "New booking — please accept within {hours} hours", "Hi {first_name},\n\nA family has booked you ({lessons} lessons, {subjects}). Accept within {hours} hours or it will be offered to another tutor.", "TutorBridge: new booking ({lessons} lessons). Accept within {hours}h."),
    "booking_confirmed": (("email", "sms", "inapp"), "Your booking is confirmed", "Hi {first_name},\n\n{tutor_name} has accepted your booking. First lesson: {first_lesson}.", "TutorBridge: {tutor_name} accepted your booking. First lesson {first_lesson}."),
    "booking_reassigned": (("email", "inapp"), "We've offered your booking to another tutor", "Hi {first_name},\n\nYour previous tutor didn't respond in time, so we've offered your booking to {tutor_name}.", ""),
    "booking_unfilled": (("email", "inapp"), "We're finding you another tutor", "Hi {first_name},\n\nNo shortlisted tutor could take your booking. Our team is finding a replacement; your payment stays safely in your wallet.", ""),
    "package_renewed": (("email", "sms", "inapp"), "Your package with {tutor_name} has renewed", "Hi {first_name},\n\nYour {lessons}-lesson package for {child_name} with {tutor_name} has renewed, starting {first_lesson}. {paid_with}\n\nYou can turn off auto-renewal any time from the booking page.", "TutorBridge: {child_name}'s package with {tutor_name} renewed from {first_lesson}."),
    "renewal_payment_needed": (("email", "sms", "inapp"), "Action needed: renew {child_name}'s lessons", "Hi {first_name},\n\nWe've held {tutor_name}'s slots for {child_name}'s next {lessons} lessons, but couldn't take payment automatically ({reason}). Please pay {amount} within {hours} hours to keep the slots: {link}", "TutorBridge: please pay {amount} within {hours}h to keep {child_name}'s lesson slots. Open the app to pay."),
    "renewal_failed": (("email", "inapp"), "We couldn't renew {child_name}'s package", "Hi {first_name},\n\nWe couldn't renew {child_name}'s package with {tutor_name}: {reason}. Auto-renewal has been turned off. Our team can help you book again.", ""),
    "tutor_package_renewed": (("email", "inapp"), "{child_name}'s package has renewed", "Hi {first_name},\n\nThe family renewed {child_name}'s package: {lessons} more lessons from {first_lesson}, same schedule.", ""),
    "payment_received": (("email", "inapp"), "Payment received — {amount}", "Hi {first_name},\n\nWe received {amount} (ref {reference}). Your receipt is in your dashboard.", ""),
    "lesson_reminder": (("sms", "inapp"), "", "Lesson reminder: {when}", "TutorBridge reminder: lesson {when}. Check-in code: {code}"),
    "lesson_reminder_tutor": (("sms", "inapp"), "", "Lesson reminder: {when} at {area}", "TutorBridge reminder: lesson {when} at {area}."),
    "tutor_checked_in": (("sms", "inapp"), "", "{tutor_name} checked in at {time}.", "TutorBridge: {tutor_name} checked in at {time}."),
    "tutor_checked_out": (("email", "inapp"), "Lesson completed — notes inside", "Hi {first_name},\n\n{tutor_name} checked out at {time}.\n\nTopics: {topics}\nHomework: {homework}", ""),
    "tutor_late": (("sms", "inapp"), "", "{tutor_name} has not checked in yet for the {when} lesson.", "TutorBridge: {tutor_name} hasn't checked in for the {when} lesson. We're on it."),
    "no_show": (("email", "sms", "inapp"), "Missed lesson", "The lesson on {when} was recorded as a tutor no-show. The lesson has been credited to your wallet.", "TutorBridge: lesson {when} marked as no-show. Credited to your wallet."),
    "lesson_cancelled": (("email", "inapp"), "Lesson cancelled", "The lesson on {when} was cancelled. {detail}", ""),
    "dispute_update": (("email", "inapp"), "Dispute update: {status}", "Your dispute about the lesson on {when} is now {status}.\n{notes}", ""),
    "safety_alert": (("email", "sms"), "URGENT safety report #{id}", "URGENT safety report #{id} from {reporter} ({role}).\nSeverity: {severity}\n{description}", "URGENT TutorBridge safety report #{id} from {reporter}: {description}"),
    "payout_sent": (("email", "sms", "inapp"), "Payout sent — {amount}", "Hi {first_name},\n\nWe've sent {amount} to your bank account ending {last4}.", "TutorBridge: payout of {amount} sent to account ending {last4}."),
    "payout_failed": (("email", "inapp"), "Payout issue", "Hi {first_name},\n\nYour payout of {amount} could not be completed. Our finance team will retry or contact you.", ""),
    "new_message": (("inapp",), "", "New message from {sender}", ""),
    "account_suspended": (("email",), "Your account has been suspended", "Hi {first_name},\n\nYour account has been suspended pending review.\nReason: {reason}", ""),
    "review_reminder": (("email", "inapp"), "How was {tutor_name}?", "Hi {first_name},\n\nPlease rate your lessons with {tutor_name}.", ""),
    "reverification_due": (("email", "inapp"), "Time to re-verify your TutorBridge account", "Hi {first_name},\n\nYour annual identity and background re-verification is due by {due}. Please upload a fresh police certificate and repeat your ID check.", ""),
    "finance_alert": (("email",), "Finance alert: {title}", "{detail}", ""),
}


class _SafeDict(dict):
    def __missing__(self, key):
        return ""


def render(event, context):
    channels, subject, body, sms_body = DEFAULT_TEMPLATES[event]
    override = NotificationTemplate.objects.filter(key=event).first()
    if override:
        subject, body, sms_body = override.subject, override.body, override.sms_body or sms_body
    ctx = _SafeDict(context)
    return channels, subject.format_map(ctx), body.format_map(ctx), sms_body.format_map(ctx)


def notify(user, event, context=None, link="", force_channels=None):
    context = {"first_name": getattr(user, "first_name", ""), **(context or {})}
    channels, subject, body, sms_body = render(event, context)
    channels = force_channels or channels
    prefs = (getattr(user, "notification_prefs", None) or {}) if user else {}
    created = []
    for channel in channels:
        # MSG-07: users can opt out of non-critical channels; security events always go out.
        if prefs.get(channel) is False and event not in {"phone_otp", "bank_change_otp", "password_reset", "verify_email", "account_locked"}:
            continue
        if channel == "email":
            n = Notification.objects.create(user=user, channel="email", event=event, to=user.email, subject=subject, body=body, link=link)
            enqueue("send_email", {"notification_id": n.pk})
        elif channel == "sms" and sms_body:
            n = Notification.objects.create(user=user, channel="sms", event=event, to=user.phone, body=sms_body, link=link)
            enqueue("send_sms", {"notification_id": n.pk})
        elif channel == "inapp":
            n = Notification.objects.create(user=user, channel="inapp", event=event, to=str(user.pk), subject=subject, body=body.split("\n\n")[-1] if body else sms_body, link=link, status="sent")
        else:
            continue
        created.append(n)
    return created


def notify_address(email=None, phone=None, event="", context=None):
    """Notify a non-user (referee, guarantor, safety officer)."""
    channels, subject, body, sms_body = render(event, context or {})
    if email and "email" in channels:
        n = Notification.objects.create(channel="email", event=event, to=email, subject=subject, body=body)
        enqueue("send_email", {"notification_id": n.pk})
    if phone and "sms" in channels and sms_body:
        n = Notification.objects.create(channel="sms", event=event, to=phone, body=sms_body)
        enqueue("send_sms", {"notification_id": n.pk})


@job_handler("send_email")
def _send_email(notification_id):
    n = Notification.objects.get(pk=notification_id)
    if n.status == "sent":
        return
    send_mail(n.subject, n.body, settings.DEFAULT_FROM_EMAIL, [n.to], fail_silently=False)
    n.status, n.sent_at = "sent", timezone.now()
    n.save(update_fields=["status", "sent_at"])


@job_handler("send_sms")
def _send_sms(notification_id):
    n = Notification.objects.get(pk=notification_id)
    if n.status == "sent":
        return
    n.provider_ref = send_sms(n.to, n.body)
    n.status, n.sent_at = "sent", timezone.now()
    n.save(update_fields=["status", "sent_at", "provider_ref"])
