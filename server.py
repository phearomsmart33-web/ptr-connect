import hashlib
import os
import secrets
from datetime import datetime, timezone

from flask import Flask, jsonify, redirect, request, session
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from authlib.integrations.flask_client import OAuth
from urllib.parse import quote

app = Flask(__name__)
database_url = os.environ.get("DATABASE_URL", "sqlite:///ptrconnect.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config.update(
    SQLALCHEMY_DATABASE_URI=database_url,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
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
def health(): return jsonify(ok=True, database="connected", payment="pending", google_auth=bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET")))

def issue_session_token(user):
    token = secrets.token_urlsafe(32)
    db.session.add(Session(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id))
    db.session.commit()
    return token

@app.get("/auth/google")
def google_login():
    if not os.environ.get("GOOGLE_CLIENT_ID") or not os.environ.get("GOOGLE_CLIENT_SECRET"):
        return jsonify(error="Google authentication is not configured"), 503
    session["oauth_nonce"] = secrets.token_urlsafe(16)
    return google.authorize_redirect(
        "https://ptr-connect-api.onrender.com/auth/google/callback",
        nonce=session["oauth_nonce"],
    )

@app.get("/auth/google/callback")
def google_callback():
    token_data = google.authorize_access_token()
    session.pop("oauth_nonce", None)
    profile = token_data.get("userinfo")
    if not profile:
        profile = google.get("userinfo", token=token_data).json()
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
    if error: return error
    if request.method == "GET":
        rows = Booking.query.filter_by(user_id=user.id).order_by(Booking.id.desc()).all()
        return jsonify(bookings=[{"reference":b.reference,"service":b.service,"status":b.status,"createdAt":b.created_at.isoformat()} for b in rows])
    data = request.get_json(silent=True) or {}
    required = ("name", "contact", "service", "startDate", "duration", "quantity")
    if any(not data.get(key) for key in required): return jsonify(error="Missing required booking fields"), 400
    booking = Booking(reference="BKG-"+secrets.token_hex(4).upper(), user_id=user.id,
        customer_name=data["name"], contact=data["contact"], service=data["service"],
        extra_services=data.get("extraServices", []), start_date=data["startDate"], duration=data["duration"],
        quantity=int(data["quantity"]), destination=data.get("destination", ""), details=data.get("details", ""))
    db.session.add(booking); db.session.commit()
    return jsonify(reference=booking.reference, status=booking.status), 201

@app.post("/api/bookings/<reference>/invoice")
def create_invoice(reference):
    user, error = require_user()
    if error: return error
    booking = Booking.query.filter_by(reference=reference, user_id=user.id).first_or_404()
    data = request.get_json(silent=True) or {}; supplier=float(data.get("supplierCost",0)); fee=float(data.get("serviceFee",0))
    invoice = Invoice(reference="INV-"+secrets.token_hex(4).upper(), booking_id=booking.id,
        supplier_cost=supplier, service_fee=fee, total=supplier+fee)
    booking.status="INVOICE READY"; db.session.add(invoice); db.session.commit()
    return jsonify(reference=invoice.reference, status=invoice.status, total=float(invoice.total)), 201

@app.post("/api/invoices/<reference>/approve")
def approve_invoice(reference):
    user, error = require_user()
    if error: return error
    invoice = db.session.query(Invoice).join(Booking).filter(Invoice.reference==reference, Booking.user_id==user.id).first_or_404()
    invoice.status="APPROVED — PAYMENT PENDING"; db.session.get(Booking, invoice.booking_id).status=invoice.status
    db.session.commit(); return jsonify(reference=reference, status=invoice.status)

with app.app_context(): db.create_all()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
