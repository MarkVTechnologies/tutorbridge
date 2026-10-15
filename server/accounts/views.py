from datetime import timedelta

import pyotp
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.db import transaction
from django.db.models import Q
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from accounts.models import OTPCode, Role, User
from accounts.phone import normalise_phone
from accounts.serializers import PasswordResetSerializer, SignupSerializer, UserSerializer
from accounts.tokens import decode_uid, email_verification_token, encode_uid, password_reset_token
from core.audit import audit
from core.throttles import LoginThrottle, OTPThrottle, ResetThrottle
from messaging.notify import notify


def _session_payload(request, user):
    data = UserSerializer(user).data
    data["two_factor_ok"] = bool(request.session.get("2fa_ok"))
    data["needs_2fa_setup"] = user.is_staff_member and not user.totp_enabled
    return data


def send_email_verification(user):
    link = f"{settings.SITE_URL}/verify-email?uid={encode_uid(user)}&token={email_verification_token.make_token(user)}"
    notify(user, "verify_email", {"link": link})


@api_view(["GET"])
@permission_classes([AllowAny])
def csrf(request):
    return Response({"csrfToken": get_token(request)})


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginThrottle])
def signup(request):
    s = SignupSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    d = s.validated_data
    with transaction.atomic():
        user = User.objects.create_user(
            email=d["email"], phone=d["phone"], password=d["password"], first_name=d["first_name"],
            last_name=d["last_name"], gender=d.get("gender", ""), role=d["role"],
            consent_terms_at=timezone.now(), consent_marketing=d.get("consent_marketing", False),
        )
        if user.role == Role.PARENT:
            from parents.models import ParentProfile

            ParentProfile.objects.create(user=user)
        else:
            from tutors.models import TutorProfile

            TutorProfile.objects.create(user=user)
        send_email_verification(user)
        code = OTPCode.issue(user, "phone")
        notify(user, "phone_otp", {"code": code})
    login(request, user, backend="accounts.backends.EmailOrPhoneBackend")
    return Response(_session_payload(request, user), status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginThrottle])
def login_view(request):
    identifier = (request.data.get("identifier") or "").strip()
    password = request.data.get("password") or ""
    phone = normalise_phone(identifier)
    candidate = User.objects.filter(Q(email__iexact=identifier) | Q(phone=phone or "__none__")).first()
    generic_error = Response({"detail": "Incorrect email/phone or password."}, status=400)

    if candidate and candidate.is_locked:
        return Response({"detail": "Too many failed attempts. Try again in 15 minutes."}, status=423)

    user = authenticate(request, username=identifier, password=password)
    if user is None:
        if candidate:
            candidate.failed_login_count += 1
            if candidate.failed_login_count >= settings.LOGIN_LOCKOUT_ATTEMPTS:
                candidate.locked_until = timezone.now() + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
                candidate.failed_login_count = 0
                notify(candidate, "account_locked")
            candidate.save(update_fields=["failed_login_count", "locked_until"])
        return generic_error

    if user.suspended_at:
        return Response({"detail": "This account is suspended. Contact support."}, status=403)

    user.failed_login_count, user.locked_until = 0, None
    user.save(update_fields=["failed_login_count", "locked_until"])

    if user.totp_enabled:
        # Password OK, but no session until the TOTP code is verified.
        request.session["pending_2fa_user"] = user.pk
        request.session["pending_2fa_remember"] = bool(request.data.get("remember"))
        return Response({"requires_2fa": True})

    login(request, user)
    if not request.data.get("remember"):
        request.session.set_expiry(0)  # browser-session cookie
    return Response(_session_payload(request, user))


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([OTPThrottle])
def two_factor_login(request):
    user_id = request.session.get("pending_2fa_user")
    user = User.objects.filter(pk=user_id, is_active=True).first() if user_id else None
    if not user or not pyotp.TOTP(user.totp_secret).verify(str(request.data.get("code", "")), valid_window=1):
        return Response({"detail": "Invalid code."}, status=400)
    remember = request.session.get("pending_2fa_remember")
    login(request, user, backend="accounts.backends.EmailOrPhoneBackend")
    request.session["2fa_ok"] = True
    if not remember:
        request.session.set_expiry(0)
    return Response(_session_payload(request, user))


@api_view(["POST"])
def logout_view(request):
    logout(request)
    return Response(status=204)


@api_view(["GET", "PATCH"])
@permission_classes([AllowAny])
def me(request):
    if not request.user.is_authenticated:
        return Response({"detail": "Not signed in."}, status=401)
    if request.method == "PATCH":
        allowed = {k: v for k, v in request.data.items() if k in {"first_name", "last_name", "notification_prefs", "consent_marketing", "consent_location"}}
        s = UserSerializer(request.user, data=allowed, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
    return Response(_session_payload(request, request.user))


@api_view(["POST"])
@permission_classes([AllowAny])
def verify_email(request):
    user = User.objects.filter(pk=decode_uid(request.data.get("uid", ""))).first()
    if not user or not email_verification_token.check_token(user, request.data.get("token", "")):
        return Response({"detail": "This link is invalid or has expired."}, status=400)
    if not user.email_verified_at:
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at"])
    return Response({"detail": "Email verified."})


@api_view(["POST"])
@throttle_classes([OTPThrottle])
def resend_email_verification(request):
    if not request.user.email_verified_at:
        send_email_verification(request.user)
    return Response({"detail": "Verification email sent."})


@api_view(["POST"])
@throttle_classes([OTPThrottle])
def send_phone_otp(request):
    if request.user.phone_verified_at:
        return Response({"detail": "Phone already verified."})
    notify(request.user, "phone_otp", {"code": OTPCode.issue(request.user, "phone")})
    return Response({"detail": "Code sent."})


@api_view(["POST"])
@throttle_classes([OTPThrottle])
def verify_phone(request):
    if not OTPCode.verify(request.user, "phone", request.data.get("code", "")):
        return Response({"detail": "Invalid or expired code."}, status=400)
    request.user.phone_verified_at = timezone.now()
    request.user.save(update_fields=["phone_verified_at"])
    return Response(_session_payload(request, request.user))


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([ResetThrottle])
def forgot_password(request):
    user = User.objects.filter(email__iexact=(request.data.get("email") or "").strip()).first()
    if user and user.is_active:
        link = f"{settings.SITE_URL}/reset-password?uid={encode_uid(user)}&token={password_reset_token.make_token(user)}"
        notify(user, "password_reset", {"link": link})
    # Same response whether or not the account exists (no user enumeration).
    return Response({"detail": "If that email is registered, a reset link is on its way."})


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([ResetThrottle])
def reset_password(request):
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError

    s = PasswordResetSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    user = User.objects.filter(pk=decode_uid(s.validated_data["uid"])).first()
    if not user or not password_reset_token.check_token(user, s.validated_data["token"]):
        return Response({"detail": "This link is invalid or has expired."}, status=400)
    try:
        validate_password(s.validated_data["password"], user)
    except ValidationError as e:
        return Response({"password": e.messages}, status=400)
    user.set_password(s.validated_data["password"])
    user.failed_login_count, user.locked_until = 0, None
    user.save()
    audit(user, "auth.password_reset", "user", user.pk, request=request)
    return Response({"detail": "Password updated. You can now sign in."})


@api_view(["GET"])
def two_factor_setup(request):
    user = request.user
    if user.totp_enabled:
        return Response({"detail": "Two-factor is already enabled."}, status=400)
    if not user.totp_secret:
        user.totp_secret = pyotp.random_base32()
        user.save(update_fields=["totp_secret"])
    import io

    import qrcode
    import qrcode.image.svg

    uri = pyotp.TOTP(user.totp_secret).provisioning_uri(name=user.email, issuer_name="TutorBridge")
    buf = io.BytesIO()
    qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=8).save(buf)
    return Response({"secret": user.totp_secret, "otpauth_uri": uri, "qr_svg": buf.getvalue().decode()})


@api_view(["POST"])
@throttle_classes([OTPThrottle])
def two_factor_enable(request):
    user = request.user
    if not user.totp_secret or not pyotp.TOTP(user.totp_secret).verify(str(request.data.get("code", "")), valid_window=1):
        return Response({"detail": "Invalid code."}, status=400)
    user.totp_enabled = True
    user.save(update_fields=["totp_enabled"])
    request.session["2fa_ok"] = True
    audit(user, "auth.2fa_enabled", "user", user.pk, request=request)
    return Response(_session_payload(request, user))


@api_view(["POST"])
@throttle_classes([OTPThrottle])
def two_factor_verify(request):
    """Re-confirm a TOTP code inside an existing session (used before sensitive actions)."""
    user = request.user
    if not user.totp_enabled or not pyotp.TOTP(user.totp_secret).verify(str(request.data.get("code", "")), valid_window=1):
        return Response({"detail": "Invalid code."}, status=400)
    request.session["2fa_ok"] = True
    request.session["2fa_fresh_at"] = timezone.now().timestamp()
    return Response(_session_payload(request, user))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def two_factor_disable(request):
    user = request.user
    if user.is_staff_member:
        return Response({"detail": "Two-factor authentication is mandatory for staff."}, status=400)
    if not pyotp.TOTP(user.totp_secret).verify(str(request.data.get("code", "")), valid_window=1):
        return Response({"detail": "Invalid code."}, status=400)
    user.totp_enabled, user.totp_secret = False, ""
    user.save(update_fields=["totp_enabled", "totp_secret"])
    return Response(_session_payload(request, user))


@api_view(["GET"])
def export_my_data(request):
    """NDPA data-subject right: download my data."""
    user = request.user
    data = {"account": UserSerializer(user).data}
    if user.role == Role.PARENT and hasattr(user, "parent_profile"):
        from parents.serializers import ChildSerializer, ParentProfileSerializer

        data["profile"] = ParentProfileSerializer(user.parent_profile).data
        data["children"] = ChildSerializer(user.parent_profile.children.all(), many=True).data
    if user.role == Role.TUTOR and hasattr(user, "tutor_profile"):
        from tutors.serializers import TutorOwnProfileSerializer

        data["profile"] = TutorOwnProfileSerializer(user.tutor_profile).data
    data["notifications"] = list(user.notifications.values("channel", "event", "subject", "created_at")[:500])
    return Response(data)
