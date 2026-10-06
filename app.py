import os
from datetime import datetime, timedelta

import requests
from flask import Flask, jsonify, request, render_template, redirect, url_for, flash
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash


# ============================================================
# APP
# ============================================================

app = Flask(__name__)


# ============================================================
# ENVIRONMENT
# ============================================================

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key")

DATABASE_URL = os.getenv("DATABASE_URL")

DEFAULT_ADMIN_PASSWORD = os.getenv(
    "DEFAULT_ADMIN_PASSWORD",
    "admin123",
)


# ============================================================
# FLASK CONFIG
# ============================================================

app.config["SECRET_KEY"] = SECRET_KEY

if DATABASE_URL:
    # Render/Supabase may provide postgres://
    # SQLAlchemy expects postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace(
            "postgres://",
            "postgresql://",
            1,
        )

    # psycopg 3 driver
    if DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )

    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL

else:
    # Local fallback only
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///whatsapp_portal.db"


app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


# ============================================================
# DATABASE
# ============================================================

db = SQLAlchemy(app)


# ============================================================
# LOGIN
# ============================================================

login_manager = LoginManager()

login_manager.init_app(app)

login_manager.login_view = "login"

login_manager.login_message = "Please login to continue."


# ============================================================
# TIME
# ============================================================

def get_local_now():
    """
    Return current India Standard Time (IST)
    as a naive datetime.
    """

    return datetime.utcnow() + timedelta(
        hours=5,
        minutes=30,
    )


# ============================================================
# MODELS
# ============================================================

class User(UserMixin, db.Model):

    __tablename__ = "user"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    username = db.Column(
        db.String(150),
        unique=True,
        nullable=False,
        index=True,
    )

    password = db.Column(
        db.String(255),
        nullable=False,
    )

    user_type = db.Column(
        db.String(20),
        nullable=False,
        default="client",
    )

    credits = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    requests = db.relationship(
        "MessageRequest",
        back_populates="user",
        lazy=True,
        cascade="all, delete-orphan",
    )


class MessageRequest(db.Model):

    __tablename__ = "message_request"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "user.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    user = db.relationship(
        "User",
        back_populates="requests",
    )

    message_text = db.Column(
        db.Text,
        nullable=False,
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="Pending",
        server_default="Pending",
        index=True,
    )

    image1 = db.Column(
        db.String(255),
        nullable=True,
    )

    image2 = db.Column(
        db.String(255),
        nullable=True,
    )

    image3 = db.Column(
        db.String(255),
        nullable=True,
    )

    image4 = db.Column(
        db.String(255),
        nullable=True,
    )

    pdf_file = db.Column(
        db.String(255),
        nullable=True,
    )

    video_file = db.Column(
        db.String(255),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=get_local_now,
    )

    approved_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    report_ready_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    contacts = db.relationship(
        "Contact",
        back_populates="request",
        lazy=True,
        cascade="all, delete-orphan",
    )


class Contact(db.Model):

    __tablename__ = "contact"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    request_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "message_request.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    request = db.relationship(
        "MessageRequest",
        back_populates="contacts",
    )

    phone_number = db.Column(
        db.String(20),
        nullable=False,
        index=True,
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="Pending",
        server_default="Pending",
        index=True,
    )

    sent_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    error_message = db.Column(
        db.String(500),
        nullable=True,
    )

    is_csv_matched = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    whatsapp_message_id = db.Column(
        db.String(255),
        unique=True,
        nullable=True,
        index=True,
    )


class WhatsAppInstance(db.Model):

    __tablename__ = "whatsapp_instance"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    name = db.Column(
        db.String(50),
        nullable=True,
    )

    phone_number = db.Column(
        db.String(20),
        unique=True,
        nullable=True,
        index=True,
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="Active",
        server_default="Active",
        index=True,
    )

    last_used = db.Column(
        db.DateTime,
        nullable=False,
        default=get_local_now,
    )


# ============================================================
# LOGIN USER LOADER
# ============================================================

@login_manager.user_loader
def load_user(user_id):

    try:
        return db.session.get(
            User,
            int(user_id),
        )

    except Exception:
        return None


# ============================================================
# WHATSAPP CONFIGURATION
# ============================================================

WHATSAPP_API_TOKEN = os.getenv(
    "WHATSAPP_API_TOKEN"
)

WHATSAPP_PHONE_NUMBER_ID = os.getenv(
    "WHATSAPP_PHONE_NUMBER_ID"
)

WHATSAPP_VERIFY_TOKEN = os.getenv(
    "WHATSAPP_VERIFY_TOKEN"
)


def whatsapp_is_configured():

    return bool(
        WHATSAPP_API_TOKEN
        and WHATSAPP_PHONE_NUMBER_ID
    )


# ============================================================
# CREATE / RESET ADMIN
# ============================================================

def create_or_update_admin():

    try:

        admin = User.query.filter_by(
            username="admin"
        ).first()

        password = DEFAULT_ADMIN_PASSWORD

        if not password:
            password = "admin123"

        hashed_password = generate_password_hash(
            password
        )

        if admin is None:

            admin = User(
                username="admin",
                password=hashed_password,
                user_type="admin",
                credits=0,
            )

            db.session.add(admin)

            db.session.commit()

            print(
                "========================================"
            )

            print(
                "ADMIN USER CREATED"
            )

            print(
                "Username: admin"
            )

            print(
                "Password: "
                + password
            )

            print(
                "========================================"
            )

        else:

            # IMPORTANT:
            # Reset the admin password to the
            # DEFAULT_ADMIN_PASSWORD environment value.

            admin.password = hashed_password

            admin.user_type = "admin"

            db.session.commit()

            print(
                "========================================"
            )

            print(
                "ADMIN USER UPDATED"
            )

            print(
                "Username: admin"
            )

            print(
                "Password: "
                + password
            )

            print(
                "========================================"
            )

    except Exception as error:

        db.session.rollback()

        print(
            "ADMIN INITIALIZATION ERROR:",
            error,
        )


# ============================================================
# INITIALIZE DATABASE
# ============================================================

def initialize_database():

    try:

        print(
            "Initializing database..."
        )

        db.create_all()

        print(
            "Database tables ready."
        )

        create_or_update_admin()

    except Exception as error:

        db.session.rollback()

        print(
            "DATABASE INITIALIZATION ERROR:",
            error,
        )


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"],
)
def login():

    if current_user.is_authenticated:

        return redirect(
            url_for("dashboard")
        )

    if request.method == "POST":

        username = (
            request.form.get(
                "username",
                ""
            )
            .strip()
        )

        password = request.form.get(
            "password",
            "",
        )

        user = User.query.filter_by(
            username=username
        ).first()

        if (
            user
            and check_password_hash(
                user.password,
                password,
            )
        ):

            login_user(
                user,
                remember=True,
            )

            next_page = request.args.get(
                "next"
            )

            if next_page:
                return redirect(
                    next_page
                )

            return redirect(
                url_for("dashboard")
            )

        flash(
            "Invalid username or password",
            "danger",
        )

    return render_template(
        "login.html"
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
@login_required
def logout():

    logout_user()

    return redirect(
        url_for("login")
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/")
def index():

    if current_user.is_authenticated:

        return redirect(
            url_for("dashboard")
        )

    return redirect(
        url_for("login")
    )


@app.route("/dashboard")
@login_required
def dashboard():

    return render_template(
        "dashboard.html"
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    database_status = "error"

    try:

        db.session.execute(
            db.text("SELECT 1")
        )

        database_status = "connected"

        return jsonify(
            {
                "status": "ok",
                "database": database_status,
                "whatsapp": (
                    "configured"
                    if whatsapp_is_configured()
                    else "not configured"
                ),
            }
        ), 200

    except Exception as error:

        return jsonify(
            {
                "status": "error",
                "database": database_status,
                "whatsapp": (
                    "configured"
                    if whatsapp_is_configured()
                    else "not configured"
                ),
                "error": str(error),
            }
        ), 500


# ============================================================
# WHATSAPP WEBHOOK
# ============================================================

@app.route(
    "/webhook",
    methods=["GET", "POST"],
)
def webhook():

    # WhatsApp is optional.
    # If it is not configured, don't crash the app.

    if request.method == "GET":

        mode = request.args.get(
            "hub.mode"
        )

        verify_token = request.args.get(
            "hub.verify_token"
        )

        challenge = request.args.get(
            "hub.challenge"
        )

        if (
            mode == "subscribe"
            and WHATSAPP_VERIFY_TOKEN
            and verify_token
            == WHATSAPP_VERIFY_TOKEN
        ):

            return challenge, 200

        return jsonify(
            {
                "success": False,
                "error": "WhatsApp webhook not configured",
            }
        ), 403

    # POST

    if not whatsapp_is_configured():

        return jsonify(
            {
                "success": False,
                "message": "WhatsApp is not configured",
            }
        ), 200

    try:

        data = request.get_json(
            silent=True
        )

        print(
            "WhatsApp webhook:",
            data,
        )

        return jsonify(
            {
                "success": True
            }
        ), 200

    except Exception as error:

        print(
            "Webhook error:",
            error,
        )

        return jsonify(
            {
                "success": False,
                "error": str(error),
            }
        ), 500


# ============================================================
# STARTUP
# ============================================================

with app.app_context():

    initialize_database()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "5000",
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
