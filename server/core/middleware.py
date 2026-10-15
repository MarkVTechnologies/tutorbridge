class SecurityHeadersMiddleware:
    """CSP and Permissions-Policy headers (section 15.1). HSTS etc. come from Django settings."""

    CSP = (
        "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; script-src 'self' https://js.paystack.co https://checkout.flutterwave.com; "
        "frame-src https://checkout.paystack.com https://checkout.flutterwave.com; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", self.CSP)
        response.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=(self), payment=(self)")
        return response
