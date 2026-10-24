import pytest

from services.audio_utils import build_storage_filename, extension_for_upload, is_allowed_audio


@pytest.mark.parametrize("filename", ["a.mp3", "a.M4A", "a.mp4", "a.wav", "a.ogg"])
def test_allowed_extensions(filename):
    assert is_allowed_audio(filename)


def test_extensionless_ios_voice_memo_uses_mimetype():
    assert extension_for_upload("Voice Memo", "audio/x-m4a") == ".m4a"
    assert is_allowed_audio("Voice Memo", "audio/x-m4a; codecs=aac")


def test_rejects_non_audio():
    assert not is_allowed_audio("notes.txt", "text/plain")
    assert not is_allowed_audio("", None)


def test_storage_filename_is_random_and_keeps_extension():
    first = build_storage_filename("../../etc/passwd.mp3")
    second = build_storage_filename("../../etc/passwd.mp3")
    assert first.endswith(".mp3") and "/" not in first
    assert first != second


def test_storage_filename_defaults_to_m4a():
    assert build_storage_filename("recording", None).endswith(".m4a")
