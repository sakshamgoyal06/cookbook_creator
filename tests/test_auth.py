from conftest import register


def test_register_logs_in_and_redirects_to_dashboard(client):
    response = register(client)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")
    # A new account has no book yet, so the app opens onboarding.
    assert client.get("/dashboard").headers["Location"].endswith("/home")
    assert client.get("/home").headers["Location"].endswith("/start")
    assert client.get("/start").status_code == 200


def test_register_rejects_mismatched_passwords(client):
    response = client.post(
        "/register",
        data={"email": "a@x.com", "name": "A", "password": "secret123", "confirm_password": "other123"},
        follow_redirects=True,
    )
    assert b"Passwords do not match" in response.data


def test_register_rejects_duplicate_email(client):
    register(client)
    client.get("/logout")
    response = register(client)
    assert response.headers["Location"].endswith("/register")


def test_login_with_wrong_password_fails(client):
    register(client)
    client.get("/logout")
    response = client.post("/login", data={"email": "mom@example.com", "password": "wrong"}, follow_redirects=True)
    assert b"Invalid email or password" in response.data


def test_login_and_logout(client):
    register(client)
    client.get("/logout")
    response = client.post("/login", data={"email": "MOM@example.com ", "password": "secret123"})
    assert response.headers["Location"].endswith("/dashboard")
    client.get("/logout")
    assert client.get("/dashboard").status_code == 302


def test_dashboard_requires_login(client):
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_healthz_needs_no_login(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "storage": "local"}
