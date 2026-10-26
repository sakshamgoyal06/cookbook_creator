import io

import pytest
from PIL import Image

from services import dish_photo_service, pdf_service, photo_service, recipe_service
from test_book import _approved_recipes

OPENVERSE_ID = "4bc43a04-ef46-4544-a0c1-63c63f56e276"


def _item(id_=OPENVERSE_ID, license="by", **extra):
    return dict(id=id_, title="Rajma chawal", creator="A. Kumar", license=license, license_version="2.0",
                license_url="https://creativecommons.org/licenses/by/2.0/", url="https://images.example.org/rajma.jpg",
                thumbnail=f"https://api.openverse.org/v1/images/{id_}/thumb/",
                foreign_landing_url="https://www.flickr.com/photos/x/1", width=3000, height=2000, **extra)


def _jpeg():
    buffer = io.BytesIO()
    Image.new("RGB", (3000, 2000), (160, 60, 30)).save(buffer, "JPEG")
    return buffer.getvalue()


@pytest.fixture
def web(monkeypatch):
    calls = []
    dish_photo_service._cache.clear()

    def get_json(url, headers=None):
        calls.append(url)
        if "/images/?" in url:
            return {"results": [_item(), _item("bad-1", license="by-sa"), _item("bad-2", license="by-nc"),
                                dict(_item("5bc43a04-ef46-4544-a0c1-63c63f56e276"), width=400, height=300)]}
        return _item()
    monkeypatch.setattr(dish_photo_service, "_get_json", get_json)
    monkeypatch.setattr(dish_photo_service, "_download", lambda url: calls.append(url) or _jpeg())
    return calls


def test_only_photos_free_to_print_and_crop_are_offered(web):
    results = dish_photo_service.search_web("Rajma")
    assert [r["source_id"] for r in results] == [OPENVERSE_ID]  # no BY-SA, no NC, nothing too small to print
    assert results[0]["license"] == "CC BY 2.0"
    assert "license=cc0%2Cpdm%2Cby" in web[0]
    dish_photo_service.search_web("rajma")
    assert len(web) == 1  # the same search again comes from the cache


def test_picking_a_web_photo_credits_it_and_shares_it_with_the_next_book(app, auth_client, monkeypatch, web):
    pid, (rid, other) = _approved_recipes(auth_client, monkeypatch)
    recipe_service.save_structured_recipe(rid, dict(recipe_service.get_recipe(rid), recipe_title="Rajma Chawal"))
    page = auth_client.get(f"/p/{pid}/r/{rid}/photo/find").data.decode()
    assert "Free photos from the internet" in page and "A. Kumar · CC BY 2.0" in page

    response = auth_client.post(f"/p/{pid}/r/{rid}/photo/find", data={"pick": f"web-openverse-{OPENVERSE_ID}"})
    assert f"/p/{pid}/photos/r{rid}/fit" in response.headers["Location"]
    recipe = recipe_service.get_recipe(rid)
    assert recipe["photo_key"].startswith(f"p{pid}-r{rid}-")
    assert recipe["photo_credit"] == "Photo: “Rajma chawal” by A. Kumar, CC BY 2.0, via Openverse"
    assert web[-2].endswith(f"/images/{OPENVERSE_ID}/")  # details fetched again by id, not taken from the browser

    with app.test_request_context():
        html = pdf_service.render_book_html(pdf_service.project_service.get_project(pid), [recipe])
    assert "Photo: “Rajma chawal” by A. Kumar" in html

    # Another dish of the same name finds it in the library, with no search.
    recipe_service.save_structured_recipe(other, dict(recipe_service.get_recipe(other), recipe_title="Rajma"))
    searches = len(web)
    page = auth_client.get(f"/p/{pid}/r/{other}/photo/find").data.decode()
    assert "From other Andaaz books" in page and len(web) == searches
    image = dish_photo_service.library_matches("Rajma")[0]
    auth_client.post(f"/p/{pid}/r/{other}/photo/find", data={"pick": f"lib-{image['id']}"})
    copy = recipe_service.get_recipe(other)
    assert copy["photo_key"] != recipe["photo_key"] and copy["photo_image_id"] == image["id"]
    assert dish_photo_service.get_library_image(image["id"])["use_count"] == 2
    assert auth_client.get(f"/photos/library/{image['id']}.jpg").status_code == 200

    # The family's own photo replaces it, credit and all.
    from test_book_design import _upload
    _upload(auth_client, f"/p/{pid}/r/{other}/photo")
    assert recipe_service.get_recipe(other)["photo_credit"] is None


def test_a_search_that_cant_be_reached_still_shows_the_page(auth_client, monkeypatch):
    pid, (rid, _) = _approved_recipes(auth_client, monkeypatch)
    dish_photo_service._cache.clear()

    def down(url, headers=None):
        raise dish_photo_service.DishPhotoError("offline")
    monkeypatch.setattr(dish_photo_service, "_get_json", down)
    page = auth_client.get(f"/p/{pid}/r/{rid}/photo/find?q=kheer").data.decode()
    assert "Couldn&#39;t reach the photo search" in page
    bad = auth_client.post(f"/p/{pid}/r/{rid}/photo/find", data={"pick": "web-openverse-not-an-id"})
    assert bad.status_code == 302 and recipe_service.get_recipe(rid)["photo_key"] is None
    assert auth_client.post(f"/p/{pid}/r/{rid}/photo/find", data={"pick": "file:///etc"}).status_code == 400


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://127.0.0.1/a.jpg", "http://10.0.0.5/a.jpg",
                                 "http://169.254.169.254/latest/meta-data", "http://[::1]/a.jpg"])
def test_photo_downloads_refuse_private_addresses(url):
    with pytest.raises(dish_photo_service.DishPhotoError):
        dish_photo_service._check_public(url)


def test_dish_key_and_credit_line():
    assert dish_photo_service.dish_key("  Aloo Paratha (Punjabi-style)!") == "aloo paratha punjabi style"
    assert dish_photo_service.credit_line({"source": "pexels", "creator": "R. Shah", "license": "Pexels licence"}) \
        == "Photo by R. Shah, Pexels licence, via Pexels"
    assert photo_service.thumbnail  # used by the picker grid
