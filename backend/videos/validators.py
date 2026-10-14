"""Upload validation (docs/spec.md S4.2). Checks stop at the first failure."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from rest_framework.exceptions import ValidationError

from media_tools.ffmpeg import InvalidVideo, VideoMeta, probe

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".webm"}
ALLOWED_CONTENT_TYPES = {"video/mp4", "video/quicktime", "video/webm"}
# Sent by curl and some clients when they do not know the type; ffprobe decides then.
GENERIC_CONTENT_TYPE = "application/octet-stream"


@dataclass(frozen=True)
class ValidatedUpload:
    extension: str
    meta: VideoMeta
    sha256: str


def _sha256(uploaded: UploadedFile) -> str:
    digest = hashlib.sha256()
    for chunk in uploaded.chunks():
        digest.update(chunk)
    uploaded.seek(0)
    return digest.hexdigest()


def validate_upload(uploaded: UploadedFile) -> ValidatedUpload:
    extension = Path(uploaded.name or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValidationError("Unsupported file type. Allowed: mp4, mov, webm.")

    content_type = (uploaded.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES | {GENERIC_CONTENT_TYPE}:
        raise ValidationError("Unsupported file type. Allowed: mp4, mov, webm.")

    if uploaded.size > settings.MAX_UPLOAD_BYTES:
        max_mb = settings.MAX_UPLOAD_BYTES / (1024 * 1024)
        raise ValidationError(f"File is too large. Maximum size is {max_mb:g} MB.")

    # TemporaryFileUploadHandler (settings) guarantees the upload is on disk.
    try:
        meta = probe(uploaded.temporary_file_path())
    except InvalidVideo as exc:
        raise ValidationError(str(exc)) from exc

    if meta.duration_s > settings.MAX_VIDEO_SECONDS:
        raise ValidationError(
            f"Video is too long ({meta.duration_s:.0f} s). "
            f"Maximum is {settings.MAX_VIDEO_SECONDS} s."
        )

    return ValidatedUpload(extension=extension, meta=meta, sha256=_sha256(uploaded))
