"""Photos for the book (module 18): the cook, the family, and each dish.

Uploads are turned upright, stripped of metadata, shrunk to print size (300 dpi across an A4 page
is about 2,500 px) and saved as JPEG in the "photos" namespace. The PDF embeds them as data URIs,
so they work the same with local storage and with R2.

The original is kept whole. How it sits in its spot in the book is a crop, {"x", "y", "zoom"}: the
point of the photo to centre on (0 to 1 across and down) and how far to zoom in past the largest
crop that fits. The same crop serves every spot the photo appears in (the cook's photo is on the
cover and the About page), each cut to its own shape when the book is made.
"""
import base64
import io
import os
import tempfile
import uuid

from PIL import Image, ImageOps, UnidentifiedImageError

from services import storage_service

MAX_SIDE = 2500
QUALITY = 86
MAX_PIXELS = 60_000_000  # refuse decompression bombs well before Pillow's own limit
MAX_ZOOM = 4
PRINT_DPI = 300
DEFAULT_CROP = {"x": 0.5, "y": 0.5, "zoom": 1.0}


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


def clean_crop(crop):
    """A crop with every value present and in range; anything missing or broken is the centre."""
    crop = crop if isinstance(crop, dict) else {}
    values = {}
    for name, low, high in (("x", 0.0, 1.0), ("y", 0.0, 1.0), ("zoom", 1.0, MAX_ZOOM)):
        try:
            value = float(crop.get(name, DEFAULT_CROP[name]))
        except (TypeError, ValueError):
            value = DEFAULT_CROP[name]
        values[name] = round(min(max(value, low), high), 4) if value == value else DEFAULT_CROP[name]
    return values


def crop_box(width, height, aspect, crop=None):
    """(left, top, right, bottom) of the part of a width x height photo that fills a spot of this
    aspect (width / height). app.js (data-photo-fit) works the same out for the editor's preview."""
    crop = clean_crop(crop)
    if width / height > aspect:
        box_w, box_h = height * aspect, height
    else:
        box_w, box_h = width, width / aspect
    box_w, box_h = box_w / crop["zoom"], box_h / crop["zoom"]
    left = min(max(crop["x"] * width - box_w / 2, 0), width - box_w)
    top = min(max(crop["y"] * height - box_h / 2, 0), height - box_h)
    return round(left), round(top), round(left + box_w), round(top + box_h)


def data_uri(key, frame=None, crop=None):
    """The photo as a data URI for the PDF, or None when there's no photo or it has gone missing.

    With a frame (book_design.photo_frame) it is cut to the frame's shape and sized for printing it.
    """
    if not key:
        return None
    try:
        with storage_service.local_copy("photos", key) as path:
            if frame:
                return _fitted(path, frame, crop)
            with open(path, "rb") as f:
                return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("ascii")
    except Exception:  # missing locally, or s3's own error for a missing key: print without the photo
        return None


def thumbnail(key, side=480):
    """JPEG bytes of a small copy, for picking from a grid."""
    with storage_service.local_copy("photos", key) as path, Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((side, side), Image.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=80)
    return buffer.getvalue()


def _fitted(path, frame, crop):
    with Image.open(path) as image:
        image = image.convert("RGB")
        image = image.crop(crop_box(image.width, image.height, frame["width"] / frame["height"], crop))
        longest = round(max(frame["width"], frame["height"]) / 25.4 * PRINT_DPI)
        image.thumbnail((longest, longest), Image.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=QUALITY, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
