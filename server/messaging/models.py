from django.conf import settings
from django.db import models


class Thread(models.Model):
    """MSG-01: a conversation between a parent and a tutor, only once a booking exists."""

    booking = models.OneToOneField("bookings.Booking", on_delete=models.CASCADE, related_name="thread")
    created_at = models.DateTimeField(auto_now_add=True)

    def participants(self):
        return [self.booking.parent.user_id, self.booking.tutor.user_id]


class Message(models.Model):
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    body = models.TextField()  # masked body, what participants see
    original_body = models.TextField(blank=True)  # MSG-03: retained for safety/ops staff only
    flagged = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]


class NotificationTemplate(models.Model):
    """MSG-04: admin-editable templates. Code defaults apply when no row exists."""

    key = models.CharField(max_length=60, unique=True)
    subject = models.CharField(max_length=200)
    body = models.TextField()
    sms_body = models.CharField(max_length=320, blank=True)


class Notification(models.Model):
    CHANNELS = [("email", "Email"), ("sms", "SMS"), ("inapp", "In-app")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="notifications")
    channel = models.CharField(max_length=10, choices=CHANNELS)
    event = models.CharField(max_length=60)
    to = models.CharField(max_length=200)  # email/phone (allows sending to non-users such as referees)
    subject = models.CharField(max_length=200, blank=True)
    body = models.TextField()
    link = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=10, default="queued")  # queued | sent | failed | read
    provider_ref = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
