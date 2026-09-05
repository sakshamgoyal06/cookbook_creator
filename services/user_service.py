from werkzeug.security import generate_password_hash, check_password_hash
from models.database import get_connection


def create_user(email, name, password=None, auth_provider="email", auth_provider_id=None):
    conn = get_connection()
    password_hash = generate_password_hash(password) if password else None
    try:
        conn.execute(
            """INSERT INTO users (email, name, password_hash, auth_provider, auth_provider_id)
               VALUES (?, ?, ?, ?, ?)""",
            (email.lower().strip(), name, password_hash, auth_provider, auth_provider_id),
        )
        conn.commit()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
        ).fetchone()
        conn.close()
        return dict(user)
    except Exception:
        conn.close()
        return None


def get_user_by_email(email):
    conn = get_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
    ).fetchone()
    conn.close()
    return dict(user) if user else None


def get_user_by_id(user_id):
    conn = get_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(user) if user else None


def verify_password(user, password):
    if not user or not user.get("password_hash"):
        return False
    return check_password_hash(user["password_hash"], password)


def get_or_create_oauth_user(email, name, provider, provider_id):
    user = get_user_by_email(email)
    if user:
        return user
    return create_user(
        email=email,
        name=name,
        auth_provider=provider,
        auth_provider_id=provider_id,
    )
