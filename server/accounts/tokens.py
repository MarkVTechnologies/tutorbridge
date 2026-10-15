from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    key_salt = "tutorbridge.email-verification"

    def _make_hash_value(self, user, timestamp):
        return f"{user.pk}{user.email}{user.email_verified_at}{timestamp}"


email_verification_token = EmailVerificationTokenGenerator()
# Django's default generator: invalidated once the password changes (single use), expires per PASSWORD_RESET_TIMEOUT.
password_reset_token = PasswordResetTokenGenerator()


def encode_uid(user):
    return urlsafe_base64_encode(force_bytes(user.pk))


def decode_uid(uid):
    try:
        return int(force_str(urlsafe_base64_decode(uid)))
    except (ValueError, TypeError):
        return None
