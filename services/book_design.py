"""Book styles, sizes and cover layouts (module 18).

A style is a stylesheet in static/book/ plus the fonts and colours below; the page structure in
templates/pdf/ is shared, so every style gets the same cover, opening pages, contents, sections,
recipe pages and closing pages. `projects.theme` holds the style key.
"""
import os

import config

STYLES = {
    "classic": {
        "name": "Heirloom",
        "blurb": "Cream paper, fine serif type and gold rules. Quiet and elegant, like a book kept for years.",
        "accents": {"Forest": "#2F4A3A", "Maroon": "#6E2232", "Ink blue": "#24395C"},
    },
    "rustic": {
        "name": "Rasoi diary",
        "blurb": "Kraft paper, handwritten headings and taped-in photos. Warm, like a kitchen notebook.",
        "accents": {"Rust": "#A3492B", "Olive": "#5E6B32", "Brown": "#6B4428"},
    },
    "modern": {
        "name": "Modern kitchen",
        "blurb": "White pages, bold type and big photos. Clean and bright, like a new cookbook from a shop.",
        "accents": {"Terracotta": "#D0553A", "Teal": "#1F7A74", "Charcoal": "#2B2B2B"},
    },
    "festive": {
        "name": "Utsav",
        "blurb": "Rich maroon and marigold with patterned borders. Made for Diwali, weddings and big days.",
        "accents": {"Maroon": "#7A1E2C", "Peacock": "#0E5A66", "Mehendi": "#4E6A2A"},
    },
}
# Older projects were made with the earlier theme names.
LEGACY_STYLES = {"elegant": "classic", "fresh": "modern"}

# Width and height in mm. "wide" is the landscape hardcover most Indian photobook printers offer.
SIZES = {
    "a4": {"name": "A4 portrait", "detail": "21 × 29.7 cm. Prints at home or any print shop; soft or hard cover.",
           "width": 210, "height": 297},
    "wide": {"name": "Wide hardcover", "detail": "29.7 × 21 cm landscape. The coffee-table size for a hardcover gift.",
             "width": 297, "height": 210},
}

COVER_LAYOUTS = {
    "photo": "With the cook's photo",
    "title": "Title only",
}

BLEED_MM = 3


def style_key(project):
    key = (project or {}).get("theme") or "classic"
    key = LEGACY_STYLES.get(key, key)
    return key if key in STYLES else "classic"


def size_key(project):
    key = (project or {}).get("book_size") or "a4"
    return key if key in SIZES else "a4"


def accent(project):
    """The chosen accent colour, or the style's first one."""
    style = STYLES[style_key(project)]
    chosen = (project or {}).get("book_accent")
    return chosen if chosen in style["accents"].values() else next(iter(style["accents"].values()))


def cover_layout(project):
    key = (project or {}).get("cover_layout") or "photo"
    return key if key in COVER_LAYOUTS else "photo"


def stylesheets(project):
    """Local paths of the shared stylesheet and the style's own, in cascade order."""
    folder = os.path.join(config.BASE_DIR, "static", "book")
    return [os.path.join(folder, "base.css"), os.path.join(folder, f"{style_key(project)}.css")]


def page_css(project, print_ready=False):
    """The @page size and the accent, which change per book and so can't live in the static sheets."""
    size = SIZES[size_key(project)]
    marks = f"bleed: {BLEED_MM}mm; marks: crop;" if print_ready else ""
    return (f"@page {{ size: {size['width']}mm {size['height']}mm; {marks} }}\n"
            f":root {{ --accent: {accent(project)}; }}")


def body_classes(project):
    return f"style-{style_key(project)} size-{size_key(project)}"


def validate(form, project):
    """The design fields from the R14 form, with anything unknown dropped."""
    values = {}
    if form.get("theme") in STYLES:
        values["theme"] = form["theme"]
    if form.get("book_size") in SIZES:
        values["book_size"] = form["book_size"]
    if form.get("cover_layout") in COVER_LAYOUTS:
        values["cover_layout"] = form["cover_layout"]
    style = STYLES[values.get("theme") or style_key(project)]
    if form.get("book_accent") in style["accents"].values():
        values["book_accent"] = form["book_accent"]
    elif "theme" in values:
        values["book_accent"] = None
    return values


# ─── Photo frames ──────────────────────────────────────────────
# The size in mm of each photo's spot in the book, per style and size, so a photo can be cropped
# to fit it exactly (see photo_service.crop_box). They follow static/book/*.css; tests measure the
# laid-out book and fail if the two drift apart.
#   cover: the cook's photo on the cover; about: the cook's photo on the About page;
#   family: the family photo page; dish: the photo band at the top of an A4 recipe page;
#   dish_page: a dish photo on a page of its own (always in the wide book; long recipes on A4).
PHOTO_FRAMES = {
    "classic": {
        "a4": {"cover": (92, 118), "about": (64, 80), "family": (178, 205),
               "dish": (170, 60), "dish_page": (174, 261)},
        "wide": {"cover": (104, 138), "about": (64, 80), "family": (265, 140), "dish_page": (261, 174)},
    },
    "rustic": {
        "a4": {"cover": (142, 127), "about": (64, 77), "family": (162, 192),
               "dish": (162, 55), "dish_page": (158, 248)},
        "wide": {"cover": (120, 137), "about": (64, 77), "family": (249, 127), "dish_page": (245, 161)},
    },
    "modern": {
        "a4": {"cover": (210, 190), "about": (80, 100), "family": (174, 230),
               "dish": (210, 96), "dish_page": (210, 297)},
        "wide": {"cover": (168, 210), "about": (80, 100), "family": (261, 140), "dish_page": (297, 210)},
    },
    "festive": {
        "a4": {"cover": (108, 108), "about": (70, 70), "family": (167, 190),
               "dish": (167, 68), "dish_page": (165, 265)},
        "wide": {"cover": (108, 108), "about": (70, 70), "family": (254, 120), "dish_page": (252, 178)},
    },
}
# Spots that aren't plain rectangles; the photo editor shows the same shape.
PHOTO_SHAPES = {("classic", "cover"): "oval", ("classic", "about"): "oval",
                ("festive", "cover"): "round", ("festive", "about"): "round"}
PHOTO_PLACE_NAMES = {"cover": "Cover", "about": "About the cook page", "family": "Family photo page",
                     "dish": "Top of the recipe page", "dish_page": "A full page beside the recipe"}


def photo_frame(project, place):
    """{"place", "name", "width", "height", "shape"} for a photo's spot in this book's style and size."""
    style, size = style_key(project), size_key(project)
    frames = PHOTO_FRAMES[style][size]
    if place == "dish" and place not in frames:
        place = "dish_page"  # the wide book always gives the dish a page of its own
    width, height = frames[place]
    return {"place": place, "name": PHOTO_PLACE_NAMES[place], "width": width, "height": height,
            "shape": PHOTO_SHAPES.get((style, place), "rect")}
