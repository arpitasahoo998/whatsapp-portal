import os
import json
import csv
import io
import requests
import pandas as pd

from datetime import datetime, timedelta

from dotenv import load_dotenv

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    send_from_directory,
    Response
)

from flask_login import (
    LoginManager,
    login_user,
    login_required,
    logout_user,
    current_user
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from werkzeug.utils import secure_filename

from models import (
    db,
    User,
    MessageRequest,
    Contact,
    WhatsAppInstance
)


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


def env(name, default=None):
    return os.getenv(name, default)


SECRET_KEY = env("SECRET_KEY")

DATABASE_URL = env("DATABASE_URL")

WHATSAPP_API_TOKEN = env(
    "WHATSAPP_API_TOKEN"
)

WHATSAPP_PHONE_NUMBER_ID = env(
    "WHATSAPP_PHONE_NUMBER_ID"
)

WHATSAPP_VERIFY_TOKEN = env(
    "WHATSAPP_VERIFY_TOKEN"
)

WHATSAPP_API_VERSION = env(
    "WHATSAPP_API_VERSION",
    "v23.0"
)

DEFAULT_ADMIN_USERNAME = env(
    "DEFAULT_ADMIN_USERNAME",
    "admin"
)

DEFAULT_ADMIN_PASSWORD = env(
    "DEFAULT_ADMIN_PASSWORD"
)

DEFAULT_CLIENT_PASSWORD = env(
    "DEFAULT_CLIENT_PASSWORD",
    "change-me"
)


# ============================================================
# DATABASE URL
# ============================================================

if DATABASE_URL:

    if DATABASE_URL.startswith("postgres://"):

        DATABASE_URL = DATABASE_URL.replace(
            "postgres://",
            "postgresql://",
            1
        )


# ============================================================
# APPLICATION
# ============================================================

app = Flask(__name__)

app.config["SECRET_KEY"] = (
    SECRET_KEY
    or "development-only-change-this"
)

app.config["SQLALCHEMY_DATABASE_URI"] = (
    DATABASE_URL
    or "sqlite:///whatsapp_portal.db"
)

app.config[
    "SQLALCHEMY_TRACK_MODIFICATIONS"
] = False

app.config["UPLOAD_FOLDER"] = "uploads"

app.config["MEDIA_FOLDER"] = os.path.join(
    "static",
    "media"
)

app.config["MAX_CONTENT_LENGTH"] = (
    100 * 1024 * 1024
)


# ============================================================
# DIRECTORIES
# ============================================================

os.makedirs(
    app.config["UPLOAD_FOLDER"],
    exist_ok=True
)

os.makedirs(
    app.config["MEDIA_FOLDER"],
    exist_ok=True
)


# ============================================================
# DATABASE
# ============================================================

db.init_app(app)


# ============================================================
# LOGIN
# ============================================================

login_manager = LoginManager()

login_manager.login_view = "login"

login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):

    return db.session.get(
        User,
        int(user_id)
    )


# ============================================================
# TIME
# ============================================================

def get_local_now():

    return datetime.utcnow() + timedelta(
        hours=5,
        minutes=30
    )


# ============================================================
# PHONE NUMBER
# ============================================================

def normalize_phone_number(phone):

    if not phone:
        return ""

    phone = str(phone).strip()

    phone = (
        phone
        .replace("+", "")
        .replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
    )

    return "".join(
        character
        for character in phone
        if character.isdigit()
    )


# ============================================================
# WHATSAPP CONFIGURATION
# ============================================================

def whatsapp_is_configured():

    return bool(
        WHATSAPP_API_TOKEN
        and WHATSAPP_PHONE_NUMBER_ID
    )


def whatsapp_config_error():

    missing = []

    if not WHATSAPP_API_TOKEN:
        missing.append(
            "WHATSAPP_API_TOKEN"
        )

    if not WHATSAPP_PHONE_NUMBER_ID:
        missing.append(
            "WHATSAPP_PHONE_NUMBER_ID"
        )

    return (
        "Missing WhatsApp configuration: "
        + ", ".join(missing)
    )


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

with app.app_context():

    db.create_all()

    # --------------------------------------------------------
    # ADMIN
    # --------------------------------------------------------

    if DEFAULT_ADMIN_PASSWORD:

        admin = User.query.filter_by(
            username=DEFAULT_ADMIN_USERNAME
        ).first()

        if not admin:

            admin = User(

                username=(
                    DEFAULT_ADMIN_USERNAME
                ),

                password=(
                    generate_password_hash(
                        DEFAULT_ADMIN_PASSWORD
                    )
                ),

                user_type="admin",

                credits=0
            )

            db.session.add(admin)

    # --------------------------------------------------------
    # DEFAULT CLIENT
    # --------------------------------------------------------

    client = User.query.filter_by(
        username="user1"
    ).first()

    if not client:

        client = User(

            username="user1",

            password=(
                generate_password_hash(
                    DEFAULT_CLIENT_PASSWORD
                )
            ),

            user_type="client",

            credits=0
        )

        db.session.add(client)

    db.session.commit()


# ============================================================
# WHATSAPP CLOUD API
# ============================================================

class WhatsAppService:

    @staticmethod
    def send_text_message(
        to_number,
        text
    ):

        if not whatsapp_is_configured():

            return {

                "success": False,

                "error":
                    whatsapp_config_error()
            }

        clean_number = (
            normalize_phone_number(
                to_number
            )
        )

        if not clean_number:

            return {

                "success": False,

                "error":
                    "Invalid phone number"
            }

        if not text:

            return {

                "success": False,

                "error":
                    "Message text is empty"
            }

        url = (
            "https://graph.facebook.com/"
            f"{WHATSAPP_API_VERSION}/"
            f"{WHATSAPP_PHONE_NUMBER_ID}"
            "/messages"
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

            "recipient_type":
                "individual",

            "to":
                clean_number,

            "type":
                "text",

            "text": {

                "preview_url":
                    False,

                "body":
                    text
            }
        }

        try:

            response = requests.post(

                url,

                headers=headers,

                json=payload,

                timeout=30
            )

            try:

                data = response.json()

            except ValueError:

                data = {
                    "raw": response.text
                }

            print(
                "WhatsApp response:",
                response.status_code
            )

            print(
                json.dumps(
                    data,
                    indent=2
                )
            )

            if response.ok:

                messages = (
                    data.get(
                        "messages",
                        []
                    )
                )

                message_id = None

                if messages:

                    message_id = (
                        messages[0].get(
                            "id"
                        )
                    )

                return {

                    "success": True,

                    "message_id":
                        message_id,

                    "response":
                        data
                }

            error = (
                data
                .get("error", {})
                .get(
                    "message"
                )
            )

            return {

                "success": False,

                "error":
                    error
                    or "WhatsApp API request failed",

                "response":
                    data
            }

        except requests.RequestException as error:

            return {

                "success": False,

                "error":
                    str(error)
            }


# ============================================================
# TEMPLATE MESSAGE
# ============================================================

class WhatsAppTemplateService:

    @staticmethod
    def send_template(
        to_number,
        template_name,
        language_code="en_US",
        parameters=None
    ):

        if not whatsapp_is_configured():

            return {

                "success": False,

                "error":
                    whatsapp_config_error()
            }

        clean_number = (
            normalize_phone_number(
                to_number
            )
        )

        components = []

        if parameters:

            body_parameters = []

            for value in parameters:

                body_parameters.append({

                    "type":
                        "text",

                    "text":
                        str(value)
                })

            components.append({

                "type":
                    "body",

                "parameters":
                    body_parameters
            })

        template = {

            "name":
                template_name,

            "language": {

                "code":
                    language_code
            }
        }

        if components:

            template["components"] = (
                components
            )

        payload = {

            "messaging_product":
                "whatsapp",

            "to":
                clean_number,

            "type":
                "template",

            "template":
                template
        }

        url = (
            "https://graph.facebook.com/"
            f"{WHATSAPP_API_VERSION}/"
            f"{WHATSAPP_PHONE_NUMBER_ID}"
            "/messages"
        )

        headers = {

            "Authorization":
                f"Bearer {WHATSAPP_API_TOKEN}",

            "Content-Type":
                "application/json"
        }

        try:

            response = requests.post(

                url,

                headers=headers,

                json=payload,

                timeout=30
            )

            data = response.json()

            if response.ok:

                messages = (
                    data.get(
                        "messages",
                        []
                    )
                )

                return {

                    "success": True,

                    "message_id":
                        (
                            messages[0].get("id")
                            if messages
                            else None
                        ),

                    "response":
                        data
                }

            return {

                "success": False,

                "error":
                    data.get(
                        "error",
                        {}
                    ).get(
                        "message",
                        "Template send failed"
                    ),

                "response":
                    data
            }

        except Exception as error:

            return {

                "success": False,

                "error":
                    str(error)
            }


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        user = User.query.filter_by(
            username=username
        ).first()

        if (
            user
            and check_password_hash(
                user.password,
                password
            )
        ):

            login_user(user)

            return redirect(
                url_for("dashboard")
            )

        flash(
            "Invalid username or password",
            "danger"
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
@login_required
def dashboard():

    if current_user.user_type == "admin":

        requests_list = (
            MessageRequest.query
            .order_by(
                MessageRequest.created_at.desc()
            )
            .all()
        )

        instances = (
            WhatsAppInstance.query.all()
        )

        return render_template(
            "admin/dashboard.html",
            requests=requests_list,
            instances=instances
        )

    requests_list = (
        MessageRequest.query
        .filter_by(
            user_id=current_user.id
        )
        .order_by(
            MessageRequest.created_at.desc()
        )
        .all()
    )

    return render_template(
        "client/dashboard.html",
        requests=requests_list
    )


# ============================================================
# SEND MESSAGE / CREATE CAMPAIGN
# ============================================================

@app.route(
    "/send-message",
    methods=["GET", "POST"]
)
@login_required
def send_message():

    if request.method == "GET":

        return render_template(
            "client/send_message.html"
        )

    message_text = request.form.get(
        "message_text",
        ""
    ).strip()

    manual_numbers = request.form.get(
        "manual_numbers",
        ""
    )

    numbers = []

    # --------------------------------------------------------
    # MANUAL NUMBERS
    # --------------------------------------------------------

    if manual_numbers:

        numbers.extend(

            manual_numbers
            .replace(",", "\n")
            .splitlines()
        )

    # --------------------------------------------------------
    # FILE
    # --------------------------------------------------------

    uploaded_file = request.files.get(
        "number_file"
    )

    if (
        uploaded_file
        and uploaded_file.filename
    ):

        filename = secure_filename(
            uploaded_file.filename
        )

        try:

            if filename.lower().endswith(
                ".csv"
            ):

                df = pd.read_csv(
                    uploaded_file
                )

            elif filename.lower().endswith(
                (
                    ".xlsx",
                    ".xls"
                )
            ):

                df = pd.read_excel(
                    uploaded_file
                )

            else:

                flash(
                    "Only CSV or Excel files are supported.",
                    "danger"
                )

                return redirect(
                    url_for("send_message")
                )

            if len(df.columns) == 0:

                raise ValueError(
                    "File has no columns"
                )

            numbers.extend(
                df.iloc[:, 0]
                .dropna()
                .astype(str)
                .tolist()
            )

        except Exception as error:

            flash(
                f"Could not read file: {error}",
                "danger"
            )

            return redirect(
                url_for("send_message")
            )

    # --------------------------------------------------------
    # NORMALIZE
    # --------------------------------------------------------

    normalized = []

    for number in numbers:

        number = (
            normalize_phone_number(
                number
            )
        )

        if number:

            normalized.append(
                number
            )

    numbers = list(
        dict.fromkeys(
            normalized
        )
    )

    if not numbers:

        flash(
            "Please provide at least one phone number.",
            "danger"
        )

        return redirect(
            url_for("send_message")
        )

    # --------------------------------------------------------
    # CREDIT CHECK
    # --------------------------------------------------------

    if (
        len(numbers)
        > current_user.credits
    ):

        flash(
            "Insufficient credits.",
            "danger"
        )

        return redirect(
            url_for("send_message")
        )

    # --------------------------------------------------------
    # CREATE CAMPAIGN
    # --------------------------------------------------------

    campaign = MessageRequest(

        user_id=current_user.id,

        message_text=message_text,

        status="Pending",

        report_ready_at=(
            get_local_now()
            + timedelta(hours=6)
        )
    )

    db.session.add(
        campaign
    )

    db.session.flush()

    for number in numbers:

        db.session.add(

            Contact(

                request_id=
                    campaign.id,

                phone_number=
                    number,

                status=
                    "Pending"
            )
        )

    current_user.credits -= len(
        numbers
    )

    db.session.commit()

    flash(
        "Campaign submitted for approval.",
        "success"
    )

    return redirect(
        url_for("dashboard")
    )


# ============================================================
# APPROVE + SEND
# ============================================================

@app.route(
    "/admin/approve/<int:request_id>",
    methods=["POST"]
)
@login_required
def approve_request(request_id):

    if current_user.user_type != "admin":

        return jsonify({
            "success": False,
            "error": "Unauthorized"
        }), 403

    if not whatsapp_is_configured():

        return jsonify({

            "success": False,

            "error":
                whatsapp_config_error()

        }), 500

    campaign = db.get_or_404(
        MessageRequest,
        request_id
    )

    if campaign.status == "Approved":

        return jsonify({

            "success": False,

            "error":
                "Campaign already approved"
        }), 400

    contacts = Contact.query.filter_by(
        request_id=request_id
    ).all()

    if not contacts:

        return jsonify({

            "success": False,

            "error":
                "No contacts found"
        }), 400

    campaign.status = "Approved"

    campaign.approved_at = (
        get_local_now()
    )

    sent = 0

    failed = 0

    for contact in contacts:

        result = (
            WhatsAppService.send_text_message(

                contact.phone_number,

                campaign.message_text
            )
        )

        if result["success"]:

            contact.status = "Sent"

            contact.sent_at = (
                get_local_now()
            )

            contact.whatsapp_message_id = (
                result.get(
                    "message_id"
                )
            )

            contact.error_message = None

            sent += 1

        else:

            contact.status = "Failed"

            contact.sent_at = (
                get_local_now()
            )

            contact.error_message = (
                result.get(
                    "error"
                )
            )

            failed += 1

        db.session.commit()

    return jsonify({

        "success": True,

        "sent": sent,

        "failed": failed,

        "total": len(contacts)
    })


# ============================================================
# WEBHOOK VERIFY
# ============================================================

@app.route(
    "/webhook/whatsapp",
    methods=["GET"]
)
def verify_whatsapp_webhook():

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
        and token
        and token == WHATSAPP_VERIFY_TOKEN
    ):

        return challenge, 200

    return (
        "Verification failed",
        403
    )


# ============================================================
# WEBHOOK STATUS
# ============================================================

@app.route(
    "/webhook/whatsapp",
    methods=["POST"]
)
def whatsapp_webhook():

    try:

        data = request.get_json(
            silent=True
        )

        if not data:

            return jsonify({
                "success": False
            }), 400

        print(
            json.dumps(
                data,
                indent=2
            )
        )

        if (
            data.get("object")
            != "whatsapp_business_account"
        ):

            return jsonify({
                "success": False
            }), 400

        for entry in data.get(
            "entry",
            []
        ):

            for change in entry.get(
                "changes",
                []
            ):

                value = change.get(
                    "value",
                    {}
                )

                statuses = value.get(
                    "statuses",
                    []
                )

                for status_data in statuses:

                    message_id = (
                        status_data.get(
                            "id"
                        )
                    )

                    status = (
                        status_data.get(
                            "status"
                        )
                    )

                    if not message_id:

                        continue

                    contact = (
                        Contact.query
                        .filter_by(
                            whatsapp_message_id=
                                message_id
                        )
                        .first()
                    )

                    if not contact:

                        print(
                            "Unknown WhatsApp message:",
                            message_id
                        )

                        continue

                    status_map = {

                        "sent":
                            "Sent",

                        "delivered":
                            "Delivered",

                        "read":
                            "Read",

                        "failed":
                            "Failed"
                    }

                    new_status = (
                        status_map.get(
                            status
                        )
                    )

                    if not new_status:

                        continue

                    contact.status = (
                        new_status
                    )

                    if status == "failed":

                        errors = (
                            status_data.get(
                                "errors",
                                []
                            )
                        )

                        if errors:

                            contact.error_message = (
                                errors[0].get(
                                    "message"
                                )
                                or errors[0].get(
                                    "title"
                                )
                                or "WhatsApp message failed"
                            )

                        else:

                            contact.error_message = (
                                "WhatsApp message failed"
                            )

                    else:

                        contact.error_message = None

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

@app.route("/health")
def health():

    database_status = "error"

    try:

        db.session.execute(
            db.text("SELECT 1")
        )

        database_status = "connected"

    except Exception as error:

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
                str(error)

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

    })


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
