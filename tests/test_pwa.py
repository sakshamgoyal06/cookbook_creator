import json


def test_manifest_is_valid_and_icons_exist(client):
    response = client.get("/static/manifest.webmanifest")
    assert response.status_code == 200
    manifest = json.loads(response.data)
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/dashboard"
    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert {"192x192", "512x512"} <= sizes
    assert any(icon.get("purpose") == "maskable" for icon in manifest["icons"])
    for icon in manifest["icons"]:
        assert client.get(icon["src"]).status_code == 200


def test_service_worker_served_from_root_without_login(client):
    response = client.get("/sw.js")
    assert response.status_code == 200
    assert response.mimetype == "application/javascript"
    assert response.headers["Cache-Control"] == "no-cache"
    assert b"/offline" in response.data


def test_offline_page_needs_no_login(client):
    response = client.get("/offline")
    assert response.status_code == 200
    assert b"offline" in response.data


def test_pages_link_manifest_and_register_worker(client):
    html = client.get("/login").data
    assert b'rel="manifest"' in html
    assert b"apple-touch-icon" in html
    assert b'serviceWorker.register("/sw.js"' in html
