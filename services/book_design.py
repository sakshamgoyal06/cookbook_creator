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
