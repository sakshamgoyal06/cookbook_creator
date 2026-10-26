"""Render a sample book in every style and size, and the style previews for the R14 screen.

    python scripts/book_samples.py out/            # sample PDFs: <style>-<size>.pdf
    python scripts/book_samples.py --previews      # rewrite static/book/previews/<style>.png

Uses made-up recipes and plain placeholder photos; nothing touches the database. Previews need
pdftoppm (poppler-utils).
"""

import base64
import io
import os
import subprocess
import sys
import tempfile
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("FLASK_SECRET_KEY", "book-samples")

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from weasyprint import HTML  # noqa: E402

import app as flask_app  # noqa: E402
from services import book_design, pdf_service, photo_service  # noqa: E402

PREVIEW_WIDTH = 640


def sample_photo(key, frame=None, crop=None):
    image = PLACEHOLDERS.get(key)
    if image is None:
        return None
    if frame:
        image = image.crop(photo_service.crop_box(image.width, image.height, frame["width"] / frame["height"], crop))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def _placeholder(width, height, top, bottom, label):
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / height
        draw.line([(0, y), (width, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    font = ImageFont.truetype(os.path.join(ROOT, "static", "fonts", "poppins-latin-600-normal.woff"), width // 18)
    box = draw.textbbox((0, 0), label, font=font)
    draw.text(((width - box[2]) / 2, (height - box[3]) / 2), label, font=font, fill=(255, 255, 255))
    return image


PLACEHOLDERS = {
    "cook": _placeholder(800, 1000, (150, 118, 92), (205, 172, 138), "Cook's photo"),
    "family": _placeholder(1400, 1000, (118, 132, 140), (205, 180, 146), "Family photo"),
    "dish": _placeholder(1400, 1000, (168, 82, 40), (226, 160, 88), "Dish photo"),
}


def ing(quantity, unit, item, note=""):
    return {"quantity": quantity, "unit": unit, "item": item, "preparation_note": note}


def step(text, flame="", timing="", cue=""):
    return {"instruction": text, "flame_level": flame, "timing": timing, "sensory_cue": cue}


RECIPES = [
    dict(
        id=1,
        recipe_id="R1",
        recipe_title="Rajma chawal",
        category="Dal",
        photo_key="dish",
        alternate_names=["राजमा चावल"],
        family_note="Rajma raat ko bhigo dena, tabhi ghulta hai. Sunday ko yahi banta tha.",
        serves="4",
        prep_time_minutes=15,
        cook_time_minutes=50,
        difficulty="Easy",
        ingredients=[
            ing("1", "cup", "rajma", "soaked overnight"),
            ing("2", "", "onions", "finely chopped"),
            ing("2", "", "tomatoes", "pureed"),
            ing("1", "tbsp", "ginger-garlic paste"),
            ing("2", "tbsp", "ghee"),
            ing("1", "tsp", "jeera"),
            ing("1", "tsp", "rajma masala"),
            ing("½", "tsp", "haldi"),
            ing("", "", "namak", "andaaze se"),
            ing("", "", "hara dhaniya", "to finish"),
        ],
        method_steps=[
            step(
                "Rajma ko 6–7 seeti tak namak daal ke pressure cooker mein pakaayein.",
                "medium",
                "6–7 whistles",
                "should mash between fingers",
            ),
            step(
                "Kadhai mein ghee garam karke jeera daalein, phir pyaaz sunehra hone tak bhunein.",
                "medium",
                "8–10 min",
                "golden brown",
            ),
            step(
                "Adrak-lehsun aur tamatar daalein; masala tab tak bhunein jab tak ghee alag na ho.",
                "low",
                "10 min",
                "oil separates",
            ),
            step(
                "Rajma paani samet daalein, thoda masal ke gaadha karein aur 15 minute dheemi aanch par pakaayein.",
                "low",
                "15 min",
            ),
            step("Dhaniya daal ke chawal ke saath garam parosein."),
        ],
        moms_tips=["Rajma ka paani mat phenko, wahi asli swaad hai.", "Ek chammach makhan aakhir mein daalo."],
        serving_suggestion="Steamed rice, sliced onion and a squeeze of lemon.",
        storage_notes="Keeps 2 days in the fridge; tastes better the next day.",
        listen_token="sample1",
        audio_clips=[{}],
    ),
    dict(
        id=2,
        recipe_id="R2",
        recipe_title="Aloo paratha",
        category="Breakfast",
        photo_key="dish",
        serves="6 parathas",
        prep_time_minutes=20,
        cook_time_minutes=30,
        ingredients=[
            ing("2", "cups", "atta"),
            ing("4", "", "aloo", "boiled and mashed"),
            ing("1", "", "hari mirch", "chopped"),
            ing("½", "tsp", "ajwain"),
            ing("", "", "ghee", "for roasting"),
        ],
        method_steps=[
            step("Atta naram goondh ke 20 minute dhak ke rakhein."),
            step("Aloo mein masale milaayein."),
            step("Loi mein bharawan bhar ke dheere se belein.", cue="should not tear"),
            step("Tawe par dono taraf ghee laga ke sekein.", "medium", cue="golden spots"),
        ],
        moms_tips=["Aloo thande hon tabhi bharo, garam aloo se paratha phat-ta hai."],
        listen_token="sample2",
        audio_clips=[{}],
    ),
    dict(
        id=3,
        recipe_id="R3",
        recipe_title="Gajar ka halwa",
        category="Sweets",
        photo_key="dish",
        family_note="Sardiyon mein pehli gajar aate hi ye banta tha.",
        serves="6",
        cook_time_minutes=75,
        difficulty="Medium",
        ingredients=[
            ing("1", "kg", "gajar", "grated"),
            ing("1", "litre", "full-cream milk"),
            ing("¾", "cup", "sugar"),
            ing("3", "tbsp", "ghee"),
            ing("8–10", "", "kaju-badaam", "sliced"),
            ing("4", "", "elaichi", "crushed"),
        ],
        method_steps=[
            step(
                "Gajar aur doodh ko bhaari kadhai mein pakaayein jab tak doodh sookh na jaaye, beech beech mein "
                "chalaate rahein.",
                "medium",
                "45–50 min",
                "milk fully absorbed",
            ),
            step("Cheeni daalein; ye phir se geela hoga, use sookhne dein.", "medium", "10 min"),
            step(
                "Ghee daal ke bhunein jab tak halwa kinaare chhodne lage.",
                "low",
                "10 min",
                "glossy, leaves the sides",
            ),
            step("Elaichi aur meve daal ke garam parosein."),
        ],
        moms_tips=["Laal Dilli wali gajar hi lena.", "Khoya ho to aakhir mein 100 g mila do."],
        serving_suggestion="Warm, with a scoop of vanilla ice cream for the kids.",
        listen_token="sample3",
        audio_clips=[{}],
    ),
    dict(
        id=4,
        recipe_id="R4",
        recipe_title="Kadhi pakora",
        category="Dal",
        serves="4",
        cook_time_minutes=40,
        ingredients=[
            ing("1", "cup", "khatta dahi"),
            ing("3", "tbsp", "besan"),
            ing("1", "cup", "besan", "for pakoras"),
            ing("1", "", "pyaaz", "sliced"),
            ing("1", "tsp", "methi dana"),
            ing("2", "", "sookhi laal mirch"),
        ],
        method_steps=[
            step("Dahi aur besan ko 4 cup paani ke saath phent lein."),
            step("Pakore talein.", "medium"),
            step(
                "Kadhi ko ubaal aane tak lagaatar chalaayein, phir dheemi aanch par 25 minute pakaayein.",
                "low",
                "25 min",
                "coats the spoon",
            ),
            step("Pakore daalein aur methi-mirch ka tadka lagaayein."),
        ],
        listen_token="sample4",
        audio_clips=[{}],
    ),
]


def sample_project(style, size, layout="photo", photos=True):
    return dict(
        id=0,
        title="Mummy ki Rasoi",
        subtitle="Forty years of Sunday lunches",
        theme=style,
        book_size=size,
        book_accent=None,
        cover_layout=layout,
        cook_photo_key="cook" if photos else None,
        family_photo_key="family" if photos else None,
        storyteller_name="Sunita Sharma",
        storyteller_address_as="Mummy",
        cook_mode="whatsapp",
        occasion="Diwali",
        reveal_date=date(2026, 11, 8),
        dedication="For Mummy, who never measured anything and never got it wrong.",
        about_author="Sunita Sharma learnt to cook in her mother's kitchen in Meerut, standing on a steel stool.\n"
        "Forty years later her rajma is still the reason everyone comes home on Sundays.",
        introduction="Diwali 2025, the whole family at Nani's house.",
        acknowledgement="We made this book so the recipes, and her voice, stay with us. Thank you, Mummy.\n"
        "With love, Rohan, Priya and the kids",
        book_token="sample",
    )


def render(project, recipes, path, print_ready=False):
    html = pdf_service.render_book_html(project, recipes, print_ready)
    HTML(string=html, base_url=ROOT).write_pdf(path, stylesheets=book_design.stylesheets(project))


def previews():
    """Each style's title cover beside a recipe page, as the R14 style picker shows them."""
    folder = os.path.join(ROOT, "static", "book", "previews")
    os.makedirs(folder, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for style in book_design.STYLES:
            pdf = os.path.join(tmp, f"{style}.pdf")
            recipe = dict(RECIPES[1], photo_key=None)
            render(sample_project(style, "a4", layout="title", photos=False), [recipe], pdf)
            # Page 1 is the cover; the recipe follows the dedication, About and contents pages.
            pages = []
            for number in (1, 5):
                prefix = os.path.join(tmp, f"{style}-{number}")
                subprocess.run(
                    [
                        "pdftoppm",
                        "-r",
                        "60",
                        "-png",
                        "-singlefile",
                        "-f",
                        str(number),
                        "-l",
                        str(number),
                        pdf,
                        prefix,
                    ],
                    check=True,
                )
                pages.append(Image.open(prefix + ".png").convert("RGB"))
            gap = 12
            width = pages[0].width * 2 + gap * 3
            sheet = Image.new("RGB", (width, pages[0].height + gap * 2), (226, 222, 214))
            for i, page in enumerate(pages):
                sheet.paste(page, (gap + i * (page.width + gap), gap))
            sheet = sheet.resize((PREVIEW_WIDTH, round(sheet.height * PREVIEW_WIDTH / sheet.width)), Image.LANCZOS)
            sheet.save(os.path.join(folder, f"{style}.png"), optimize=True)
            print(os.path.join(folder, f"{style}.png"), sheet.size)


def main():
    # Placeholder photos instead of storage, cut to each spot as the real ones are.
    photo_service.data_uri = sample_photo
    with flask_app.app.test_request_context():
        if sys.argv[1:] == ["--previews"]:
            previews()
            return
        out = sys.argv[1] if len(sys.argv) > 1 else "book-samples"
        os.makedirs(out, exist_ok=True)
        for style in book_design.STYLES:
            for size in book_design.SIZES:
                path = os.path.join(out, f"{style}-{size}.pdf")
                render(sample_project(style, size), RECIPES, path)
                print(path)


if __name__ == "__main__":
    main()
