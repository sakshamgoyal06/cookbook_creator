import os
import uuid

import config

MIME_TO_EXTENSION = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/m4a": ".m4a",
    "audio/wav": ".wav",
    "audio/wave": ".wav",
    "audio/x-wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/aac": ".aac",
    "audio/x-caf": ".caf",
    "audio/caf": ".caf",
    "video/mp4": ".mp4",
}

ALLOWED_AUDIO_MIMETYPES = set(MIME_TO_EXTENSION.keys())

SUPPORTED_FORMATS_LABEL = ".mp3, .m4a, .mp4, .wav, or .ogg"


def _normalize_mimetype(mimetype):
    if not mimetype:
        return ""
    return mimetype.split(";", 1)[0].strip().lower()


def extension_for_upload(filename, mimetype=None):
    ext = os.path.splitext(filename or "")[1].lower()
    if ext in config.ALLOWED_AUDIO_EXTENSIONS:
        return ext

    normalized_mimetype = _normalize_mimetype(mimetype)
    if normalized_mimetype in MIME_TO_EXTENSION:
        return MIME_TO_EXTENSION[normalized_mimetype]

    return ""


def is_allowed_audio(filename, mimetype=None):
    if extension_for_upload(filename, mimetype):
        return True
    return _normalize_mimetype(mimetype) in ALLOWED_AUDIO_MIMETYPES


def build_storage_filename(original_filename, mimetype=None):
    ext = extension_for_upload(original_filename, mimetype)
    if not ext:
        ext = ".m4a"
    return f"{uuid.uuid4().hex}{ext}"
