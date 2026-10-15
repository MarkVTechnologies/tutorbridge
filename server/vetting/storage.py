"""
Secure private file storage (section 15.1 Uploads): type and size checks,
image re-encoding (strips EXIF/GPS and any embedded payload), randomised
names, stored outside public_html.
"""
import hashlib
import io
import uuid
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from PIL import Image
from rest_framework.exceptions import ValidationError

from vetting.models import Document

ALLOWED = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}
MAGIC = {b"%PDF": "application/pdf", b"\xff\xd8\xff": "image/jpeg", b"\x89PNG": "image/png"}


def _sniff(head: bytes):
    for magic, ctype in MAGIC.items():
        if head.startswith(magic):
            return ctype
    return None


def save_upload(uploaded, owner, doc_type) -> Document:
    if uploaded.size > settings.MAX_UPLOAD_BYTES:
        raise ValidationError({"file": "Files must be 5 MB or smaller."})
    data = uploaded.read()
    content_type = _sniff(data[:8])
    if content_type not in ALLOWED:
        raise ValidationError({"file": "Only PDF, JPG and PNG files are accepted."})

    if content_type.startswith("image/"):
        try:
            img = Image.open(io.BytesIO(data))
            img.verify()
            img = Image.open(io.BytesIO(data))
            img = img.convert("RGB") if content_type == "image/jpeg" else img
            img.thumbnail((2400, 2400))
            out = io.BytesIO()
            img.save(out, format="JPEG" if content_type == "image/jpeg" else "PNG", optimize=True)
            data = out.getvalue()
        except Exception as e:  # noqa: BLE001
            raise ValidationError({"file": "This image could not be read."}) from e

    now = timezone.now()
    rel = Path(f"{now:%Y/%m}") / f"{uuid.uuid4().hex}{ALLOWED[content_type]}"
    dest = Path(settings.PRIVATE_MEDIA_ROOT) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return Document.objects.create(
        owner=owner,
        doc_type=doc_type,
        storage_path=rel.as_posix(),
        original_name=Path(uploaded.name).name[:255],
        content_type=content_type,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


def absolute_path(doc: Document) -> Path:
    root = Path(settings.PRIVATE_MEDIA_ROOT).resolve()
    path = (root / doc.storage_path).resolve()
    if root not in path.parents:
        raise PermissionError("Invalid storage path")
    return path


def delete_file(doc: Document):
    try:
        absolute_path(doc).unlink(missing_ok=True)
    except PermissionError:
        pass
