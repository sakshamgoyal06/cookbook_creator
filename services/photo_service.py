"""Photos for the book (module 18): the cook, the family, and each dish.

Uploads are turned upright, stripped of metadata, shrunk to print size (300 dpi across an A4 page
is about 2,500 px) and saved as JPEG in the "photos" namespace. The PDF embeds them as data URIs,
so they work the same with local storage and with R2.
"""
import base64
import os
import tempfile
import uuid

from PIL import Image, ImageOps, UnidentifiedImageError

from services import storage_service

MAX_SIDE = 2500
QUALITY = 86
MAX_PIXELS = 60_000_000  # refuse decompression bombs well before Pillow's own limit


class PhotoError(ValueError):
    pass


def save_photo(stream, prefix):
    """Save an uploaded image and return its storage key; PhotoError if it isn't a usable image."""
    try:
        image = Image.open(stream)
        if image.width * image.height > MAX_PIXELS:
            raise PhotoError("That photo is too large. Please pick a smaller one.")
        image = ImageOps.exif_transpose(image)
        image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise PhotoError("That file isn't a photo we can read. Please pick a JPG or PNG.") from exc
    if image.mode != "RGB":
        background = Image.new("RGB", image.size, (255, 255, 255))
        rgba = image.convert("RGBA")
        background.paste(rgba, mask=rgba.split()[-1])
        image = background
    image.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)

    key = f"{prefix}-{uuid.uuid4().hex[:16]}.jpg"
    handle, path = tempfile.mkstemp(suffix=".jpg")
    os.close(handle)
    try:
        image.save(path, "JPEG", quality=QUALITY, optimize=True, progressive=True)
        storage_service.save_file("photos", key, path, content_type="image/jpeg")
    finally:
        os.remove(path)
    return key


def delete_photo(key):
    if key:
        storage_service.delete("photos", key)


def data_uri(key):
    """The photo as a data URI for the PDF, or None when there's no photo or it has gone missing."""
    if not key:
        return None
    try:
        with storage_service.local_copy("photos", key) as path:
            with open(path, "rb") as f:
                return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("ascii")
    except Exception:  # missing locally, or s3's own error for a missing key: print without the photo
        return None
