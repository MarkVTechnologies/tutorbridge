from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

from accounts.models import User
from accounts.phone import normalise_phone


class EmailOrPhoneBackend(ModelBackend):
    """AUTH-03: log in with email or phone number + password."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None
        identifier = username.strip()
        phone = normalise_phone(identifier)
        user = User.objects.filter(Q(email__iexact=identifier) | Q(phone=phone or "__none__")).first()
        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    def get_user(self, user_id):
        return User.objects.filter(pk=user_id, is_active=True).first()
