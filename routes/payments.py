import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from cart_store import get_user_cart
from db import get_db_connection

router = APIRouter(prefix="/api/payments", tags=["payments"])
PAYSTACK_BASE_URL = "https://api.paystack.co"
ZERO_DECIMAL_CURRENCIES = {"JPY", "KRW"}


class CheckoutItem(BaseModel):
    product_id: int = 0
    name: str
    unit_price: float
    quantity: int = Field(gt=0)
    color: Optional[str] = None
    size: Optional[str] = None


class InitializeItemsPaymentRequest(BaseModel):
    email: str
    user_id: str = "default_user"
    currency: str = Field(default="NGN", min_length=3, max_length=3)
    callback_url: Optional[str] = None
    items: list[CheckoutItem]


class InitializePaymentRequest(BaseModel):
    email: str
    user_id: str = "default_user"
    currency: str = Field(default="NGN", min_length=3, max_length=3)
    callback_url: Optional[str] = None


class InitializePaymentResponse(BaseModel):
    order_id: int
    reference: str
    currency: str
    amount_minor: int
    authorization_url: str
    access_code: str
    status: str


class VerifyPaymentResponse(BaseModel):
    reference: str
    order_id: int
    payment_status: str
    order_status: str
    currency: str
    amount_minor: int
    paid_at: Optional[str] = None
    success_token: Optional[str] = None
    success_page_url: Optional[str] = None
    receipt_download_url: Optional[str] = None


def _normalize_currency(currency: str) -> str:
    normalized = currency.strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise HTTPException(status_code=400, detail="currency must be a 3-letter ISO code")
    return normalized


def _allowed_currencies() -> set[str]:
    raw = (os.getenv("PAYSTACK_ALLOWED_CURRENCIES") or "").strip()
    if not raw:
        return set()
    return {value.strip().upper() for value in raw.split(",") if value.strip()}


def _ensure_currency_allowed(currency: str) -> None:
    allowed = _allowed_currencies()
    if allowed and currency not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported currency '{currency}'. Allowed: {sorted(allowed)}",
        )


def _minor_multiplier(currency: str) -> int:
    return 1 if currency in ZERO_DECIMAL_CURRENCIES else 100


def _to_minor_units(value_major: float, currency: str) -> int:
    multiplier = _minor_multiplier(currency)
    value = Decimal(str(value_major)) * Decimal(multiplier)
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _generate_reference() -> str:
    return f"SAMPLIFY-{uuid.uuid4().hex[:18].upper()}"


def _paystack_secret() -> str:
    secret = (os.getenv("PAYSTACK_SECRET_KEY") or "").strip()
    if not secret:
        raise HTTPException(status_code=500, detail="Missing PAYSTACK_SECRET_KEY")
    return secret


def _webhook_secret() -> str:
    return os.getenv("PAYSTACK_WEBHOOK_SECRET") or _paystack_secret()


def _success_secret() -> str:
    return os.getenv("PAYMENT_SUCCESS_TOKEN_SECRET") or _paystack_secret()


def _default_callback_url() -> Optional[str]:
    app_base_url = (os.getenv("APP_BASE_URL") or "").rstrip("/")
    if not app_base_url:
        return None
    return f"{app_base_url}/payment/callback"


def _paystack_request(path: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {_paystack_secret()}"}
    url = f"{PAYSTACK_BASE_URL}{path}"
    try:
        if payload is None:
            response = requests.get(url, headers=headers, timeout=20)
        else:
            response = requests.post(url, headers=headers, json=payload, timeout=20)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Paystack request failed: {e}") from e

    try:
        data = response.json()
    except ValueError:
        snippet = (response.text or "")[:300]
        raise HTTPException(
            status_code=502,
            detail=f"Invalid response from Paystack (status={response.status_code}): {snippet}",
        )

    if response.status_code >= 400:
        message = data.get("message") if isinstance(data, dict) else "Paystack error"
        raise HTTPException(
            status_code=502,
            detail=f"Paystack error (status={response.status_code}): {message}",
        )

    return data


def _create_success_token(reference: str) -> str:
    return hmac.new(
        _success_secret().encode("utf-8"),
        reference.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _validate_success_token(reference: str, token: str) -> bool:
    expected = _create_success_token(reference)
    return hmac.compare_digest(expected, token)


def _calculate_amount_from_items(items: list[CheckoutItem], currency: str) -> int:
    if not items:
        raise HTTPException(status_code=400, detail="items cannot be empty")
    subtotal = sum(item.unit_price * item.quantity for item in items)
    tax = subtotal * 0.1
    total_major = subtotal + tax
    return _to_minor_units(total_major, currency)


def _calculate_amount_from_cart(user_id: str, currency: str) -> tuple[int, list[CheckoutItem]]:
    cart = get_user_cart(user_id)
    if not cart:
        raise HTTPException(status_code=400, detail="Cart is empty")

    items = [
        CheckoutItem(
            product_id=item["id"],
            name=item["name"],
            unit_price=float(item["price"]),
            quantity=int(item["quantity"]),
            color=item.get("color"),
            size=item.get("size"),
        )
        for item in cart
    ]
    return _calculate_amount_from_items(items, currency), items


def _insert_order_payment_items(
    user_id: str,
    email: str,
    currency: str,
    amount_minor: int,
    items: list[CheckoutItem],
    reference: str,
) -> int:
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Failed to connect to database")

    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO orders (user_id, email, amount_minor, currency, status, reference)
                    VALUES (%s, %s, %s, %s, 'pending', %s)
                    RETURNING id
                    """,
                    (user_id, email, amount_minor, currency, reference),
                )
                order_id = cursor.fetchone()[0]

                for item in items:
                    cursor.execute(
                        """
                        INSERT INTO order_items (
                            order_id, product_id, name, unit_price_minor, quantity, color, size
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            order_id,
                            item.product_id,
                            item.name,
                            _to_minor_units(item.unit_price, currency),
                            item.quantity,
                            item.color,
                            item.size,
                        ),
                    )

                cursor.execute(
                    """
                    INSERT INTO payments (order_id, reference, status, amount_minor, currency)
                    VALUES (%s, %s, 'pending', %s, %s)
                    """,
                    (order_id, reference, amount_minor, currency),
                )
                return order_id
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create payment records: {e}") from e
    finally:
        conn.close()


def _update_payment_and_order_status(
    reference: str,
    payment_status: str,
    order_status: str,
    gateway_response: dict[str, Any],
    paid_at: Optional[datetime] = None,
) -> tuple[int, str, int]:
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Failed to connect to database")

    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT p.order_id, p.status, p.currency, p.amount_minor
                    FROM payments p
                    WHERE p.reference = %s
                    """,
                    (reference,),
                )
                row = cursor.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Payment reference not found")

                order_id, current_status, currency, amount_minor = row
                if current_status == "paid" and payment_status == "paid":
                    return order_id, currency, amount_minor

                cursor.execute(
                    """
                    UPDATE payments
                    SET status = %s, paid_at = %s, gateway_response = %s::jsonb, updated_at = NOW()
                    WHERE reference = %s
                    """,
                    (payment_status, paid_at, json.dumps(gateway_response), reference),
                )
                cursor.execute(
                    """
                    UPDATE orders
                    SET status = %s, updated_at = NOW()
                    WHERE reference = %s
                    """,
                    (order_status, reference),
                )
                return order_id, currency, amount_minor
    finally:
        conn.close()


def _get_payment_record(reference: str) -> tuple[int, str, int, str, Optional[datetime]]:
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Failed to connect to database")

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT p.order_id, p.currency, p.amount_minor, p.status, p.paid_at
                FROM payments p
                WHERE p.reference = %s
                """,
                (reference,),
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Payment reference not found")
            return row
    finally:
        conn.close()


def _build_success_links(reference: str) -> tuple[str, str, str]:
    token = _create_success_token(reference)
    success_path = f"/api/payments/success?reference={reference}&token={token}"
    receipt_path = f"/api/payments/receipt/{reference}?token={token}"
    return token, success_path, receipt_path


def _initialize_common(email: str, user_id: str, currency: str, callback_url: Optional[str], items: list[CheckoutItem]) -> InitializePaymentResponse:
    amount_minor = _calculate_amount_from_items(items, currency)
    reference = _generate_reference()
    order_id = _insert_order_payment_items(
        user_id=user_id,
        email=email,
        currency=currency,
        amount_minor=amount_minor,
        items=items,
        reference=reference,
    )

    payload = {
        "email": email,
        "amount": amount_minor,
        "reference": reference,
        "currency": currency,
        "callback_url": callback_url or _default_callback_url(),
        "metadata": {"user_id": user_id},
    }
    if payload["callback_url"] is None:
        del payload["callback_url"]

    data = _paystack_request("/transaction/initialize", payload=payload)
    if not data.get("status") or not data.get("data"):
        _update_payment_and_order_status(
            reference=reference,
            payment_status="failed",
            order_status="failed",
            gateway_response=data if isinstance(data, dict) else {"response": data},
        )
        raise HTTPException(status_code=502, detail=f"Paystack initialize failed: {data.get('message')}")

    payment_data = data["data"]
    return InitializePaymentResponse(
        order_id=order_id,
        reference=reference,
        currency=currency,
        amount_minor=amount_minor,
        authorization_url=payment_data["authorization_url"],
        access_code=payment_data["access_code"],
        status="pending",
    )


@router.post("/paystack/initialize", response_model=InitializePaymentResponse)
def initialize_paystack_items_payment(request: InitializeItemsPaymentRequest):
    currency = _normalize_currency(request.currency)
    _ensure_currency_allowed(currency)
    return _initialize_common(
        email=request.email,
        user_id=request.user_id,
        currency=currency,
        callback_url=request.callback_url,
        items=request.items,
    )


@router.post("/initialize", response_model=InitializePaymentResponse)
def initialize_payment_from_cart(request: InitializePaymentRequest):
    currency = _normalize_currency(request.currency)
    _ensure_currency_allowed(currency)
    _, items = _calculate_amount_from_cart(request.user_id, currency)
    return _initialize_common(
        email=request.email,
        user_id=request.user_id,
        currency=currency,
        callback_url=request.callback_url,
        items=items,
    )


@router.get("/paystack/verify/{reference}", response_model=VerifyPaymentResponse)
@router.get("/verify/{reference}", response_model=VerifyPaymentResponse)
def verify_payment(reference: str, request: Request):
    expected_order_id, expected_currency, expected_amount_minor, existing_status, existing_paid_at = _get_payment_record(reference)

    # Final-state shortcut: once paid/failed locally, do not keep re-verifying with Paystack.
    if existing_status in {"paid", "failed"}:
        if existing_status == "paid":
            token, success_path, receipt_path = _build_success_links(reference)
            base = str(request.base_url).rstrip("/")
            return VerifyPaymentResponse(
                reference=reference,
                order_id=expected_order_id,
                payment_status="paid",
                order_status="paid",
                currency=expected_currency,
                amount_minor=expected_amount_minor,
                paid_at=existing_paid_at.isoformat() if existing_paid_at else None,
                success_token=token,
                success_page_url=f"{base}{success_path}",
                receipt_download_url=f"{base}{receipt_path}",
            )

        return VerifyPaymentResponse(
            reference=reference,
            order_id=expected_order_id,
            payment_status="failed",
            order_status="failed",
            currency=expected_currency,
            amount_minor=expected_amount_minor,
        )

    data = _paystack_request(f"/transaction/verify/{reference}")
    status_ok = bool(data.get("status"))
    gateway_data = data.get("data") or {}
    paystack_status = (gateway_data.get("status") or "").lower()
    gateway_currency = (gateway_data.get("currency") or "").upper()
    gateway_amount = gateway_data.get("amount")

    if gateway_currency and gateway_currency != expected_currency:
        status_ok = False
    if gateway_amount is not None:
        try:
            if int(gateway_amount) != expected_amount_minor:
                status_ok = False
        except (TypeError, ValueError):
            status_ok = False

    if status_ok and paystack_status == "success":
        paid_at_raw = gateway_data.get("paid_at")
        if paid_at_raw:
            try:
                paid_at = datetime.fromisoformat(paid_at_raw.replace("Z", "+00:00"))
            except ValueError:
                paid_at = datetime.now(timezone.utc)
        else:
            paid_at = datetime.now(timezone.utc)

        order_id, currency, amount_minor = _update_payment_and_order_status(
            reference=reference,
            payment_status="paid",
            order_status="paid",
            gateway_response=data,
            paid_at=paid_at,
        )
        token, success_path, receipt_path = _build_success_links(reference)
        base = str(request.base_url).rstrip("/")
        return VerifyPaymentResponse(
            reference=reference,
            order_id=expected_order_id if expected_order_id else order_id,
            payment_status="paid",
            order_status="paid",
            currency=currency,
            amount_minor=amount_minor,
            paid_at=paid_at.isoformat(),
            success_token=token,
            success_page_url=f"{base}{success_path}",
            receipt_download_url=f"{base}{receipt_path}",
        )

    order_id, currency, amount_minor = _update_payment_and_order_status(
        reference=reference,
        payment_status="failed",
        order_status="failed",
        gateway_response=data,
    )
    return VerifyPaymentResponse(
        reference=reference,
        order_id=expected_order_id if expected_order_id else order_id,
        payment_status="failed",
        order_status="failed",
        currency=currency,
        amount_minor=amount_minor,
    )


@router.post("/webhook")
async def paystack_webhook(request: Request):
    signature = request.headers.get("x-paystack-signature")
    secret = _webhook_secret().encode("utf-8")
    body = await request.body()
    digest = hmac.new(secret, body, hashlib.sha512).hexdigest()

    if not signature or not hmac.compare_digest(digest, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    event_payload = await request.json()
    event = event_payload.get("event")
    if event != "charge.success":
        return {"received": True, "ignored": True}

    data = event_payload.get("data", {})
    reference = data.get("reference") if isinstance(data, dict) else None
    if not reference:
        raise HTTPException(status_code=400, detail="Missing payment reference")

    _, expected_currency, expected_amount_minor, _, _ = _get_payment_record(reference)
    gateway_currency = (data.get("currency") or "").upper()
    gateway_amount = data.get("amount")
    if gateway_currency and gateway_currency != expected_currency:
        raise HTTPException(status_code=400, detail="Currency mismatch in webhook")
    if gateway_amount is not None:
        try:
            if int(gateway_amount) != expected_amount_minor:
                raise HTTPException(status_code=400, detail="Amount mismatch in webhook")
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid amount in webhook")

    paid_at = datetime.now(timezone.utc)
    _update_payment_and_order_status(
        reference=reference,
        payment_status="paid",
        order_status="paid",
        gateway_response=event_payload,
        paid_at=paid_at,
    )
    return {"received": True, "reference": reference}


@router.get("/success", response_class=HTMLResponse)
def payment_success_page(reference: str, token: str):
    if not _validate_success_token(reference, token):
        raise HTTPException(status_code=401, detail="Invalid success token")

    _, _, _, status, _ = _get_payment_record(reference)
    if status != "paid":
        raise HTTPException(status_code=403, detail="Payment not verified as successful")

    html = f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Payment Success</title>
      </head>
      <body style="font-family: Arial, sans-serif; max-width: 700px; margin: 40px auto; padding: 0 16px;">
        <h1>Payment Successful</h1>
        <p>Your payment has been verified successfully.</p>
        <p><strong>Reference:</strong> {reference}</p>
        <a href="/api/payments/receipt/{reference}?token={token}">Download Receipt</a>
      </body>
    </html>
    """
    return HTMLResponse(content=html)


@router.get("/receipt/{reference}")
def download_receipt(reference: str, token: str):
    if not _validate_success_token(reference, token):
        raise HTTPException(status_code=401, detail="Invalid receipt token")

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Failed to connect to database")

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT o.id, o.email, o.currency, o.amount_minor, o.status, p.paid_at, o.created_at
                FROM orders o
                JOIN payments p ON p.reference = o.reference
                WHERE o.reference = %s
                """,
                (reference,),
            )
            order_row = cursor.fetchone()
            if not order_row:
                raise HTTPException(status_code=404, detail="Order not found")

            order_id, email, currency, amount_minor, status, paid_at, created_at = order_row
            if status != "paid":
                raise HTTPException(status_code=403, detail="Receipt available only for successful payments")

            cursor.execute(
                """
                SELECT name, unit_price_minor, quantity, color, size
                FROM order_items
                WHERE order_id = %s
                ORDER BY id ASC
                """,
                (order_id,),
            )
            items = cursor.fetchall()
    finally:
        conn.close()

    lines = [
        "Samplify Payment Receipt",
        f"Reference: {reference}",
        f"Order ID: {order_id}",
        f"Email: {email}",
        f"Currency: {currency}",
        f"Total (minor): {amount_minor}",
        f"Created At: {created_at}",
        f"Paid At: {paid_at}",
        "",
        "Items:",
    ]
    for name, unit_price_minor, quantity, color, size in items:
        lines.append(
            f"- {name} | unit(minor): {unit_price_minor} | qty: {quantity} | color: {color or '-'} | size: {size or '-'}"
        )
    lines.append("")
    lines.append("Thank you for your payment.")

    content = "\n".join(lines)
    filename = f"receipt-{reference}.txt"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=content, media_type="text/plain; charset=utf-8", headers=headers)
