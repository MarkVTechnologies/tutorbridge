"""Application-level field encryption for sensitive data (section 15.1)."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.db import models


def _fernet():
    keys = list(settings.FIELD_ENCRYPTION_KEYS)
    if not keys:
        if not (settings.DEBUG or settings.TESTING):
            raise RuntimeError("FIELD_ENCRYPTION_KEYS must be set in production")
        # Development only: derive a key from SECRET_KEY.
        keys = [base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()).decode()]
    return MultiFernet([Fernet(k.encode()) for k in keys])


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return ""


class EncryptedTextField(models.TextField):
    """Text stored encrypted at rest; transparent to application code."""

    def from_db_value(self, value, expression, connection):
        if value in (None, ""):
            return value
        return decrypt(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value in (None, ""):
            return value
        return encrypt(value)


class EncryptedJSONField(models.TextField):
    def from_db_value(self, value, expression, connection):
        import json

        if value in (None, ""):
            return None
        plain = decrypt(value)
        return json.loads(plain) if plain else None

    def to_python(self, value):
        return value

    def get_prep_value(self, value):
        import json

        if value is None:
            return None
        return encrypt(json.dumps(value))
