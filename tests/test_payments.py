import hashlib
import hmac
import io
import json
import re
from unittest import mock

import pytest
from sqlalchemy import select
from test_screens import _event_names, _onboard

import config
from models.database import get_engine
from models.schema import orders
from services import payment_service, project_service

SECRET, HOOK_SECRET = "test_key_secret", "test_hook_secret"


@pytest.fixture
def razorpay(monkeypatch):
    monkeypatch.setattr(config, "PILOT_FREE", False)
    monkeypatch.setattr(config, "RAZORPAY_KEY_ID", "rzp_test_abc")
    monkeypatch.setattr(config, "RAZORPAY_KEY_SECRET", SECRET)
    monkeypatch.setattr(config, "RAZORPAY_WEBHOOK_SECRET", HOOK_SECRET)
    calls = []

    def fake(method, path, body):
        calls.append(body)
        return {"id": f"order_T{len(calls)}", "amount": body["amount"], "status": "created"}

    monkeypatch.setattr(payment_service, "_razorpay", fake)
    return calls


def _sign(order_ref, payment_id):
    return hmac.new(SECRET.encode(), f"{order_ref}|{payment_id}".encode(), hashlib.sha256).hexdigest()


def _hook(client, event, order_ref, payment_id="pay_H1", secret=HOOK_SECRET, **entity):
    body = json.dumps({"event": event, "payload": {"payment": {"entity": {
        "id": payment_id, "order_id": order_ref, **entity}}}}).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/payments/razorpay/webhook", data=body, content_type="application/json",
                       headers={"X-Razorpay-Signature": signature})


def test_pilot_books_skip_payment(auth_client):
    pid = _onboard(auth_client)
    assert project_service.get_project(pid)["payment_status"] == "pilot"
    assert b"nothing to pay today" in auth_client.get(f"/p/{pid}/setup/pay").data


def test_paying_with_checkout_unlocks_the_book_and_gives_a_receipt(auth_client, razorpay):
    pid = _onboard(auth_client, finish=False)
    assert auth_client.get(f"/p/{pid}").headers["Location"].endswith(f"/p/{pid}/setup/pay")
    page = auth_client.get(f"/p/{pid}/setup/pay").data.decode()
    assert "Pay ₹1,200" in page and "data-pay" in page and "checkout.razorpay.com" in page
    blocked = auth_client.post(f"/p/{pid}/setup/pay", follow_redirects=True).data.decode()
    assert "Please finish the payment first" in blocked

    first = auth_client.post(f"/p/{pid}/pay/order").json
    assert first["order_id"] == "order_T1" and first["amount"] == 120000 and first["key"] == "rzp_test_abc"
    assert auth_client.post(f"/p/{pid}/pay/order").json["order_id"] == "order_T1"  # reused: no second order
    assert len(razorpay) == 1 and razorpay[0]["currency"] == "INR"

    verify = f"/p/{pid}/pay/verify"
    bad = auth_client.post(verify, json={"razorpay_order_id": "order_T1", "razorpay_payment_id": "pay_1",
                                         "razorpay_signature": "x"})
    assert bad.status_code == 400 and project_service.get_project(pid)["payment_status"] == "unpaid"
    good = auth_client.post(verify, json={"razorpay_order_id": "order_T1", "razorpay_payment_id": "pay_1",
                                          "razorpay_signature": _sign("order_T1", "pay_1")})
    assert good.json["redirect"].endswith(f"/p/{pid}/setup/invite")
    assert project_service.get_project(pid)["payment_status"] == "paid"
    order = payment_service.paid_order(pid)
    assert re.fullmatch(r"AZ/\d{4}-\d{2}/0001", order["invoice_number"])

    # The webhook for the same payment, delivered twice, changes nothing.
    assert _hook(auth_client, "payment.captured", "order_T1", "pay_1").status_code == 200
    assert _hook(auth_client, "payment.captured", "order_T1", "pay_1").status_code == 200
    assert _event_names().count("payment_succeeded") == 1 and _event_names().count("checkout_started") == 1
    assert payment_service.paid_order(pid)["invoice_number"] == order["invoice_number"]
    assert auth_client.post(f"/p/{pid}/pay/order").status_code == 409  # already paid

    receipt = auth_client.get(f"/p/{pid}/orders/{order['id']}/invoice").data.decode()
    assert "Receipt" in receipt and "₹1,200.00" in receipt and "GST not charged" in receipt
    assert f"/p/{pid}/orders/{order['id']}/invoice" in auth_client.get(f"/p/{pid}/book").data.decode()


def test_webhook_unlocks_a_book_when_the_browser_closed_after_paying(auth_client, razorpay):
    pid = _onboard(auth_client, finish=False)
    ref = auth_client.post(f"/p/{pid}/pay/order").json["order_id"]
    assert b"won't be charged twice" in auth_client.get(f"/p/{pid}/setup/pay").data

    assert _hook(auth_client, "payment.failed", ref, error_reason="payment_failed").status_code == 200
    assert project_service.get_project(pid)["payment_status"] == "unpaid" and "payment_failed" in _event_names()

    assert _hook(auth_client, "payment.captured", ref, secret="wrong").status_code == 400
    assert _hook(auth_client, "payment.captured", "order_unknown").status_code == 503  # Razorpay will retry
    assert _hook(auth_client, "refund.created", ref).status_code == 200  # events we don't use are fine
    assert _hook(auth_client, "payment.captured", ref, "pay_late").status_code == 200
    assert project_service.get_project(pid)["payment_status"] == "paid"
    assert b"Paid. Thank you!" in auth_client.get(f"/p/{pid}/setup/pay").data
    assert auth_client.post(f"/p/{pid}/setup/pay").headers["Location"].endswith(f"/p/{pid}/setup/invite")


def test_invoice_numbers_count_up_and_show_gst_when_registered(auth_client, razorpay, monkeypatch):
    numbers = []
    for _ in range(2):
        pid = _onboard(auth_client, finish=False)
        ref = auth_client.post(f"/p/{pid}/pay/order").json["order_id"]
        _hook(auth_client, "payment.captured", ref)
        numbers.append(payment_service.paid_order(pid)["invoice_number"])
    assert [n[-4:] for n in numbers] == ["0001", "0002"]

    monkeypatch.setattr(config, "SELLER_GSTIN", "07ABCDE1234F1Z5")
    monkeypatch.setattr(config, "SELLER_SAC", "998439")
    order = payment_service.paid_order(pid)
    page = auth_client.get(f"/p/{pid}/orders/{order['id']}/invoice").data.decode()
    assert "Tax invoice" in page and "GSTIN 07ABCDE1234F1Z5" in page and "SAC 998439" in page
    assert "₹1,016.95" in page and "₹183.05" in page and "GST 18%" in page

    assert payment_service.mark_refunded(order["id"]) and not payment_service.mark_refunded(order["id"])
    assert project_service.get_project(pid)["payment_status"] == "refunded"
    assert "was refunded" in auth_client.get(f"/p/{pid}/orders/{order['id']}/invoice").data.decode()


def test_orders_and_receipts_are_private(client, razorpay):
    from conftest import register
    register(client, email="a@example.com")
    pid = _onboard(client, finish=False)
    ref = client.post(f"/p/{pid}/pay/order").json["order_id"]
    _hook(client, "payment.captured", ref)
    oid = payment_service.paid_order(pid)["id"]
    client.get("/logout")
    register(client, email="b@example.com")
    assert client.get(f"/p/{pid}/orders/{oid}/invoice").status_code == 302
    assert client.post(f"/p/{pid}/pay/verify", json={}).status_code == 302
    other = _onboard(client, finish=False)
    forged = client.post(f"/p/{other}/pay/verify",
                         json={"razorpay_order_id": ref, "razorpay_payment_id": "pay_H1",
                               "razorpay_signature": _sign(ref, "pay_H1")})
    assert forged.status_code == 400  # someone else's order can't unlock this book
    assert project_service.get_project(other)["payment_status"] == "unpaid"


def test_razorpay_errors_and_request_shape(auth_client, monkeypatch):
    monkeypatch.setattr(config, "PILOT_FREE", False)
    monkeypatch.setattr(config, "RAZORPAY_KEY_ID", "rzp_test_abc")
    monkeypatch.setattr(config, "RAZORPAY_KEY_SECRET", SECRET)
    pid = _onboard(auth_client, finish=False)
    with mock.patch("urllib.request.urlopen") as urlopen:
        urlopen.return_value.__enter__.return_value = io.BytesIO(b'{"id": "order_R1"}')
        assert auth_client.post(f"/p/{pid}/pay/order").json["order_id"] == "order_R1"
        sent = urlopen.call_args.args[0]
        assert sent.full_url == "https://api.razorpay.com/v1/orders" and sent.get_method() == "POST"
        assert sent.headers["Authorization"].startswith("Basic ") and json.loads(sent.data)["amount"] == 120000
    with get_engine().begin() as conn:
        conn.execute(orders.delete())
    import urllib.error
    with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
        failed = auth_client.post(f"/p/{pid}/pay/order")
    assert failed.status_code == 502 and "try again" in failed.json["error"]
    with get_engine().connect() as conn:
        assert conn.execute(select(orders)).first() is None


def test_payments_stay_off_without_keys(auth_client, monkeypatch):
    monkeypatch.setattr(config, "PILOT_FREE", False)
    monkeypatch.setattr(config, "RAZORPAY_KEY_ID", "")
    pid = _onboard(auth_client, finish=False)
    assert "Payments open soon" in auth_client.post(f"/p/{pid}/setup/pay", follow_redirects=True).data.decode()
    assert auth_client.post(f"/p/{pid}/pay/order").status_code == 409
