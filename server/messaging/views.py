from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from bookings.models import BookingStatus
from core.throttles import MessageThrottle
from messaging.masking import mask
from messaging.models import Message, Notification, Thread
from messaging.notify import notify

FLAG_ALERT_THRESHOLD = 3


def _threads_for(user):
    return Thread.objects.filter(Q(booking__parent__user=user) | Q(booking__tutor__user=user)).select_related(
        "booking__parent__user", "booking__tutor__user", "booking__child")


@api_view(["GET"])
def threads(request):
    out = []
    for t in _threads_for(request.user).order_by("-created_at"):
        b = t.booking
        other = b.tutor.user if request.user.pk == b.parent.user_id else b.parent.user
        last = t.messages.order_by("-created_at").first()
        out.append({
            "id": t.pk, "booking": b.pk, "with": other.display_name, "child": b.child.first_name,
            "last_message": last.body[:120] if last else "", "last_at": last.created_at if last else t.created_at,
            "unread": t.messages.filter(read_at__isnull=True).exclude(sender=request.user).count(),
        })
    out.sort(key=lambda r: r["last_at"], reverse=True)
    return Response(out)


@api_view(["GET", "POST"])
@throttle_classes([MessageThrottle])
def messages(request, pk):
    thread = get_object_or_404(_threads_for(request.user), pk=pk)
    if request.method == "POST":
        if thread.booking.status in (BookingStatus.CANCELLED, BookingStatus.AWAITING_PAYMENT):
            raise ValidationError("Messaging is closed for this booking.")
        body = (request.data.get("body") or "").strip()
        if not body:
            raise ValidationError({"body": "Write a message."})
        if len(body) > 2000:
            raise ValidationError({"body": "Messages are limited to 2,000 characters."})
        masked, flagged = mask(body)
        Message.objects.create(thread=thread, sender=request.user, body=masked, original_body=body, flagged=flagged)
        if flagged:
            attempts = Message.objects.filter(thread__booking__in=_booking_ids(request.user), sender=request.user, flagged=True).count()
            if attempts >= FLAG_ALERT_THRESHOLD and attempts % FLAG_ALERT_THRESHOLD == 0:
                _flag_alert(request.user, thread, attempts)
        b = thread.booking
        recipient = b.tutor.user if request.user.pk == b.parent.user_id else b.parent.user
        notify(recipient, "new_message", {"sender": request.user.display_name}, link=f"/messages/{thread.pk}")
    thread.messages.filter(read_at__isnull=True).exclude(sender=request.user).update(read_at=timezone.now())
    return Response([
        {"id": m.id, "mine": m.sender_id == request.user.pk, "sender": m.sender.display_name, "body": m.body, "masked": m.flagged, "created_at": m.created_at}
        for m in thread.messages.select_related("sender").order_by("created_at")
    ])


def _booking_ids(user):
    return Thread.objects.filter(Q(booking__parent__user=user) | Q(booking__tutor__user=user)).values("booking_id")


def _flag_alert(user, thread, attempts):
    """MSG-02: repeated attempts to share contact details are flagged to safety staff."""
    from accounts.models import Role, User

    for u in User.objects.filter(role__in=[Role.SAFETY, Role.OPS], is_active=True):
        notify(u, "finance_alert", {"title": f"Contact-sharing attempts by {user.get_full_name()}",
                                    "detail": f"{attempts} masked messages (latest in thread #{thread.pk})."}, force_channels=("inapp",))


@api_view(["GET"])
def notifications(request):
    qs = Notification.objects.filter(user=request.user, channel="inapp").order_by("-created_at")[:50]
    return Response({
        "unread": Notification.objects.filter(user=request.user, channel="inapp", status="sent").count(),
        "items": [{"id": n.id, "event": n.event, "subject": n.subject, "body": n.body, "link": n.link, "read": n.status == "read", "created_at": n.created_at} for n in qs],
    })


@api_view(["POST"])
def notifications_read(request):
    Notification.objects.filter(user=request.user, channel="inapp", status="sent").update(status="read")
    return Response({"unread": 0})
