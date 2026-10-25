"""Payments with Razorpay Checkout (BUILD_PLAN module 13, PRD BUY-2).

Flow: the pay step asks us for an order, Razorpay Checkout takes the payment (UPI first),
and the browser hands back a signed payment id. The signed webhook does the same job
for a buyer whose browser closed before that, so either one can unlock the book, and
doing it twice changes nothing.
"""
import base64
import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError

import config
from models.database import get_engine
from models.schema import orders, projects
from services import events_service

log = logging.getLogger(__name__)
REUSE_ORDER_FOR = timedelta(hours=12)  # a Razorpay order can only be paid once, so reusing it can't double-charge


class PaymentError(RuntimeError):
    pass


def enabled():
    return not config.PILOT_FREE and bool(config.RAZORPAY_KEY_ID and config.RAZORPAY_KEY_SECRET)


def is_unlocked(project):
    return project.get("payment_status") in ("pilot", "paid")


def mark_pilot(project_id):
    with get_engine().begin() as conn:
        conn.execute(update(projects).where(projects.c.id == project_id, projects.c.payment_status == "unpaid")
                     .values(payment_status="pilot"))


def price_paise(project):
    tier = config.TIERS.get(project.get("tier")) or {}
    if not tier.get("available") or not tier.get("price_inr"):
        raise PaymentError("This book isn't on sale yet.")
    return int(tier["price_inr"]) * 100


def create_order(project, user_id):
    """The open order for this book, made at Razorpay if there isn't a recent one. Returns the row."""
    amount = price_paise(project)
    open_order = latest_order(project["id"])
    if (open_order and open_order["status"] == "created" and open_order["amount_paise"] == amount
            and _aware(open_order["created_at"]) > datetime.now(timezone.utc) - REUSE_ORDER_FOR):
        return open_order
    remote = _razorpay("POST", "/orders", {
        "amount": amount, "currency": "INR", "receipt": f"book-{project['id']}",
        "notes": {"project_id": str(project["id"]), "product": project["tier"]},
    })
    with get_engine().begin() as conn:
        conn.execute(insert(orders).values(project_id=project["id"], user_id=user_id, product=project["tier"],
                                           amount_paise=amount, currency="INR", provider_ref=remote["id"]))
    events_service.track("checkout_started", project_id=project["id"], actor="buyer", tier=project["tier"])
    return get_order_by_ref(remote["id"])


def latest_order(project_id):
    with get_engine().connect() as conn:
        row = conn.execute(select(orders).where(orders.c.project_id == project_id)
                           .order_by(orders.c.id.desc()).limit(1)).mappings().first()
    return dict(row) if row else None


def paid_order(project_id):
    with get_engine().connect() as conn:
        row = conn.execute(select(orders).where(orders.c.project_id == project_id, orders.c.status == "paid")
                           .order_by(orders.c.id.desc()).limit(1)).mappings().first()
    return dict(row) if row else None


def get_order(project_id, order_id):
    with get_engine().connect() as conn:
        row = conn.execute(select(orders).where(orders.c.id == order_id, orders.c.project_id == project_id)
                           ).mappings().first()
    return dict(row) if row else None


def get_order_by_ref(provider_ref):
    with get_engine().connect() as conn:
        row = conn.execute(select(orders).where(orders.c.provider_ref == provider_ref)).mappings().first()
    return dict(row) if row else None


def checkout_signature_ok(order_ref, payment_id, signature):
    """Razorpay signs order_id|payment_id with the key secret when Checkout succeeds."""
    expected = hmac.new(config.RAZORPAY_KEY_SECRET.encode(), f"{order_ref}|{payment_id}".encode(),
                        hashlib.sha256).hexdigest()
    return bool(signature) and hmac.compare_digest(expected, signature)


def webhook_signature_ok(body, signature):
    if not config.RAZORPAY_WEBHOOK_SECRET or not signature:
        return False
    expected = hmac.new(config.RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def mark_paid(order_ref, payment_id, channel="web"):
    """Unlock the book for this order. Safe to call any number of times; returns the order or None."""
    order = get_order_by_ref(order_ref)
    if order is None:
        return None
    if order["status"] == "paid":
        return order
    for _ in range(3):
        try:
            with get_engine().begin() as conn:
                changed = conn.execute(
                    update(orders).where(orders.c.id == order["id"], orders.c.status != "paid")
                    .values(status="paid", provider_payment_id=payment_id, paid_at=func.now(), failure_reason=None,
                            invoice_number=_next_invoice_number(conn))
                ).rowcount
                if changed:
                    conn.execute(update(projects).where(projects.c.id == order["project_id"])
                                 .values(payment_status="paid", updated_at=func.now()))
                    events_service.track("payment_succeeded", project_id=order["project_id"], actor="buyer",
                                         channel=channel, conn=conn, amount_paise=order["amount_paise"],
                                         tier=order["product"])
            break
        except IntegrityError:  # two requests took the same invoice number; the next try gets a new one
            continue
    return get_order_by_ref(order_ref)


def mark_failed(order_ref, reason):
    order = get_order_by_ref(order_ref)
    if order is None or order["status"] != "created":
        return order
    with get_engine().begin() as conn:
        conn.execute(update(orders).where(orders.c.id == order["id"], orders.c.status == "created")
                     .values(failure_reason=(reason or "unknown")[:200]))
    events_service.track("payment_failed", project_id=order["project_id"], actor="buyer", channel="system",
                         reason=(reason or "unknown")[:40])
    return get_order_by_ref(order_ref)


def handle_webhook(payload):
    """Returns True when handled (or nothing to do), False when the order isn't known yet (Razorpay retries)."""
    event = payload.get("event")
    entity = ((payload.get("payload") or {}).get("payment") or {}).get("entity") or {}
    order_ref = entity.get("order_id") or (((payload.get("payload") or {}).get("order") or {}).get("entity")
                                           or {}).get("id")
    if event not in ("payment.captured", "order.paid", "payment.failed") or not order_ref:
        return True
    if get_order_by_ref(order_ref) is None:
        return False
    if event == "payment.failed":
        mark_failed(order_ref, entity.get("error_reason") or entity.get("error_code"))
    else:
        mark_paid(order_ref, entity.get("id"), channel="system")
    return True


def mark_refunded(order_id):
    """Manual refund bookkeeping (the refund itself is made in the Razorpay dashboard)."""
    with get_engine().begin() as conn:
        row = conn.execute(select(orders).where(orders.c.id == order_id)).mappings().first()
        if row is None or row["status"] != "paid":
            return False
        conn.execute(update(orders).where(orders.c.id == order_id)
                     .values(status="refunded", refunded_at=func.now()))
        conn.execute(update(projects).where(projects.c.id == row["project_id"])
                     .values(payment_status="refunded", updated_at=func.now()))
    return True


def invoice(order, project, buyer):
    """What the invoice page shows. Amounts are in rupees; prices include GST when a GSTIN is set."""
    total = order["amount_paise"] / 100
    taxed = bool(config.SELLER_GSTIN)
    taxable = round(total / (1 + config.GST_RATE_PERCENT / 100), 2) if taxed else total
    tier = config.TIERS.get(order["product"]) or {}
    return {
        "number": order["invoice_number"], "date": _aware(order["paid_at"]).date() if order["paid_at"] else None,
        "taxed": taxed, "seller": {"name": config.SELLER_NAME, "address": config.SELLER_ADDRESS,
                                   "gstin": config.SELLER_GSTIN, "state": config.SELLER_STATE},
        "buyer": {"name": buyer.get("name"), "email": buyer.get("email")},
        "item": f"{tier.get('label', order['product'])} voice cookbook: {project['title']}", "sac": config.SELLER_SAC,
        "taxable": taxable, "gst": round(total - taxable, 2), "rate": config.GST_RATE_PERCENT, "total": total,
        "payment_id": order["provider_payment_id"], "refunded": order["status"] == "refunded",
    }


def _next_invoice_number(conn):
    """Consecutive within the Indian financial year (April to March), e.g. AZ/2026-27/0001."""
    today = date.today()
    start = today.year if today.month >= 4 else today.year - 1
    prefix = f"{config.INVOICE_PREFIX}/{start}-{str(start + 1)[2:]}/"
    count = conn.execute(select(func.count()).select_from(orders)
                         .where(orders.c.invoice_number.like(prefix + "%"))).scalar()
    return f"{prefix}{count + 1:04d}"


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _razorpay(method, path, body):
    auth = base64.b64encode(f"{config.RAZORPAY_KEY_ID}:{config.RAZORPAY_KEY_SECRET}".encode()).decode()
    request = urllib.request.Request(config.RAZORPAY_API_URL + path, method=method, data=json.dumps(body).encode(),
                                     headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        log.error("Razorpay %s %s failed: %s %s", method, path, e.code, e.read()[:300])
        raise PaymentError("Payment couldn't start. Please try again.") from e
    except (urllib.error.URLError, TimeoutError) as e:
        log.error("Razorpay %s %s unreachable: %s", method, path, e)
        raise PaymentError("Payment couldn't start. Please check your connection and try again.") from e
