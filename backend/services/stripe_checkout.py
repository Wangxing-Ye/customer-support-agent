"""Stripe Checkout for pay_when=checkout_to_hold (paid Zoom consultations)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import stripe

from backend.config import (
    PAYMENT_HOLD_MINUTES,
    PUBLIC_BASE_URL,
    STRIPE_PRODUCT_CONSULT_30,
    STRIPE_PRODUCT_CONSULT_60,
    STRIPE_PRODUCT_STRATEGY_SESSION,
    STRIPE_SECRET_KEY,
    STRIPE_WEBHOOK_SECRET,
)

logger = logging.getLogger(__name__)

# Checkout Session expires_at must be at least 30 minutes from creation.
STRIPE_MIN_HOLD_MINUTES = 31

PRODUCT_BY_SLUG = {
    "consult-30": STRIPE_PRODUCT_CONSULT_30 or STRIPE_PRODUCT_STRATEGY_SESSION,
    "consult-60": STRIPE_PRODUCT_CONSULT_60 or STRIPE_PRODUCT_STRATEGY_SESSION,
}


def stripe_enabled() -> bool:
    return bool(STRIPE_SECRET_KEY)


def product_id_for_slug(slug: str) -> str:
    return (PRODUCT_BY_SLUG.get(slug) or "").strip()


def hold_minutes_for_stripe() -> int:
    return max(PAYMENT_HOLD_MINUTES, STRIPE_MIN_HOLD_MINUTES)


def _configure_stripe() -> None:
    if not STRIPE_SECRET_KEY:
        raise RuntimeError("STRIPE_SECRET_KEY is not set")
    stripe.api_key = STRIPE_SECRET_KEY


def price_id_for_product(product_id: str) -> str:
    _configure_stripe()
    product = stripe.Product.retrieve(product_id)
    default_price = product.get("default_price") if isinstance(product, dict) else product.default_price
    if isinstance(default_price, str) and default_price:
        return default_price
    if default_price is not None and getattr(default_price, "id", None):
        return default_price.id
    prices = stripe.Price.list(product=product_id, active=True, limit=1)
    if prices.data:
        return prices.data[0].id
    raise RuntimeError(f"Stripe product {product_id} has no active price")


def create_checkout_session(
    *,
    appointment_id: str,
    service_slug: str,
    customer_email: str,
    customer_name: str,
) -> tuple[str, str, datetime]:
    """Return (checkout_url, session_id, expires_at_utc)."""
    product_id = product_id_for_slug(service_slug)
    if not STRIPE_SECRET_KEY:
        raise RuntimeError("STRIPE_SECRET_KEY is not set")
    if not product_id:
        raise RuntimeError(f"No Stripe product configured for slug {service_slug}")

    _configure_stripe()
    price_id = price_id_for_product(product_id)
    minutes = hold_minutes_for_stripe()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price": price_id, "quantity": 1}],
        customer_email=customer_email,
        client_reference_id=appointment_id,
        metadata={
            "appointment_id": appointment_id,
            "service_slug": service_slug,
            "customer_email": customer_email,
            "customer_name": customer_name,
        },
        success_url=(
            f"{PUBLIC_BASE_URL}/pay/success?appointment_id={appointment_id}"
            "&session_id={CHECKOUT_SESSION_ID}"
        ),
        cancel_url=f"{PUBLIC_BASE_URL}/pay/cancel?appointment_id={appointment_id}",
        expires_at=int(expires_at.timestamp()),
    )
    url = session.url or ""
    if not url:
        raise RuntimeError("Stripe Checkout Session had no URL")
    return url, session.id, expires_at


def live_checkout_url(checkout_session_id: str) -> str:
    if not checkout_session_id or not STRIPE_SECRET_KEY:
        return ""
    _configure_stripe()
    sess = stripe.checkout.Session.retrieve(checkout_session_id)
    return sess.url or ""


def session_is_paid(checkout_session_id: str) -> bool:
    if not checkout_session_id or not STRIPE_SECRET_KEY:
        return False
    _configure_stripe()
    sess = stripe.checkout.Session.retrieve(checkout_session_id)
    return (sess.payment_status or "") == "paid"


def parse_webhook_event(payload: bytes, signature: str | None) -> stripe.Event:
    if not STRIPE_WEBHOOK_SECRET:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET is not set")
    if not signature:
        raise ValueError("Missing Stripe-Signature header")
    _configure_stripe()
    return stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)
