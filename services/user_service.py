from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

from models.database import get_engine
from models.schema import users


def create_user(email, name, password=None, auth_provider="email", auth_provider_id=None):
    password_hash = generate_password_hash(password) if password else None
    try:
        with get_engine().begin() as conn:
            row = conn.execute(
                insert(users)
                .values(
                    email=_normalize_email(email),
                    name=name,
                    password_hash=password_hash,
                    auth_provider=auth_provider,
                    auth_provider_id=auth_provider_id,
                )
                .returning(*users.c)
            ).mappings().one()
    except IntegrityError:
        return None
    return dict(row)


def get_user_by_email(email):
    return _get_one(users.c.email == _normalize_email(email))


def get_user_by_id(user_id):
    return _get_one(users.c.id == user_id)


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


def _get_one(condition):
    with get_engine().connect() as conn:
        row = conn.execute(select(users).where(condition)).mappings().first()
    return dict(row) if row else None


def _normalize_email(email):
    return email.lower().strip()
