"""Dish photos from the internet, and the shared library they build up (module 18).

When a family has no photo of a dish, the app searches free photo libraries for one. Only
licences that allow printing in a book that is sold, and cropping, are offered: CC0, public
domain and CC BY from Openverse, and Pexels photos when PEXELS_API_KEY is set. CC BY-SA (whose
crops would have to carry the same licence), NC and ND are never shown.

A picked photo is stored once in `dish_images` under the dish's name. The next book with the same
dish sees it first ("From other Andaaz books") and gets a copy of the stored file, so popular
dishes stop needing a search. Every use carries the photo's credit line, which the recipe page
prints.
"""
import ipaddress
import json
import logging
import os
import re
import socket
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from sqlalchemy import insert, or_, select, update

import config
from models.database import get_engine
from models.schema import dish_images
from services import photo_service, storage_service

log = logging.getLogger(__name__)

OPENVERSE_LICENSES = {"cc0": "CC0", "pdm": "Public domain", "by": "CC BY"}
PEXELS_LICENSE = "Pexels licence"
PEXELS_LICENSE_URL = "https://www.pexels.com/license/"
MAX_DOWNLOAD_BYTES = 15 * 1024 * 1024
MIN_PRINT_SIDE = 1200  # smaller photos look soft on a printed page
TIMEOUT = 10
CACHE_SECONDS = 3600
_cache = {}


class DishPhotoError(Exception):
    pass


def dish_key(title):
    """"Aloo Paratha (Punjabi style)" -> "aloo paratha punjabi style": how the library files a dish."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (title or "").lower())).strip()


# ─── The shared library ───────────────────────────────────────

def library_matches(title, limit=8):
    """Photos other books picked for this dish, most used first."""
    key = dish_key(title)
    if not key:
        return []
    words = [w for w in key.split() if len(w) > 2][:4]
    condition = or_(dish_images.c.dish_key == key, *[dish_images.c.dish_key.like(f"%{w}%") for w in words])
    with get_engine().connect() as conn:
        rows = conn.execute(select(dish_images).where(condition)
                            .order_by((dish_images.c.dish_key == key).desc(), dish_images.c.use_count.desc(),
                                      dish_images.c.id)
                            .limit(limit)).mappings().all()
    return [dict(r, credit=credit_line(r)) for r in rows]


def get_library_image(image_id):
    with get_engine().connect() as conn:
        row = conn.execute(select(dish_images).where(dish_images.c.id == image_id)).mappings().first()
    return dict(row) if row else None


def use_library_image(image, prefix):
    """A copy of a library photo for one recipe: (photo key, credit line)."""
    with storage_service.local_copy("photos", image["storage_key"]) as path, open(path, "rb") as f:
        key = photo_service.save_photo(f, prefix)
    with get_engine().begin() as conn:
        conn.execute(update(dish_images).where(dish_images.c.id == image["id"])
                     .values(use_count=dish_images.c.use_count + 1))
    return key, credit_line(image)


def add_web_photo(title, source, source_id):
    """Fetch a search result by its id (never a URL from the browser), keep it in the library and
    return the library row. If another book already picked it, that row is returned as it is."""
    with get_engine().connect() as conn:
        row = conn.execute(select(dish_images).where(dish_images.c.source == source,
                                                     dish_images.c.source_id == str(source_id))).mappings().first()
    if row:
        return dict(row)
    info = _lookup(source, source_id)
    data = _download(info["image_url"])
    handle, path = tempfile.mkstemp(suffix=".img")
    os.close(handle)
    try:
        with open(path, "wb") as f:
            f.write(data)
        with open(path, "rb") as f:
            storage_key = photo_service.save_photo(f, "lib")
    except photo_service.PhotoError as exc:
        raise DishPhotoError("That photo couldn't be used. Please pick another.") from exc
    finally:
        os.remove(path)
    values = {k: info.get(k) for k in ("title", "creator", "license", "license_url", "landing_url", "width", "height")}
    with get_engine().begin() as conn:
        image_id = conn.execute(insert(dish_images).values(
            dish_key=dish_key(title), source=source, source_id=str(source_id), storage_key=storage_key, **values,
        )).inserted_primary_key[0]
    return get_library_image(image_id)


def credit_line(image):
    """'Photo: "Rajma chawal" by A. Kumar, CC BY 2.0, via Openverse', as printed under the recipe."""
    source = {"openverse": "Openverse", "pexels": "Pexels"}.get(image.get("source"), image.get("source"))
    title, creator = image.get("title"), image.get("creator")
    if title:
        lead = f"Photo: “{title}” by {creator}" if creator else f"Photo: “{title}”"
    else:
        lead = f"Photo by {creator}" if creator else "Photo"
    return f"{lead}, {image['license']}, via {source}"


# ─── Searching ─────────────────────────────────────────────────

def search_web(query, limit=12):
    """Free-licence photos for a dish, Pexels first when it has a key. Raises DishPhotoError when
    no search could be reached; an empty list means nothing suitable was found."""
    query = " ".join((query or "").split())[:80]
    if not query or not config.PHOTO_SEARCH_ENABLED:
        return []
    cached = _cache.get(query.lower())
    if cached and cached[0] > time.time():
        return cached[1]
    results, failures = [], 0
    searches = ([_search_pexels] if config.PEXELS_API_KEY else []) + [_search_openverse]
    for search in searches:
        try:
            results += search(query, limit)
        except DishPhotoError as exc:
            log.warning("Photo search failed: %s", exc)
            failures += 1
    if failures == len(searches):
        raise DishPhotoError("Couldn't reach the photo search just now. Please try again in a bit.")
    results = results[:limit]
    _cache[query.lower()] = (time.time() + CACHE_SECONDS, results)
    return results


def _search_openverse(query, limit):
    params = {"q": f"{query} food", "license": ",".join(OPENVERSE_LICENSES), "page_size": limit * 2,
              "mature": "false", "size": "large"}
    data = _get_json(f"{config.OPENVERSE_API_URL}/images/?{urllib.parse.urlencode(params)}")
    results = []
    for item in data.get("results") or []:
        info = _openverse_info(item)
        if info and min(info["width"] or 0, info["height"] or 0) >= MIN_PRINT_SIDE * 0.75:
            results.append(info)
    return results[:limit]


def _openverse_info(item):
    license_code = (item.get("license") or "").lower()
    if license_code not in OPENVERSE_LICENSES or not item.get("url") or not item.get("id"):
        return None
    name = OPENVERSE_LICENSES[license_code]
    if license_code == "by" and item.get("license_version"):
        name = f"{name} {item['license_version']}"
    return {"source": "openverse", "source_id": str(item["id"]), "title": (item.get("title") or "")[:120],
            "creator": (item.get("creator") or "")[:80], "license": name, "license_url": item.get("license_url"),
            "landing_url": item.get("foreign_landing_url"), "image_url": item["url"],
            "thumb_url": item.get("thumbnail") or item["url"], "width": item.get("width"),
            "height": item.get("height")}


def _search_pexels(query, limit):
    params = {"query": f"{query} food", "per_page": limit}
    data = _get_json(f"https://api.pexels.com/v1/search?{urllib.parse.urlencode(params)}",
                     {"Authorization": config.PEXELS_API_KEY})
    return [_pexels_info(p) for p in data.get("photos") or []]


def _pexels_info(photo):
    return {"source": "pexels", "source_id": str(photo["id"]), "title": (photo.get("alt") or "")[:120],
            "creator": (photo.get("photographer") or "")[:80], "license": PEXELS_LICENSE,
            "license_url": PEXELS_LICENSE_URL, "landing_url": photo.get("url"),
            "image_url": (photo.get("src") or {}).get("original"), "thumb_url": (photo.get("src") or {}).get("medium"),
            "width": photo.get("width"), "height": photo.get("height")}


def _lookup(source, source_id):
    """A search result's details fetched again from its own service, so its licence is checked here."""
    if source == "openverse" and re.fullmatch(r"[0-9a-f-]{36}", str(source_id)):
        info = _openverse_info(_get_json(f"{config.OPENVERSE_API_URL}/images/{source_id}/"))
    elif source == "pexels" and config.PEXELS_API_KEY and str(source_id).isdigit():
        info = _pexels_info(_get_json(f"https://api.pexels.com/v1/photos/{source_id}",
                                      {"Authorization": config.PEXELS_API_KEY}))
    else:
        info = None
    if not info or not info.get("image_url"):
        raise DishPhotoError("That photo can't be used. Please pick another.")
    return info


# ─── Fetching ──────────────────────────────────────────────────

def _get_json(url, headers=None):
    request = urllib.request.Request(url, headers={"User-Agent": f"{config.APP_NAME}/1.0", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read(2_000_000))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise DishPhotoError(f"{urllib.parse.urlsplit(url).netloc}: {exc}") from exc


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _check_public(url):
    """Refuse anything but http(s) to a public address: image URLs come from other people's sites."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise DishPhotoError("That photo's address can't be used.")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parts.hostname, parts.port or 443)}
    except socket.gaierror as exc:
        raise DishPhotoError("That photo's site couldn't be reached.") from exc
    for address in addresses:
        if not ipaddress.ip_address(address.split("%")[0]).is_global:
            raise DishPhotoError("That photo's address can't be used.")


def _download(url, redirects=4):
    """The image's bytes, following a few redirects, each checked; capped at MAX_DOWNLOAD_BYTES."""
    opener = urllib.request.build_opener(_NoRedirect)
    for _ in range(redirects + 1):
        _check_public(url)
        request = urllib.request.Request(url, headers={"User-Agent": f"{config.APP_NAME}/1.0"})
        try:
            with opener.open(request, timeout=TIMEOUT) as response:
                if not (response.headers.get("Content-Type") or "").startswith("image/"):
                    raise DishPhotoError("That link isn't a photo.")
                data = response.read(MAX_DOWNLOAD_BYTES + 1)
                if len(data) > MAX_DOWNLOAD_BYTES:
                    raise DishPhotoError("That photo is too large.")
                return data
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308) and exc.headers.get("Location"):
                url = urllib.parse.urljoin(url, exc.headers["Location"])
                continue
            raise DishPhotoError(f"The photo's site said {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise DishPhotoError("That photo's site couldn't be reached.") from exc
    raise DishPhotoError("That photo's address went round in circles.")
