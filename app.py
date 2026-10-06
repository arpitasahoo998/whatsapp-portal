import os
import csv
import io
import json
from datetime import datetime, timedelta
from functools import wraps

import pandas as pd
import requests

from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    redirect,
    url_for,
    session,
    flash,
)

from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)

from sqlalchemy import text


# ============================================================
# APPLICATION
# ============================================================

app = Flask(__name__)


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

SECRET_KEY = os.getenv("SECRET_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD")

# WhatsApp is OPTIONAL
WHATSAPP_API_TOKEN = os.getenv("WHATSAPP_API_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv(
    "WHATSAPP_PHONE_NUMBER_ID"
)
WHATSAPP_VERIFY_TOKEN = os.getenv(
    "WHATSAPP_VERIFY_TOKEN"
)

WHATSAPP_API_VERSION = os.getenv(
    "WHATSAPP_API_VERSION",
    "v23.0"
)


# ============================================================
# REQUIRED CONFIGURATION
# ============================================================

missing_variables = []

if not SECRET_KEY:
    missing_variables.append("SECRET_KEY")

if not DATABASE_URL:
    missing_variables.append("DATABASE_URL")

if not DEFAULT_ADMIN_PASSWORD:
    missing_variables.append(
        "DEFAULT_ADMIN_PASSWORD"
    )

if missing_variables:

    raise RuntimeError(
        "Missing environment variables: "
        + ", ".join(missing_variables)
    )


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

# PostgreSQL compatibility
if DATABASE_URL.startswith("postgres://"):

    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql://",
        1
    )


app.config["SECRET_KEY"] = SECRET_KEY

app.config[
    "SQLALCHEMY_DATABASE_URI"
] = DATABASE_URL

app.config[
    "SQLALCHEMY_TRACK_MODIFICATIONS"
] = False

app.config[
    "SQLALCHEMY_ENGINE_OPTIONS"
] = {
    "pool_pre_ping": True,
}


# ============================================================
# UPLOAD CONFIGURATION
# ============================================================

UPLOAD_FOLDER = os.getenv(
    "UPLOAD_FOLDER",
    "uploads"
)

app.config[
    "UPLOAD_FOLDER"
] = UPLOAD_FOLDER

app.config[
    "MAX_CONTENT_LENGTH"
] = 100 * 1024 * 1024


os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


# ============================================================
# EXTENSIONS
# ============================================================

db = SQLAlchemy(app)

login_manager = LoginManager()

login_manager.init_app(app)

login_manager.login_view = "login"


# ============================================================
# TIME
# ============================================================

def get_local_now():

    return datetime.utcnow() + timedelta(
        hours=5,
        minutes=30
    )


# ============================================================
# MODELS
# ============================================================

class User(
    db.Model,
    UserMixin
):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    username = db.Column(
        db.String(150),
        unique=True,
        nullable=False
    )

    password = db.Column(
        db.String(255),
        nullable=False
    )

    user_type = db.Column(
        db.String(20),
        nullable=False,
        default="client"
    )

    credits = db.Column(
        db.Integer,
        nullable=False,
        default=0
    )


class MessageRequest(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    user = db.relationship(
        "User",
        backref="requests"
    )

    message_text = db.Column(
        db.Text,
        nullable=False
    )

    status = db.Column(
        db.String(20),
        default="Pending"
    )

    image1 = db.Column(
        db.String(255)
    )

    image2 = db.Column(
        db.String(255)
    )

    image3 = db.Column(
        db.String(255)
    )

    image4 = db.Column(
        db.String(255)
    )

    pdf_file = db.Column(
        db.String(255)
    )

    video_file = db.Column(
        db.String(255)
    )

    created_at = db.Column(
        db.DateTime,
        default=get_local_now
    )

    approved_at = db.Column(
        db.DateTime
    )

    report_ready_at = db.Column(
        db.DateTime
    )

    contacts = db.relationship(
        "Contact",
        backref="request",
        lazy=True,
        cascade="all, delete-orphan"
    )


class Contact(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    request_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "message_request.id"
        ),
        nullable=False
    )

    phone_number = db.Column(
        db.String(20),
        nullable=False
    )

    status = db.Column(
        db.String(20),
        default="Pending"
    )

    sent_at = db.Column(
        db.DateTime
    )

    error_message = db.Column(
        db.String(500)
    )

    is_csv_matched = db.Column(
        db.Boolean,
        default=False
    )

    whatsapp_message_id = db.Column(
        db.String(255),
        unique=True,
        nullable=True,
        index=True
    )


class WhatsAppInstance(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(50)
    )

    phone_number = db.Column(
        db.String(20),
        unique=True
    )

    status = db.Column(
        db.String(20),
        default="Active"
    )

    last_used = db.Column(
        db.DateTime,
        default=get_local_now
    )


# ============================================================
# LOGIN
# ============================================================

@login_manager.user_loader
def load_user(user_id):

    try:

        return db.session.get(
            User,
            int(user_id)
        )

    except Exception:

        return None


# ============================================================
# HELPERS
# ============================================================

def whatsapp_is_configured():

    return bool(
        WHATSAPP_API_TOKEN
        and WHATSAPP_PHONE_NUMBER_ID
    )


def admin_required(function):

    @wraps(function)
    @login_required
    def decorated(*args, **kwargs):

        if current_user.user_type != "admin":

            return jsonify({
                "success": False,
                "error": "Admin access required"
            }), 403

        return function(*args, **kwargs)

    return decorated


def save_uploaded_file(file):

    if not file:

        return None

    if not file.filename:

        return None

    filename = file.filename

    timestamp = datetime.now().strftime(
        "%Y%m%d%H%M%S%f"
    )

    safe_filename = (
        f"{timestamp}_{filename}"
    )

    filepath = os.path.join(
        app.config["UPLOAD_FOLDER"],
        safe_filename
    )

    file.save(filepath)

    return safe_filename


# ============================================================
# WHATSAPP
# ============================================================

def send_whatsapp_message(
    phone_number,
    message_text
):

    if not whatsapp_is_configured():

        return {
            "success": False,
            "configured": False,
            "error":
                "WhatsApp API is not configured"
        }

    url = (
        "https://graph.facebook.com/"
        f"{WHATSAPP_API_VERSION}/"
        f"{WHATSAPP_PHONE_NUMBER_ID}/messages"
    )

    headers = {

        "Authorization":
            f"Bearer {WHATSAPP_API_TOKEN}",

        "Content-Type":
            "application/json"
    }

    payload = {

        "messaging_product":
            "whatsapp",

        "to":
            phone_number,

        "type":
            "text",

        "text": {

            "body":
                message_text
        }
    }

    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30
        )

        response_data = {}

        try:

            response_data = response.json()

        except Exception:

            response_data = {
                "raw":
                    response.text
            }

        if response.ok:

            return {

                "success": True,

                "configured": True,

                "data":
                    response_data
            }

        return {

            "success": False,

            "configured": True,

            "error":
                response_data
        }

    except Exception as error:

        return {

            "success": False,

            "configured": True,

            "error":
                str(error)
        }


# ============================================================
# HOME
# ============================================================

@app.route("/")
def index():

    if current_user.is_authenticated:

        if current_user.user_type == "admin":

            return redirect(
                url_for("admin_dashboard")
            )

        return redirect(
            url_for("dashboard")
        )

    return redirect(
        url_for("login")
    )


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        username = (
            request.form.get(
                "username"
            )
            or ""
        ).strip()

        password = (
            request.form.get(
                "password"
            )
            or ""
        )

        user = User.query.filter_by(
            username=username
        ).first()

        if user and check_password_hash(
            user.password,
            password
        ):

            login_user(user)

            if user.user_type == "admin":

                return redirect(
                    url_for(
                        "admin_dashboard"
                    )
                )

            return redirect(
                url_for(
                    "dashboard"
                )
            )

        flash(
            "Invalid username or password",
            "error"
        )

    try:

        return render_template(
            "login.html"
        )

    except Exception:

        return """
        <html>
        <head>
            <title>WhatsApp Portal Login</title>
        </head>
        <body>
            <h2>WhatsApp Portal</h2>

            <form method="POST">

                <input
                    name="username"
                    placeholder="Username"
                    required
                >

                <br><br>

                <input
                    type="password"
                    name="password"
                    placeholder="Password"
                    required
                >

                <br><br>

                <button type="submit">
                    Login
                </button>

            </form>
        </body>
        </html>
        """


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
# CLIENT DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    requests_list = MessageRequest.query.filter_by(
        user_id=current_user.id
    ).order_by(
        MessageRequest.id.desc()
    ).all()

    try:

        return render_template(
            "dashboard.html",
            requests=requests_list
        )

    except Exception:

        return jsonify({

            "success": True,

            "user": current_user.username,

            "requests": [

                {
                    "id": item.id,

                    "message":
                        item.message_text,

                    "status":
                        item.status,

                    "created_at":
                        str(item.created_at)
                }

                for item in requests_list
            ]
        })


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    requests_list = MessageRequest.query.order_by(
        MessageRequest.id.desc()
    ).all()

    users = User.query.order_by(
        User.id.desc()
    ).all()

    try:

        return render_template(
            "admin.html",
            requests=requests_list,
            users=users
        )

    except Exception:

        return jsonify({

            "success": True,

            "users": len(users),

            "requests": len(
                requests_list
            ),

            "whatsapp":
                whatsapp_is_configured()
        })


# ============================================================
# CREATE REQUEST
# ============================================================

@app.route(
    "/api/requests",
    methods=["POST"]
)
@login_required
def create_request():

    try:

        message_text = (
            request.form.get(
                "message_text"
            )
            or request.json.get(
                "message_text"
            )
            if request.is_json
            else request.form.get(
                "message_text"
            )
        )

        if not message_text:

            return jsonify({

                "success": False,

                "error":
                    "message_text is required"

            }), 400

        new_request = MessageRequest(

            user_id=current_user.id,

            message_text=message_text,

            status="Pending"
        )

        new_request.image1 = (
            save_uploaded_file(
                request.files.get("image1")
            )
        )

        new_request.image2 = (
            save_uploaded_file(
                request.files.get("image2")
            )
        )

        new_request.image3 = (
            save_uploaded_file(
                request.files.get("image3")
            )
        )

        new_request.image4 = (
            save_uploaded_file(
                request.files.get("image4")
            )
        )

        new_request.pdf_file = (
            save_uploaded_file(
                request.files.get("pdf_file")
            )
        )

        new_request.video_file = (
            save_uploaded_file(
                request.files.get("video_file")
            )
        )

        db.session.add(
            new_request
        )

        db.session.commit()

        return jsonify({

            "success": True,

            "request_id":
                new_request.id,

            "status":
                new_request.status

        }), 201

    except Exception as error:

        db.session.rollback()

        return jsonify({

            "success": False,

            "error":
                str(error)

        }), 500


# ============================================================
# GET REQUESTS
# ============================================================

@app.route(
    "/api/requests",
    methods=["GET"]
)
@login_required
def get_requests():

    if current_user.user_type == "admin":

        requests_list = MessageRequest.query.order_by(
            MessageRequest.id.desc()
        ).all()

    else:

        requests_list = MessageRequest.query.filter_by(
            user_id=current_user.id
        ).order_by(
            MessageRequest.id.desc()
        ).all()

    return jsonify({

        "success": True,

        "requests": [

            {

                "id":
                    item.id,

                "user_id":
                    item.user_id,

                "username":
                    item.user.username,

                "message_text":
                    item.message_text,

                "status":
                    item.status,

                "created_at":
                    str(item.created_at),

                "approved_at":
                    str(item.approved_at)
                    if item.approved_at
                    else None,

                "report_ready_at":
                    str(item.report_ready_at)
                    if item.report_ready_at
                    else None,

                "contacts":
                    len(item.contacts)

            }

            for item in requests_list
        ]

    })


# ============================================================
# GET SINGLE REQUEST
# ============================================================

@app.route(
    "/api/requests/<int:request_id>",
    methods=["GET"]
)
@login_required
def get_request(request_id):

    item = db.session.get(
        MessageRequest,
        request_id
    )

    if not item:

        return jsonify({

            "success": False,

            "error":
                "Request not found"

        }), 404

    if (
        current_user.user_type != "admin"
        and item.user_id != current_user.id
    ):

        return jsonify({

            "success": False,

            "error":
                "Access denied"

        }), 403

    return jsonify({

        "success": True,

        "request": {

            "id":
                item.id,

            "message_text":
                item.message_text,

            "status":
                item.status,

            "created_at":
                str(item.created_at),

            "contacts": [

                {

                    "id":
                        contact.id,

                    "phone_number":
                        contact.phone_number,

                    "status":
                        contact.status,

                    "sent_at":
                        str(contact.sent_at)
                        if contact.sent_at
                        else None,

                    "error_message":
                        contact.error_message,

                    "whatsapp_message_id":
                        contact.whatsapp_message_id

                }

                for contact in item.contacts
            ]

        }

    })


# ============================================================
# ADD CONTACT
# ============================================================

@app.route(
    "/api/requests/<int:request_id>/contacts",
    methods=["POST"]
)
@login_required
def add_contact(request_id):

    item = db.session.get(
        MessageRequest,
        request_id
    )

    if not item:

        return jsonify({

            "success": False,

            "error":
                "Request not found"

        }), 404

    if (
        current_user.user_type != "admin"
        and item.user_id != current_user.id
    ):

        return jsonify({

            "success": False,

            "error":
                "Access denied"

        }), 403

    data = request.get_json(
        silent=True
    ) or {}

    phone_number = (
        data.get(
            "phone_number"
        )
        or ""
    ).strip()

    if not phone_number:

        return jsonify({

            "success": False,

            "error":
                "phone_number is required"

        }), 400

    contact = Contact(

        request_id=request_id,

        phone_number=phone_number,

        status="Pending"
    )

    db.session.add(contact)

    db.session.commit()

    return jsonify({

        "success": True,

        "contact_id":
            contact.id

    }), 201


# ============================================================
# UPLOAD CSV CONTACTS
# ============================================================

@app.route(
    "/api/requests/<int:request_id>/contacts/csv",
    methods=["POST"]
)
@login_required
def upload_contacts_csv(request_id):

    item = db.session.get(
        MessageRequest,
        request_id
    )

    if not item:

        return jsonify({

            "success": False,

            "error":
                "Request not found"

        }), 404

    if (
        current_user.user_type != "admin"
        and item.user_id != current_user.id
    ):

        return jsonify({

            "success": False,

            "error":
                "Access denied"

        }), 403

    file = request.files.get(
        "file"
    )

    if not file:

        return jsonify({

            "success": False,

            "error":
                "CSV file is required"

        }), 400

    try:

        content = file.read().decode(
            "utf-8-sig"
        )

        reader = csv.DictReader(
            io.StringIO(content)
        )

        count = 0

        for row in reader:

            phone = (
                row.get("phone_number")
                or row.get("phone")
                or row.get("mobile")
                or row.get("mobile_number")
            )

            if not phone:

                continue

            phone = str(
                phone
            ).strip()

            if not phone:

                continue

            contact = Contact(

                request_id=request_id,

                phone_number=phone,

                status="Pending",

                is_csv_matched=True
            )

            db.session.add(
                contact
            )

            count += 1

        db.session.commit()

        return jsonify({

            "success": True,

            "imported":
                count

        })

    except Exception as error:

        db.session.rollback()

        return jsonify({

            "success": False,

            "error":
                str(error)

        }), 500


# ============================================================
# APPROVE REQUEST
# ============================================================

@app.route(
    "/api/requests/<int:request_id>/approve",
    methods=["POST"]
)
@admin_required
def approve_request(request_id):

    item = db.session.get(
        MessageRequest,
        request_id
    )

    if not item:

        return jsonify({

            "success": False,

            "error":
                "Request not found"

        }), 404

    item.status = "Approved"

    item.approved_at = (
        get_local_now()
    )

    db.session.commit()

    return jsonify({

        "success": True,

        "status":
            item.status

    })


# ============================================================
# SEND REQUEST
# ============================================================

@app.route(
    "/api/requests/<int:request_id>/send",
    methods=["POST"]
)
@login_required
def send_request(request_id):

    item = db.session.get(
        MessageRequest,
        request_id
    )

    if not item:

        return jsonify({

            "success": False,

            "error":
                "Request not found"

        }), 404

    if (
        current_user.user_type != "admin"
        and item.user_id != current_user.id
    ):

        return jsonify({

            "success": False,

            "error":
                "Access denied"

        }), 403

    contacts = item.contacts

    if not contacts:

        return jsonify({

            "success": False,

            "error":
                "No contacts found"

        }), 400

    sent = 0
    failed = 0

    for contact in contacts:

        if not whatsapp_is_configured():

            contact.status = "Pending"

            contact.error_message = (
                "WhatsApp API is not configured"
            )

            continue

        result = send_whatsapp_message(

            contact.phone_number,

            item.message_text
        )

        if result.get("success"):

            contact.status = "Sent"

            contact.sent_at = (
                get_local_now()
            )

            contact.error_message = None

            data = result.get(
                "data",
                {}
            )

            messages = data.get(
                "messages",
                []
            )

            if messages:

                contact.whatsapp_message_id = (
                    messages[0].get("id")
                )

            sent += 1

        else:

            contact.status = "Failed"

            contact.error_message = str(
                result.get("error")
            )

            failed += 1

    if sent > 0:

        item.status = "Sent"

    elif not whatsapp_is_configured():

        item.status = "Pending"

    else:

        item.status = "Failed"

    db.session.commit()

    return jsonify({

        "success": True,

        "whatsapp_configured":
            whatsapp_is_configured(),

        "sent":
            sent,

        "failed":
            failed,

        "status":
            item.status

    })


# ============================================================
# WHATSAPP STATUS
# ============================================================

@app.route(
    "/api/whatsapp/status"
)
def whatsapp_status():

    return jsonify({

        "success": True,

        "configured":
            whatsapp_is_configured(),

        "phone_number_id":
            bool(
                WHATSAPP_PHONE_NUMBER_ID
            ),

        "api_token":
            bool(
                WHATSAPP_API_TOKEN
            ),

        "verify_token":
            bool(
                WHATSAPP_VERIFY_TOKEN
            ),

        "api_version":
            WHATSAPP_API_VERSION

    })


# ============================================================
# WHATSAPP WEBHOOK VERIFICATION
# ============================================================

@app.route(
    "/webhook",
    methods=["GET"]
)
def whatsapp_webhook_verify():

    if not WHATSAPP_VERIFY_TOKEN:

        return jsonify({

            "success": False,

            "error":
                "WhatsApp webhook is not configured"

        }), 503

    mode = request.args.get(
        "hub.mode"
    )

    token = request.args.get(
        "hub.verify_token"
    )

    challenge = request.args.get(
        "hub.challenge"
    )

    if (
        mode == "subscribe"
        and token == WHATSAPP_VERIFY_TOKEN
    ):

        return challenge or "", 200

    return "Verification token mismatch", 403


# ============================================================
# WHATSAPP WEBHOOK
# ============================================================

@app.route(
    "/webhook",
    methods=["POST"]
)
def whatsapp_webhook():

    if not whatsapp_is_configured():

        return jsonify({

            "success": False,

            "error":
                "WhatsApp API is not configured"

        }), 503

    try:

        payload = request.get_json(
            silent=True
        ) or {}

        print(
            "WhatsApp webhook:",
            json.dumps(
                payload
            )
        )

        entries = payload.get(
            "entry",
            []
        )

        for entry in entries:

            changes = entry.get(
                "changes",
                []
            )

            for change in changes:

                value = change.get(
                    "value",
                    {}
                )

                messages = value.get(
                    "messages",
                    []
                )

                for message in messages:

                    message_id = message.get(
                        "id"
                    )

                    sender = message.get(
                        "from"
                    )

                    if not message_id:

                        continue

                    contact = Contact.query.filter_by(
                        whatsapp_message_id=
                            message_id
                    ).first()

                    if contact:

                        contact.status = "Delivered"

                        db.session.commit()

        return jsonify({
            "success": True
        }), 200

    except Exception as error:

        print(
            "Webhook error:",
            error
        )

        db.session.rollback()

        return jsonify({

            "success": False,

            "error":
                str(error)

        }), 500


# ============================================================
# HEALTH
# ============================================================

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    database_status = "error"

    database_error = None

    try:

        db.session.execute(
            text("SELECT 1")
        )

        database_status = "connected"

    except Exception as error:

        database_error = str(
            error
        )

    if database_status != "connected":

        return jsonify({

            "status":
                "error",

            "database":
                database_status,

            "whatsapp":
                (
                    "configured"
                    if whatsapp_is_configured()
                    else "not configured"
                ),

            "error":
                database_error

        }), 500

    return jsonify({

        "status":
            "ok",

        "database":
            database_status,

        "whatsapp":
            (
                "configured"
                if whatsapp_is_configured()
                else "not configured"
            )

    }), 200


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def initialize_database():

    with app.app_context():

        db.create_all()

        admin = User.query.filter_by(
            username="admin"
        ).first()

        if not admin:

            admin = User(

                username="admin",

                password=
                    generate_password_hash(
                        DEFAULT_ADMIN_PASSWORD
                    ),

                user_type="admin",

                credits=0
            )

            db.session.add(
                admin
            )

        db.session.commit()


# ============================================================
# STARTUP
# ============================================================

try:

    initialize_database()

    print(
        "Database initialized successfully."
    )

except Exception as error:

    print(
        "Database initialization failed:",
        error
    )


print(
    "Application configuration loaded."
)

print(
    "PostgreSQL:",
    "configured"
    if DATABASE_URL
    else "not configured"
)

print(
    "WhatsApp:",
    "configured"
    if whatsapp_is_configured()
    else "not configured"
)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "5000"
        )
    )

    app.run(

        host="0.0.0.0",

        port=port,

        debug=False
    )
