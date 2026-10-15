import logging

import requests
from django.conf import settings

log = logging.getLogger(__name__)


def send_sms(to, body):
    """Send an SMS; returns provider reference. Raises on failure so the job is retried."""
    provider = settings.SMS_PROVIDER
    if provider == "termii":
        resp = requests.post(
            "https://api.ng.termii.com/api/sms/send",
            json={
                "api_key": settings.TERMII_API_KEY,
                "to": to.lstrip("+"),
                "from": settings.TERMII_SENDER_ID,
                "sms": body,
                "type": "plain",
                "channel": "dnd",
            },
            timeout=20,
        )
        resp.raise_for_status()
        return str(resp.json().get("message_id", ""))
    log.info("[SMS to %s] %s", to, body)
    return "console"
