from rest_framework.throttling import SimpleRateThrottle


class _ScopeThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        ident = request.user.pk if request.user and request.user.is_authenticated else self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class LoginThrottle(_ScopeThrottle):
    scope = "login"


class OTPThrottle(_ScopeThrottle):
    scope = "otp"


class ResetThrottle(_ScopeThrottle):
    scope = "password_reset"


class PaymentThrottle(_ScopeThrottle):
    scope = "payment"


class MessageThrottle(_ScopeThrottle):
    scope = "messages"
