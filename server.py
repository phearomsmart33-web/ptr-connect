import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import Flask, jsonify, redirect, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from authlib.integrations.flask_client import OAuth
from urllib.parse import quote
from urllib.parse import urlencode
from urllib.parse import urlparse
from werkzeug.middleware.proxy_fix import ProxyFix
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding as rsa_padding
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy.exc import IntegrityError

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
database_url = os.environ.get("DATABASE_URL", "sqlite:///ptrconnect.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config.update(
    SQLALCHEMY_DATABASE_URI=database_url,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="None",
    PREFERRED_URL_SCHEME="https",
    MAX_CONTENT_LENGTH=64 * 1024,
)
db = SQLAlchemy(app)
oauth = OAuth(app)
google = oauth.register(
    name="google",
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)
FRONTEND_URL = "https://www.ptrconnect.online"
PAYWAY_RETURN_URL = "https://ptr-connect-api.onrender.com/api/payments/payway/callback"
PAYWAY_LINK_PATH = "/api/merchant-portal/merchant-access/payment-link/create"
PAYWAY_CHECK_PATH = "/api/payment-gateway/v1/payments/check-transaction-2"
PAYWAY_BASE_URLS = {
    "sandbox": "https://checkout-sandbox.payway.com.kh",
    "production": "https://checkout.payway.com.kh",
}
SERVICE_PRICING = {
    "hotel": {"name": "5-Star Hotel Booking", "unit_price": Decimal("700.00"), "fee_rate": Decimal("0.10")},
    "transport": {"name": "Private Transportation", "unit_price": Decimal("180.00"), "fee_rate": Decimal("0.12")},
    "tour": {"name": "Cambodia Tour Package", "unit_price": Decimal("2500.00"), "fee_rate": Decimal("0.12")},
    "business": {"name": "Business & Local Legal Coordination", "unit_price": Decimal("20000.00"), "fee_rate": Decimal("0.08")},
}
MONEY_PLACES = Decimal("0.01")
MAX_BOOKING_QUANTITY = 1000
PAYWAY_CREATE_TIMEOUT = (3.05, 8)
PAYWAY_CHECK_TIMEOUT = (1.0, 1.5)
PAYWAY_RECHECK_SECONDS = 10
PAYWAY_CREATE_STALE_SECONDS = 120
INVOICE_READY = "INVOICE READY"
INVOICE_APPROVED = "APPROVED - PAYMENT PENDING"
PAYMENT_LINK_READY = "PAYMENT LINK READY"
PAYMENT_VERIFYING = "PAYMENT VERIFICATION PENDING"
PAYMENT_PAID = "PAID"
LEGACY_APPROVED_STATUS = "APPROVED â€” PAYMENT PENDING"
LEGACY_APPROVED_STATUSES = {
    LEGACY_APPROVED_STATUS,
    "APPROVED \u2014 PAYMENT PENDING",
    "APPROVED \u00e2\u20ac\u201d PAYMENT PENDING",
}
APPROVED_PAYMENT_STATUSES = {INVOICE_APPROVED, *LEGACY_APPROVED_STATUSES}
PAYMENT_FLOW_STATUSES = {
    INVOICE_APPROVED,
    *LEGACY_APPROVED_STATUSES,
    PAYMENT_LINK_READY,
    PAYMENT_VERIFYING,
    PAYMENT_PAID,
}
PAYWAY_TRANSACTION_ID_RE = re.compile(r"^[0-9]{1,20}$")
logger = logging.getLogger(__name__)
CORS(app, resources={r"/api/*": {"origins": [
    "https://www.ptrconnect.online", "https://ptrconnect.online"
]}})

def now(): return datetime.now(timezone.utc)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(320), unique=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)

class Session(db.Model):
    token_hash = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)

class GoogleAuthState(db.Model):
    state = db.Column(db.String(128), primary_key=True)
    nonce = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(32), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    customer_name = db.Column(db.String(200), nullable=False)
    contact = db.Column(db.String(320), nullable=False)
    service = db.Column(db.String(100), nullable=False)
    extra_services = db.Column(db.JSON, default=list, nullable=False)
    start_date = db.Column(db.String(32), nullable=False)
    duration = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    destination = db.Column(db.String(200), default="")
    details = db.Column(db.Text, default="")
    status = db.Column(db.String(80), default="RECORDED", nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=now, onupdate=now, nullable=False)

class BookingIdempotency(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    idempotency_key = db.Column(db.String(128), nullable=False)
    request_fingerprint = db.Column(db.String(64), nullable=False)
    booking_id = db.Column(db.Integer, db.ForeignKey("booking.id", ondelete="CASCADE"), unique=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)
    __table_args__ = (
        db.UniqueConstraint("user_id", "idempotency_key", name="uq_booking_idempotency_user_key"),
    )

class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(32), unique=True, nullable=False)
    booking_id = db.Column(db.Integer, db.ForeignKey("booking.id"), unique=True, nullable=False)
    supplier_cost = db.Column(db.Numeric(12, 2), nullable=False)
    service_fee = db.Column(db.Numeric(12, 2), nullable=False)
    total = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(80), default="INVOICE READY", nullable=False)
    payment_link = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=now, onupdate=now, nullable=False)

class PaymentAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoice.id", ondelete="CASCADE"), unique=True, nullable=False)
    merchant_ref_no = db.Column(db.String(50), unique=True, nullable=False)
    provider_link_id = db.Column(db.Text)
    create_log_id = db.Column(db.String(100))
    payway_tran_id = db.Column(db.String(100), unique=True)
    payment_link = db.Column(db.Text)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(3), default="USD", nullable=False)
    status = db.Column(db.String(40), default="CREATING", nullable=False)
    error_code = db.Column(db.String(40))
    last_checked_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=now, onupdate=now, nullable=False)

class PayWayError(Exception):
    def __init__(self, message, code="PAYWAY_ERROR"):
        super().__init__(message)
        self.code = code

def money(value):
    if isinstance(value, bool):
        raise InvalidOperation
    amount = Decimal(str(value))
    if not amount.is_finite():
        raise InvalidOperation
    return amount.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)

def invoice_json(invoice):
    return {
        "reference": invoice.reference,
        "status": invoice.status,
        "supplierCost": float(invoice.supplier_cost),
        "serviceFee": float(invoice.service_fee),
        "total": float(invoice.total),
        "currency": "USD",
    }

def payment_json(invoice, attempt):
    result = {
        "invoice": invoice_json(invoice),
        "paymentStatus": attempt.status if attempt else "NOT STARTED",
        "paid": bool(attempt and attempt.status == PAYMENT_PAID and invoice.status == PAYMENT_PAID),
        "mode": payway_mode() if payway_mode() in PAYWAY_BASE_URLS else "invalid",
    }
    if attempt and attempt.status in {
        "RECONCILIATION_REQUIRED",
        "VERIFICATION_CONFLICT",
        "VERIFICATION_MISMATCH",
    }:
        result["manualActionRequired"] = True
    if (
        attempt
        and attempt.payment_link
        and not attempt.payway_tran_id
        and attempt.status in {"LINK_READY", "PENDING"}
    ):
        try:
            result["paymentUrl"] = validate_payway_link(attempt.payment_link)
        except PayWayError:
            # Never return a stored URL that does not satisfy the current
            # exact PayWay-host policy.
            pass
    return result

def payway_mode():
    return os.environ.get("PAYWAY_MODE", "sandbox").strip().lower()

def payway_link_expiry():
    try:
        lifetime = int(os.environ.get("PAYWAY_LINK_LIFETIME_SECONDS", "3600"))
    except ValueError:
        lifetime = 3600
    lifetime = min(max(lifetime, 300), 86400)
    return int((now() + timedelta(seconds=lifetime)).timestamp())

def payway_allowed_link_hosts(mode=None):
    mode = mode or payway_mode()
    defaults = {
        "sandbox": {"dpayment-euat.payway.com.kh"},
        "production": {"dpayment.payway.com.kh"},
    }
    hosts = set(defaults.get(mode, set()))
    for item in os.environ.get("PAYWAY_ALLOWED_LINK_HOSTS", "").split(","):
        hostname = item.strip().lower().rstrip(".")
        if hostname and (hostname == "payway.com.kh" or hostname.endswith(".payway.com.kh")):
            hosts.add(hostname)
    return hosts

def payway_public_key_source():
    inline_key = os.environ.get("PAYWAY_RSA_PUBLIC_KEY", "").strip()
    if inline_key:
        return inline_key.replace("\\n", "\n").encode("utf-8")
    key_path = os.environ.get("PAYWAY_RSA_PUBLIC_KEY_PATH", "").strip()
    if key_path:
        try:
            with open(key_path, "rb") as key_file:
                return key_file.read()
        except OSError as exc:
            raise PayWayError("PayWay public key file could not be read", "PAYWAY_KEY_UNREADABLE") from exc
    raise PayWayError("PayWay RSA public key is not configured", "PAYWAY_KEY_MISSING")

def payway_config():
    mode = payway_mode()
    merchant_id = os.environ.get("PAYWAY_MERCHANT_ID", "").strip()
    api_key = os.environ.get("PAYWAY_API_KEY", "").strip()
    if mode not in PAYWAY_BASE_URLS:
        raise PayWayError("Unsupported PayWay mode", "PAYWAY_MODE_INVALID")
    if not merchant_id or not api_key:
        raise PayWayError("PayWay credentials are not configured", "PAYWAY_CONFIG_MISSING")
    return {
        "mode": mode,
        "merchant_id": merchant_id,
        "api_key": api_key,
        "base_url": PAYWAY_BASE_URLS[mode],
    }

def payway_is_configured():
    has_key = bool(os.environ.get("PAYWAY_RSA_PUBLIC_KEY", "").strip() or os.environ.get("PAYWAY_RSA_PUBLIC_KEY_PATH", "").strip())
    return bool(
        payway_mode() in PAYWAY_BASE_URLS
        and os.environ.get("PAYWAY_MERCHANT_ID", "").strip()
        and os.environ.get("PAYWAY_API_KEY", "").strip()
        and has_key
    )

def payway_request_time():
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

def payway_hmac(payload, api_key):
    digest = hmac.new(api_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha512).digest()
    return base64.b64encode(digest).decode("ascii")

def encrypt_payway_merchant_auth(data):
    try:
        public_key = serialization.load_pem_public_key(payway_public_key_source())
    except (TypeError, ValueError) as exc:
        raise PayWayError("PayWay RSA public key is invalid", "PAYWAY_KEY_INVALID") from exc
    if not hasattr(public_key, "encrypt") or not hasattr(public_key, "key_size"):
        raise PayWayError("PayWay RSA public key is invalid", "PAYWAY_KEY_INVALID")
    source = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    max_chunk = (public_key.key_size // 8) - 11
    if max_chunk <= 0:
        raise PayWayError("PayWay RSA public key is invalid", "PAYWAY_KEY_INVALID")
    encrypted = b"".join(
        public_key.encrypt(source[offset:offset + max_chunk], rsa_padding.PKCS1v15())
        for offset in range(0, len(source), max_chunk)
    )
    return base64.b64encode(encrypted).decode("ascii")

def validate_payway_link(link, mode=None):
    try:
        parsed = urlparse(link)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except (TypeError, ValueError):
        raise PayWayError("PayWay returned an invalid payment link", "PAYWAY_LINK_INVALID")
    if (
        parsed.scheme != "https"
        or hostname not in payway_allowed_link_hosts(mode)
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or not parsed.path.startswith("/")
        or parsed.fragment
    ):
        raise PayWayError("PayWay returned an invalid payment link", "PAYWAY_LINK_INVALID")
    return link

def create_payway_payment_link(invoice, booking, merchant_ref_no):
    config = payway_config()
    request_time = payway_request_time()
    merchant_data = {
        "mc_id": config["merchant_id"],
        "title": f"PTR Connect invoice {invoice.reference}"[:250],
        "amount": float(money(invoice.total)),
        "currency": "USD",
        "description": f"{SERVICE_PRICING[booking.service]['name']} - {booking.reference}"[:250],
        "payment_limit": 1,
        "expired_date": payway_link_expiry(),
        "return_url": base64.b64encode(PAYWAY_RETURN_URL.encode("utf-8")).decode("ascii"),
        "merchant_ref_no": merchant_ref_no,
    }
    merchant_auth = encrypt_payway_merchant_auth(merchant_data)
    signature = payway_hmac(request_time + config["merchant_id"] + merchant_auth, config["api_key"])
    multipart = {
        "request_time": (None, request_time),
        "merchant_id": (None, config["merchant_id"]),
        "merchant_auth": (None, merchant_auth),
        "hash": (None, signature),
    }
    try:
        response = requests.post(
            config["base_url"] + PAYWAY_LINK_PATH,
            files=multipart,
            timeout=PAYWAY_CREATE_TIMEOUT,
        )
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise PayWayError("PayWay could not create the payment link", "PAYWAY_UNAVAILABLE") from exc
    if not isinstance(result, dict):
        raise PayWayError("PayWay returned an invalid response", "PAYWAY_RESPONSE_INVALID")
    status = result.get("status") if isinstance(result.get("status"), dict) else {}
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    provider_code = str(status.get("code") or "")
    if provider_code != "00" or not data.get("payment_link"):
        safe_code = provider_code if re.fullmatch(r"[A-Za-z0-9_-]{1,40}", provider_code) else "PAYWAY_REJECTED"
        raise PayWayError("PayWay rejected the payment-link request", safe_code)
    try:
        response_amount = money(data.get("amount"))
        response_limit = int(data.get("payment_limit"))
        response_expiry = int(data.get("expired_date"))
    except (InvalidOperation, TypeError, ValueError):
        raise PayWayError("PayWay returned invalid payment-link details", "PAYWAY_RESPONSE_INVALID")
    if (
        response_amount != money(invoice.total)
        or str(data.get("currency") or "").upper() != "USD"
        or str(data.get("merchant_ref_no") or "") != merchant_ref_no
        or str(data.get("status") or "").upper() != "OPEN"
        or response_limit != 1
        or response_expiry != merchant_data["expired_date"]
        # The request carries base64, while PayWay's documented response
        # returns the decoded HTTPS URL.
        or str(data.get("return_url") or "") != PAYWAY_RETURN_URL
    ):
        raise PayWayError("PayWay returned mismatched payment-link details", "PAYWAY_RESPONSE_MISMATCH")
    return {
        "payment_link": validate_payway_link(str(data["payment_link"]), config["mode"]),
        "provider_link_id": str(data.get("id") or ""),
        "create_log_id": str(result.get("tran_id") or ""),
    }

def check_payway_transaction(tran_id, timeout=PAYWAY_CHECK_TIMEOUT):
    config = payway_config()
    request_time = payway_request_time()
    signature = payway_hmac(request_time + config["merchant_id"] + str(tran_id), config["api_key"])
    payload = {
        "req_time": request_time,
        "merchant_id": config["merchant_id"],
        "tran_id": str(tran_id),
        "hash": signature,
    }
    try:
        response = requests.post(config["base_url"] + PAYWAY_CHECK_PATH, json=payload, timeout=timeout)
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("invalid response")
        return result
    except (requests.RequestException, ValueError) as exc:
        raise PayWayError("PayWay could not verify the transaction", "PAYWAY_VERIFY_UNAVAILABLE") from exc

def verify_payway_callback_signature(payload, received_signature):
    config = payway_config()
    concatenated = ""
    for key in sorted(payload):
        value = payload[key]
        if isinstance(value, (dict, list)):
            value = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        elif value is None:
            value = ""
        concatenated += str(value)
    expected = payway_hmac(concatenated, config["api_key"])
    return hmac.compare_digest(expected, received_signature or "")

def payway_callback_signature_required():
    configured = os.environ.get("PAYWAY_REQUIRE_CALLBACK_SIGNATURE")
    if configured is None:
        # Payment Link callbacks do not document an HMAC header. They are
        # treated as untrusted hints and verified through Check Transaction.
        return False
    return configured.strip().lower() in {"1", "true", "yes", "on"}

def as_aware_utc(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

def checked_recently(attempt):
    checked_at = as_aware_utc(attempt.last_checked_at)
    return bool(checked_at and (now() - checked_at).total_seconds() < PAYWAY_RECHECK_SECONDS)

def payment_link_creation_is_stale(attempt):
    updated_at = as_aware_utc(attempt.updated_at or attempt.created_at)
    return bool(updated_at and (now() - updated_at).total_seconds() >= PAYWAY_CREATE_STALE_SECONDS)

def current_user():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "): return None
    digest = hashlib.sha256(auth[7:].encode()).hexdigest()
    session = db.session.get(Session, digest)
    return db.session.get(User, session.user_id) if session else None

def require_user():
    user = current_user()
    return user, None if user else (jsonify(error="Authentication required"), 401)

@app.get("/api/health")
def health():
    mode = payway_mode()
    return jsonify(
        ok=True,
        database="connected",
        payment={
            "provider": "payway",
            "mode": mode if mode in PAYWAY_BASE_URLS else "invalid",
            "configured": payway_is_configured(),
        },
        google_auth=bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET")),
    )

def invoice_for_user(reference, user):
    return (
        db.session.query(Invoice)
        .join(Booking)
        .filter(Invoice.reference == reference, Booking.user_id == user.id)
        .first_or_404()
    )

def calculate_booking_invoice(booking):
    pricing = SERVICE_PRICING.get(booking.service)
    if not pricing:
        raise ValueError("Unsupported service")
    supplier = money(pricing["unit_price"] * booking.quantity)
    fee = money(supplier * pricing["fee_rate"])
    return supplier, fee, money(supplier + fee)

def set_invoice_and_booking_status(invoice, status):
    if invoice.status == PAYMENT_PAID and status != PAYMENT_PAID:
        return
    invoice.status = status
    # A transaction id may be waiting for its uniqueness check at commit time.
    # Looking up the booking must not trigger an early autoflush that escapes
    # the reconciliation conflict handler.
    with db.session.no_autoflush:
        booking = db.session.get(Booking, invoice.booking_id)
    if booking and not (booking.status == PAYMENT_PAID and status != PAYMENT_PAID):
        booking.status = status

def reconcile_payway_attempt(attempt, candidate_tran_id=None):
    invoice = db.session.get(Invoice, attempt.invoice_id)
    if not invoice:
        raise PayWayError("Payment invoice no longer exists", "INVOICE_MISSING")
    if attempt.status == PAYMENT_PAID or invoice.status == PAYMENT_PAID:
        attempt.status = PAYMENT_PAID
        set_invoice_and_booking_status(invoice, PAYMENT_PAID)
        db.session.commit()
        return True

    tran_id = str(candidate_tran_id or attempt.payway_tran_id or "")
    if not PAYWAY_TRANSACTION_ID_RE.fullmatch(tran_id):
        raise PayWayError("Invalid PayWay transaction identifier", "PAYWAY_TRANSACTION_INVALID")
    if attempt.payway_tran_id and attempt.payway_tran_id != tran_id:
        raise PayWayError("Payment transaction does not match this invoice", "PAYWAY_TRANSACTION_MISMATCH")
    if checked_recently(attempt):
        return False

    attempt.last_checked_at = now()
    if attempt.status != PAYMENT_PAID:
        attempt.status = "VERIFYING"
        set_invoice_and_booking_status(invoice, PAYMENT_VERIFYING)
    db.session.commit()

    result = check_payway_transaction(tran_id)
    status = result.get("status") if isinstance(result.get("status"), dict) else {}
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    provider_code = str(status.get("code") or "")
    response_tran_id = str(status.get("tran_id") or "")
    provider_currency = str(data.get("payment_currency") or "").upper()
    provider_payment_status = str(data.get("payment_status") or "").upper()
    try:
        provider_amount = money(data.get("total_amount"))
    except (InvalidOperation, TypeError, ValueError):
        provider_amount = None

    response_identity_ok = response_tran_id == tran_id
    response_money_ok = (
        provider_amount == money(attempt.amount)
        and money(invoice.total) == money(attempt.amount)
        and provider_currency == str(attempt.currency).upper() == "USD"
    )
    trusted_candidate = provider_code == "00" and response_identity_ok and response_money_ok
    approved = (
        trusted_candidate
        and str(data.get("payment_status_code")) == "0"
        and provider_payment_status == "APPROVED"
    )

    def commit_reconciled_state():
        try:
            db.session.commit()
            return None
        except IntegrityError:
            # payway_tran_id is globally unique. A callback must not be able to
            # allocate one approved transaction to two invoices during a race.
            db.session.rollback()
            current = db.session.get(PaymentAttempt, attempt.id)
            current_invoice = db.session.get(Invoice, attempt.invoice_id)
            if current and current_invoice and (
                current.status == PAYMENT_PAID or current_invoice.status == PAYMENT_PAID
            ):
                current.status = PAYMENT_PAID
                set_invoice_and_booking_status(current_invoice, PAYMENT_PAID)
                db.session.commit()
                return True
            if current and current_invoice and not current.payway_tran_id:
                current.status = "VERIFICATION_CONFLICT"
                current.error_code = "PAYWAY_TRANSACTION_CONFLICT"
                set_invoice_and_booking_status(current_invoice, PAYMENT_VERIFYING)
                db.session.commit()
            return False

    if approved:
        attempt.payway_tran_id = tran_id
        attempt.status = PAYMENT_PAID
        attempt.error_code = None
        set_invoice_and_booking_status(invoice, PAYMENT_PAID)
        conflict_result = commit_reconciled_state()
        return True if conflict_result is None else conflict_result

    # Persist a transaction candidate only after Check Transaction itself
    # confirms its identity, amount and currency. This allows an eventually
    # consistent PENDING payment to be rechecked without trusting callback data.
    pending_candidate = trusted_candidate and provider_payment_status in {"PENDING", "PROCESSING"}
    if pending_candidate and not attempt.payway_tran_id:
        attempt.payway_tran_id = tran_id
    if attempt.status != PAYMENT_PAID:
        if provider_code == "00" and (not response_identity_ok or not response_money_ok):
            attempt.status = "VERIFICATION_MISMATCH"
            attempt.error_code = "PAYWAY_RESPONSE_MISMATCH"
            set_invoice_and_booking_status(invoice, PAYMENT_VERIFYING)
        elif pending_candidate:
            attempt.status = "PENDING"
            attempt.error_code = None
            set_invoice_and_booking_status(invoice, PAYMENT_VERIFYING)
        else:
            # A declined/unknown transaction is not bound to the link. A later
            # genuine payment on the same single-use link may have a new ID.
            attempt.status = "LINK_READY"
            attempt.error_code = (provider_payment_status or provider_code or "PAYMENT_NOT_APPROVED")[:40]
            set_invoice_and_booking_status(invoice, PAYMENT_LINK_READY)
    conflict_result = commit_reconciled_state()
    return False if conflict_result is None else conflict_result

def issue_session_token(user):
    token = secrets.token_urlsafe(32)
    db.session.add(Session(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id))
    db.session.commit()
    return token

@app.get("/auth/google")
def google_login():
    if not os.environ.get("GOOGLE_CLIENT_ID") or not os.environ.get("GOOGLE_CLIENT_SECRET"):
        return jsonify(error="Google authentication is not configured"), 503
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    db.session.add(GoogleAuthState(state=state, nonce=nonce))
    db.session.commit()
    params = urlencode({
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "redirect_uri": "https://ptr-connect-api.onrender.com/auth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "prompt": "select_account",
    })
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + params)

@app.get("/auth/google/callback")
def google_callback():
    state_value = request.args.get("state", "")
    code = request.args.get("code", "")
    saved_state = db.session.get(GoogleAuthState, state_value)
    if not saved_state or not code:
        return redirect(FRONTEND_URL + "/#auth_error=invalid_state")
    nonce = saved_state.nonce
    db.session.delete(saved_state)
    db.session.commit()
    token_response = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": "https://ptr-connect-api.onrender.com/auth/google/callback",
    }, timeout=15)
    token_response.raise_for_status()
    token_data = token_response.json()
    profile = id_token.verify_oauth2_token(
        token_data["id_token"], google_requests.Request(), os.environ["GOOGLE_CLIENT_ID"]
    )
    if profile.get("nonce") != nonce:
        return redirect(FRONTEND_URL + "/#auth_error=invalid_nonce")
    if not profile or not profile.get("email") or not profile.get("email_verified"):
        return redirect(FRONTEND_URL + "/#auth_error=unverified")
    email = profile["email"].lower()
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(email=email); db.session.add(user); db.session.flush()
    login_token = issue_session_token(user)
    return redirect(f"{FRONTEND_URL}/#auth_token={quote(login_token)}&email={quote(email)}")

@app.post("/api/login")
def login():
    return jsonify(error="Use Sign in with Google"), 410

@app.route("/api/bookings", methods=["GET", "POST"])
def bookings():
    user, error = require_user()
    if error:
        return error
    if request.method == "GET":
        rows = Booking.query.filter_by(user_id=user.id).order_by(Booking.id.desc()).all()
        results = []
        for booking in rows:
            invoice = Invoice.query.filter_by(booking_id=booking.id).first()
            attempt = PaymentAttempt.query.filter_by(invoice_id=invoice.id).first() if invoice else None
            item = {
                "reference": booking.reference,
                "service": booking.service,
                "status": booking.status,
                "createdAt": booking.created_at.isoformat(),
            }
            if invoice:
                item["invoice"] = invoice_json(invoice)
                item["paymentStatus"] = attempt.status if attempt else "NOT STARTED"
            results.append(item)
        return jsonify(bookings=results)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="A JSON booking object is required"), 400

    required = ("name", "contact", "service", "startDate", "duration", "quantity")
    if any(key not in data or data[key] in (None, "") for key in required):
        return jsonify(error="Missing required booking fields"), 400

    service = str(data["service"]).strip().lower()
    if service not in SERVICE_PRICING:
        return jsonify(error="Unsupported booking service"), 400
    try:
        if isinstance(data["quantity"], bool):
            raise ValueError
        quantity = int(data["quantity"])
        if str(data["quantity"]).strip() != str(quantity):
            raise ValueError
    except (TypeError, ValueError):
        return jsonify(error="Quantity must be a whole number"), 400
    if not 1 <= quantity <= MAX_BOOKING_QUANTITY:
        return jsonify(error=f"Quantity must be between 1 and {MAX_BOOKING_QUANTITY}"), 400

    def clean_text(key, maximum, required_value=False):
        value = data.get(key, "")
        if not isinstance(value, str):
            raise ValueError(key)
        value = value.strip()
        if (required_value and not value) or len(value) > maximum:
            raise ValueError(key)
        return value

    try:
        customer_name = clean_text("name", 200, True)
        contact = clean_text("contact", 320, True)
        start_date = clean_text("startDate", 32, True)
        duration = clean_text("duration", 100, True)
        destination = clean_text("destination", 200)
        details = clean_text("details", 5000)
    except ValueError as exc:
        return jsonify(error=f"Invalid booking field: {exc.args[0]}"), 400

    extra_services = data.get("extraServices", [])
    if not isinstance(extra_services, list) or len(extra_services) > 20:
        return jsonify(error="extraServices must be a list with at most 20 items"), 400
    if any(not isinstance(item, str) or not item.strip() or len(item.strip()) > 100 for item in extra_services):
        return jsonify(error="Invalid extra service"), 400
    extra_services = [item.strip() for item in extra_services]

    idempotency_key = request.headers.get("Idempotency-Key", "").strip()
    if idempotency_key and not re.fullmatch(r"[A-Za-z0-9._~:+/=-]{1,128}", idempotency_key):
        return jsonify(error="Invalid Idempotency-Key"), 400
    normalized_request = {
        "name": customer_name,
        "contact": contact,
        "service": service,
        "extraServices": extra_services,
        "startDate": start_date,
        "duration": duration,
        "quantity": quantity,
        "destination": destination,
        "details": details,
    }
    request_fingerprint = hashlib.sha256(
        json.dumps(normalized_request, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if idempotency_key:
        existing_request = BookingIdempotency.query.filter_by(
            user_id=user.id, idempotency_key=idempotency_key
        ).first()
        if existing_request:
            if existing_request.request_fingerprint != request_fingerprint:
                return jsonify(error="Idempotency-Key was already used for another booking"), 409
            existing_booking = db.session.get(Booking, existing_request.booking_id)
            if existing_booking:
                return jsonify(reference=existing_booking.reference, status=existing_booking.status), 200
            return jsonify(error="Booking replay record is unavailable"), 409

    booking = Booking(
        reference="BKG-" + secrets.token_hex(8).upper(),
        user_id=user.id,
        customer_name=customer_name,
        contact=contact,
        service=service,
        extra_services=extra_services,
        start_date=start_date,
        duration=duration,
        quantity=quantity,
        destination=destination,
        details=details,
    )
    db.session.add(booking)
    try:
        if idempotency_key:
            db.session.flush()
            db.session.add(
                BookingIdempotency(
                    user_id=user.id,
                    idempotency_key=idempotency_key,
                    request_fingerprint=request_fingerprint,
                    booking_id=booking.id,
                )
            )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if idempotency_key:
            existing_request = BookingIdempotency.query.filter_by(
                user_id=user.id, idempotency_key=idempotency_key
            ).first()
            if existing_request and existing_request.request_fingerprint == request_fingerprint:
                existing_booking = db.session.get(Booking, existing_request.booking_id)
                if existing_booking:
                    return jsonify(reference=existing_booking.reference, status=existing_booking.status), 200
        return jsonify(error="Could not record booking"), 409
    return jsonify(reference=booking.reference, status=booking.status), 201

@app.post("/api/bookings/<reference>/invoice")
def create_invoice(reference):
    user, error = require_user()
    if error:
        return error
    booking = Booking.query.filter_by(reference=reference, user_id=user.id).first_or_404()
    existing = Invoice.query.filter_by(booking_id=booking.id).first()
    if existing:
        return jsonify(invoice_json(existing)), 200

    # Client-supplied costs are deliberately ignored. Prices are derived only
    # from the server-maintained service catalogue and stored booking quantity.
    try:
        supplier, fee, total = calculate_booking_invoice(booking)
    except (InvalidOperation, TypeError, ValueError):
        return jsonify(error="This booking cannot be invoiced"), 400
    if total <= Decimal("0.00"):
        return jsonify(error="Invoice total must be positive"), 400

    invoice = Invoice(
        reference="INV-" + secrets.token_hex(8).upper(),
        booking_id=booking.id,
        supplier_cost=supplier,
        service_fee=fee,
        total=total,
        status=INVOICE_READY,
    )
    booking.status = INVOICE_READY
    db.session.add(invoice)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        # A concurrent request may have created the single invoice first.
        invoice = Invoice.query.filter_by(booking_id=booking.id).first()
        if not invoice:
            return jsonify(error="Could not create invoice"), 409
        return jsonify(invoice_json(invoice)), 200
    return jsonify(invoice_json(invoice)), 201

@app.post("/api/invoices/<reference>/approve")
def approve_invoice(reference):
    user, error = require_user()
    if error:
        return error
    invoice = invoice_for_user(reference, user)
    if invoice.status == PAYMENT_PAID:
        return jsonify(invoice_json(invoice)), 200
    if invoice.status not in PAYMENT_FLOW_STATUSES and invoice.status != INVOICE_READY:
        return jsonify(error="Invoice is not ready for approval"), 409
    if invoice.status == INVOICE_READY or invoice.status in LEGACY_APPROVED_STATUSES:
        set_invoice_and_booking_status(invoice, INVOICE_APPROVED)
        db.session.commit()
    return jsonify(invoice_json(invoice)), 200

@app.post("/api/invoices/<reference>/payment-link")
def create_invoice_payment_link(reference):
    user, error = require_user()
    if error:
        return error
    invoice = invoice_for_user(reference, user)
    booking = db.session.get(Booking, invoice.booking_id)
    attempt = PaymentAttempt.query.filter_by(invoice_id=invoice.id).first()

    # A payment link is single-use and single-instance per invoice. Repeated
    # calls return the same stored link and never create a second provider link.
    if attempt:
        if attempt.status == PAYMENT_PAID or invoice.status == PAYMENT_PAID:
            return jsonify(payment_json(invoice, attempt)), 200
        if attempt.payment_link and attempt.status in {"LINK_READY", "PENDING", "VERIFYING"}:
            return jsonify(payment_json(invoice, attempt)), 200
        if attempt.status == "CREATING":
            if payment_link_creation_is_stale(attempt):
                # The provider may have created a link before our process lost
                # its response. Never blindly create a second one.
                attempt.status = "RECONCILIATION_REQUIRED"
                attempt.error_code = "PAYWAY_CREATE_STATE_UNKNOWN"
                db.session.commit()
                return jsonify(payment_json(invoice, attempt)), 409
            return jsonify(error="Payment link creation is already in progress"), 409
        if attempt.status != "CONFIG_ERROR":
            return jsonify(
                error="This payment link requires reconciliation before another can be created",
                paymentStatus=attempt.status,
            ), 409

    if not booking or invoice.status not in APPROVED_PAYMENT_STATUSES:
        return jsonify(error="Approve the invoice before creating a payment link"), 409
    try:
        total = money(invoice.total)
    except (InvalidOperation, TypeError, ValueError):
        return jsonify(error="Invoice amount is invalid"), 409
    if total <= Decimal("0.00"):
        return jsonify(error="Invoice total must be positive"), 409
    if not payway_is_configured():
        return jsonify(error="PayWay is not configured"), 503

    if attempt and attempt.status == "CONFIG_ERROR":
        attempt.status = "CREATING"
        attempt.error_code = None
        if attempt.merchant_ref_no == invoice.reference and not attempt.create_log_id:
            attempt.merchant_ref_no = "PWR-" + secrets.token_hex(16).upper()
    else:
        attempt = PaymentAttempt(
            invoice_id=invoice.id,
            # This opaque value correlates the provider callback to exactly one
            # attempt. It is intentionally not the public invoice reference and
            # is never returned by our API.
            merchant_ref_no="PWR-" + secrets.token_hex(16).upper(),
            amount=total,
            currency="USD",
            status="CREATING",
        )
        db.session.add(attempt)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        attempt = PaymentAttempt.query.filter_by(invoice_id=invoice.id).first()
        if attempt and attempt.payment_link:
            return jsonify(payment_json(invoice, attempt)), 200
        return jsonify(error="Payment link creation is already in progress"), 409

    try:
        provider = create_payway_payment_link(invoice, booking, attempt.merchant_ref_no)
    except PayWayError as exc:
        local_config_errors = {
            "PAYWAY_CONFIG_MISSING",
            "PAYWAY_KEY_MISSING",
            "PAYWAY_KEY_UNREADABLE",
            "PAYWAY_KEY_INVALID",
            "PAYWAY_MODE_INVALID",
        }
        attempt.status = "CONFIG_ERROR" if exc.code in local_config_errors else "RECONCILIATION_REQUIRED"
        attempt.error_code = exc.code[:40]
        db.session.commit()
        http_status = 503 if exc.code in local_config_errors or exc.code == "PAYWAY_UNAVAILABLE" else 502
        return jsonify(error="PayWay could not create a payment link", code=exc.code), http_status

    attempt.provider_link_id = provider["provider_link_id"] or None
    # The create-link log/transaction identifier is not a customer payment
    # transaction identifier. They are intentionally stored separately.
    attempt.create_log_id = provider["create_log_id"] or None
    attempt.payment_link = provider["payment_link"]
    attempt.status = "LINK_READY"
    attempt.error_code = None
    invoice.payment_link = provider["payment_link"]
    set_invoice_and_booking_status(invoice, PAYMENT_LINK_READY)
    db.session.commit()
    return jsonify(payment_json(invoice, attempt)), 201

@app.get("/api/invoices/<reference>/payment-status")
def invoice_payment_status(reference):
    user, error = require_user()
    if error:
        return error
    invoice = invoice_for_user(reference, user)
    attempt = PaymentAttempt.query.filter_by(invoice_id=invoice.id).first()
    verification_deferred = False
    if attempt and attempt.status == "CREATING" and payment_link_creation_is_stale(attempt):
        attempt.status = "RECONCILIATION_REQUIRED"
        attempt.error_code = "PAYWAY_CREATE_STATE_UNKNOWN"
        db.session.commit()
    if (
        attempt
        and attempt.payway_tran_id
        and attempt.status != PAYMENT_PAID
        and not checked_recently(attempt)
    ):
        try:
            reconcile_payway_attempt(attempt)
        except PayWayError:
            verification_deferred = True
            db.session.rollback()
        invoice = db.session.get(Invoice, invoice.id)
        attempt = PaymentAttempt.query.filter_by(invoice_id=invoice.id).first()
    result = payment_json(invoice, attempt)
    if verification_deferred:
        result["verificationDeferred"] = True
    return jsonify(result), 200

@app.post("/api/payments/payway/callback")
def payway_payment_callback():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Invalid callback payload"), 400

    merchant_ref_no = str(payload.get("merchant_ref_no") or "").strip()
    tran_id = str(payload.get("tran_id") or "").strip()
    if not merchant_ref_no or len(merchant_ref_no) > 50 or not PAYWAY_TRANSACTION_ID_RE.fullmatch(tran_id):
        return jsonify(error="Invalid callback payload"), 400

    received_signature = request.headers.get("X-PayWay-HMAC-SHA512", "").strip()
    signature_valid = False
    if received_signature:
        try:
            signature_valid = verify_payway_callback_signature(payload, received_signature)
        except PayWayError:
            return jsonify(error="Payment verification is unavailable"), 503
        if not signature_valid:
            return jsonify(error="Invalid callback signature"), 401
    elif payway_callback_signature_required():
        return jsonify(error="Callback signature is required"), 401

    # Callback data is only a hint. Unknown references, non-success callback
    # statuses, conflicts and replay bursts are acknowledged without changing
    # payment state or revealing whether a merchant reference exists.
    attempt = PaymentAttempt.query.filter_by(merchant_ref_no=merchant_ref_no).first()
    if not attempt or str(payload.get("status") or "") != "00":
        return jsonify(received=True), 202
    invoice = db.session.get(Invoice, attempt.invoice_id)
    if not invoice:
        return jsonify(received=True), 202
    if attempt.status == PAYMENT_PAID or invoice.status == PAYMENT_PAID:
        set_invoice_and_booking_status(invoice, PAYMENT_PAID)
        attempt.status = PAYMENT_PAID
        db.session.commit()
        return jsonify(received=True, paid=True), 200
    if attempt.payway_tran_id and attempt.payway_tran_id != tran_id:
        return jsonify(received=True), 202
    if checked_recently(attempt):
        return jsonify(received=True), 202

    try:
        # Even a callback with a valid optional signature is only a hint. The
        # candidate is bound, and PAID is set, solely from Check Transaction.
        paid = reconcile_payway_attempt(attempt, candidate_tran_id=tran_id)
    except PayWayError:
        db.session.rollback()
        return jsonify(received=True, verification="deferred"), 202
    return jsonify(received=True, paid=paid), 200

with app.app_context(): db.create_all()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
