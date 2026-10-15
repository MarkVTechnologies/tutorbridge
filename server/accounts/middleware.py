import time

from django.conf import settings
from django.contrib.auth import logout


class StaffIdleTimeoutMiddleware:
    """Staff sessions expire after 8 hours of inactivity (section 15.1)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.is_staff_member:
            now = time.time()
            last = request.session.get("last_activity", now)
            if now - last > settings.STAFF_IDLE_TIMEOUT.total_seconds():
                logout(request)
            else:
                request.session["last_activity"] = now
        return self.get_response(request)
