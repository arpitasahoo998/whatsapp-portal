import os
import json
import csv
import io
import random

import pandas as pd
import requests

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
# LOAD ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# REQUIRED ENVIRONMENT VARIABLES
# ============================================================

SECRET_KEY = os.getenv("SECRET_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

WHATSAPP_API_TOKEN = os.getenv(
    "WHATSAPP_API_TOKEN"
)

WHATSAPP_PHONE_NUMBER_ID = os.getenv(
    "WHATSAPP_PHONE_NUMBER_ID"
)

WHATSAPP_VERIFY_TOKEN = os.getenv(
    "WHATSAPP_VERIFY_TOKEN"
)

WHATSAPP_VERSION = os.getenv(
    "WHATSAPP_API_VERSION",
    "v23.0"
)

DEFAULT_ADMIN_USERNAME = os.getenv(
    "DEFAULT_ADMIN_USERNAME",
    "admin"
)

DEFAULT_ADMIN_PASSWORD = os.getenv(
    "DEFAULT_ADMIN_PASSWORD"
)


# ============================================================
# VALIDATE ENVIRONMENT
# ============================================================

missing_variables = []

if not SECRET_KEY:
    missing_variables.append("SECRET_KEY")

if not DATABASE_URL:
    missing_variables.append("DATABASE_URL")

if not WHATSAPP_API_TOKEN:
    missing_variables.append("WHATSAPP_API_TOKEN")

if not WHATSAPP_PHONE_NUMBER_ID:
    missing_variables.append(
        "WHATSAPP_PHONE_NUMBER_ID"
    )

if not WHATSAPP_VERIFY_TOKEN:
    missing_variables.append(
        "WHATSAPP_VERIFY_TOKEN"
    )

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
# DATABASE URL NORMALIZATION
# ============================================================

if DATABASE_URL.startswith("postgres://"):

    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql://",
        1
    )


# ============================================================
# FLASK APPLICATION
# ============================================================

app = Flask(__name__)

app.config["SECRET_KEY"] = SECRET_KEY

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

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
# LOGIN MANAGER
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
# DATE / TIME
# ============================================================

def get_local_now():

    return datetime.utcnow() + timedelta(
        hours=5,
        minutes=30
    )


# ============================================================
# PHONE NUMBER NORMALIZATION
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
# DATABASE INITIALIZATION
# ============================================================

with app.app_context():

    db.create_all()

    # --------------------------------------------------------
    # Create admin if it does not exist
    # --------------------------------------------------------

    admin = User.query.filter_by(
        username=DEFAULT_ADMIN_USERNAME
    ).first()

    if not admin:

        admin = User(
            username=DEFAULT_ADMIN_USERNAME,
            password=generate_password_hash(
                DEFAULT_ADMIN_PASSWORD
            ),
            user_type="admin"
        )

        db.session.add(admin)

    # --------------------------------------------------------
    # Create default client
    # --------------------------------------------------------

    client = User.query.filter_by(
        username="user1"
    ).first()

    if not client:

        client = User(
            username="user1",
            password=generate_password_hash(
                os.getenv(
                    "DEFAULT_CLIENT_PASSWORD",
                    "change-me"
                )
            ),
            user_type="client",
            credits=0
        )

        db.session.add(client)

    # --------------------------------------------------------
    # Create demo WhatsApp instances ONLY if none exist
    #
    # IMPORTANT:
    # These are portal records.
    # They are NOT separate Meta WhatsApp numbers.
    # --------------------------------------------------------

    if WhatsAppInstance.query.count() == 0:

        for i in range(1, 4):

            instance = WhatsAppInstance(
                name=f"Instance {i}",
                phone_number="",
                status="Active"
            )

            db.session.add(instance)

    db.session.commit()


# ============================================================
# WHATSAPP CLOUD API SERVICE
# ============================================================

class WhatsAppService:

    @staticmethod
    def send_text_message(
        to_number,
        text
    ):
        """
        Send a real text message using
        Meta WhatsApp Cloud API.
        """

        clean_number = normalize_phone_number(
            to_number
        )

        if not clean_number:

            return {
                "success": False,
                "error": "Invalid recipient phone number"
            }

        if not text:

            return {
                "success": False,
                "error": "Message text is empty"
            }

        url = (
            "https://graph.facebook.com/"
            f"{WHATSAPP_VERSION}/"
            f"{WHATSAPP_PHONE_NUMBER_ID}"
            "/messages"
        )

        headers = {
            "Authorization": (
                f"Bearer {WHATSAPP_API_TOKEN}"
            ),
            "Content-Type": "application/json"
        }

        payload = {

            "messaging_product": "whatsapp",

            "recipient_type": "individual",

            "to": clean_number,

            "type": "text",

            "text": {

                "preview_url": False,

                "body": text
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

                response_data = response.json()

            except ValueError:

                response_data = {
                    "raw_response": response.text
                }

            print(
                "WhatsApp API:",
                response.status_code,
                json.dumps(
                    response_data,
                    indent=2
                )
            )

            if response.ok:

                messages = (
                    response_data
                    .get("messages", [])
                )

                message_id = None

                if messages:

                    message_id = messages[0].get(
                        "id"
                    )

                return {

                    "success": True,

                    "message_id": message_id,

                    "response": response_data
                }

            error_data = (
                response_data
                .get("error", {})
            )

            error_message = (
                error_data.get("message")
                or response_data.get(
                    "raw_response"
                )
                or (
                    "WhatsApp API returned "
                    f"HTTP {response.status_code}"
                )
            )

            return {

                "success": False,

                "error": error_message,

                "response": response_data
            }

        except requests.RequestException as error:

            print(
                "WhatsApp connection error:",
                str(error)
            )

            return {

                "success": False,

                "error": str(error)
            }

        except Exception as error:

            print(
                "WhatsApp unexpected error:",
                str(error)
            )

            return {

                "success": False,

                "error": str(error)
            }


# ============================================================
# WHATSAPP TEMPLATE MESSAGE
# ============================================================

class WhatsAppTemplateService:

    @staticmethod
    def send_template(
        to_number,
        template_name,
        language_code="en_US",
        parameters=None
    ):
        """
        Send an approved WhatsApp template.

        parameters should be a list such as:

        [
            "Arpita",
            "12345"
        ]
        """

        clean_number = normalize_phone_number(
            to_number
        )

        if not clean_number:

            return {
                "success": False,
                "error": "Invalid recipient phone number"
            }

        components = []

        if parameters:

            parameters_data = []

            for value in parameters:

                parameters_data.append({

                    "type": "text",

                    "text": str(value)
                })

            components.append({

                "type": "body",

                "parameters": parameters_data
            })

        url = (
            "https://graph.facebook.com/"
            f"{WHATSAPP_VERSION}/"
            f"{WHATSAPP_PHONE_NUMBER_ID}"
            "/messages"
        )

        headers = {

            "Authorization": (
                f"Bearer {WHATSAPP_API_TOKEN}"
            ),

            "Content-Type": "application/json"
        }

        template_data = {

            "name": template_name,

            "language": {

                "code": language_code
            }
        }

        if components:

            template_data["components"] = (
                components
            )

        payload = {

            "messaging_product": "whatsapp",

            "to": clean_number,

            "type": "template",

            "template": template_data
        }

        try:

            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=30
            )

            response_data = response.json()

            print(
                "WhatsApp template API:",
                response.status_code,
                json.dumps(
                    response_data,
                    indent=2
                )
            )

            if response.ok:

                messages = (
                    response_data
                    .get("messages", [])
                )

                message_id = None

                if messages:

                    message_id = messages[0].get(
                        "id"
                    )

                return {

                    "success": True,

                    "message_id": message_id,

                    "response": response_data
                }

            error_data = (
                response_data
                .get("error", {})
            )

            return {

                "success": False,

                "error": error_data.get(
                    "message",
                    "Template message failed"
                ),

                "response": response_data
            }

        except Exception as error:

            return {

                "success": False,

                "error": str(error)
            }


# ============================================================
# FILE VALIDATION
# ============================================================

def allowed_file(
    filename,
    extensions
):

    return (
        "."
        in filename
        and filename.rsplit(
            ".",
            1
        )[1].lower()
        in extensions
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
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        username = request.form.get(
            "username"
        )

        password = request.form.get(
            "password"
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
            "Invalid credentials",
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
# CREATE MESSAGE REQUEST
# ============================================================

@app.route(
    "/send-message",
    methods=["GET", "POST"]
)
@login_required
def send_message():

    if request.method == "POST":

        message_text = request.form.get(
            "message_text"
        )

        numbers_raw = request.form.get(
            "manual_numbers"
        )

        file = request.files.get(
            "number_file"
        )

        phone_numbers = []

        # ----------------------------------------------------
        # Read CSV / Excel
        # ----------------------------------------------------

        if file and file.filename != "":

            filename = secure_filename(
                file.filename
            )

            filepath = os.path.join(
                app.config["UPLOAD_FOLDER"],
                filename
            )

            file.save(filepath)

            try:

                if filename.lower().endswith(
                    ".csv"
                ):

                    df = pd.read_csv(
                        filepath
                    )

                else:

                    df = pd.read_excel(
                        filepath
                    )

                phone_numbers = (
                    df.iloc[:, 0]
                    .astype(str)
                    .tolist()
                )

            except Exception as error:

                flash(
                    f"Error reading file: {error}",
                    "danger"
                )

                return redirect(
                    url_for("send_message")
                )

            finally:

                if os.path.exists(
                    filepath
                ):

                    os.remove(
                        filepath
                    )

        # ----------------------------------------------------
        # Manual numbers
        # ----------------------------------------------------

        if numbers_raw:

            manual_numbers = [

                number.strip()

                for number in (
                    numbers_raw
                    .replace(",", "\n")
                    .split("\n")
                )

                if number.strip()
            ]

            phone_numbers.extend(
                manual_numbers
            )

        # ----------------------------------------------------
        # Validate
        # ----------------------------------------------------

        phone_numbers = [

            normalize_phone_number(number)

            for number in phone_numbers

            if normalize_phone_number(number)
        ]

        phone_numbers = list(
            dict.fromkeys(
                phone_numbers
            )
        )

        if not phone_numbers:

            flash(
                "No phone numbers provided",
                "warning"
            )

            return redirect(
                url_for("send_message")
            )

        required_credits = len(
            phone_numbers
        )

        if (
            required_credits
            > current_user.credits
        ):

            flash(
                "Insufficient credits. "
                f"This campaign requires "
                f"{required_credits} credits, "
                f"but you only have "
                f"{current_user.credits}.",
                "danger"
            )

            return redirect(
                url_for("send_message")
            )

        # ----------------------------------------------------
        # Media
        # ----------------------------------------------------

        media_files = {

            "image1":
                request.files.get("image1"),

            "image2":
                request.files.get("image2"),

            "image3":
                request.files.get("image3"),

            "image4":
                request.files.get("image4"),

            "pdf_file":
                request.files.get("pdf_file"),

            "video_file":
                request.files.get("video_file")
        }

        saved_paths = {}

        for key, media_file in (
            media_files.items()
        ):

            if (
                media_file
                and media_file.filename != ""
            ):

                if "image" in key:

                    extensions = [
                        "png",
                        "jpg",
                        "jpeg",
                        "gif"
                    ]

                elif "pdf" in key:

                    extensions = [
                        "pdf"
                    ]

                else:

                    extensions = [
                        "mp4",
                        "avi",
                        "mov"
                    ]

                if allowed_file(
                    media_file.filename,
                    extensions
                ):

                    filename = (
                        f"{datetime.now().strftime('%Y%m%d%H%M%S')}_"
                        f"{secure_filename(media_file.filename)}"
                    )

                    filepath = os.path.join(
                        app.config["MEDIA_FOLDER"],
                        filename
                    )

                    media_file.save(
                        filepath
                    )

                    saved_paths[key] = filename

        # ----------------------------------------------------
        # Create campaign
        # ----------------------------------------------------

        new_request = MessageRequest(

            user_id=current_user.id,

            message_text=message_text or "",

            status="Pending",

            report_ready_at=(
                get_local_now()
                + timedelta(hours=6)
            ),

            **saved_paths
        )

        db.session.add(
            new_request
        )

        db.session.flush()

        for number in phone_numbers:

            contact = Contact(

                request_id=new_request.id,

                phone_number=number,

                status="Pending"
            )

            db.session.add(
                contact
            )

        current_user.credits -= (
            required_credits
        )

        db.session.commit()

        flash(
            "Message request submitted "
            "and is pending approval.",
            "success"
        )

        return redirect(
            url_for("dashboard")
        )

    return render_template(
        "client/send_message.html"
    )


# ============================================================
# ADMIN APPROVE CAMPAIGN
# ============================================================

@app.route(
    "/admin/approve/<int:request_id>",
    methods=["POST"]
)
@login_required
def approve_request(
    request_id
):

    if current_user.user_type != "admin":

        return jsonify({
            "error": "Unauthorized"
        }), 403

    campaign = db.get_or_404(
        MessageRequest,
        request_id
    )

    if campaign.status == "Approved":

        return jsonify({

            "success": False,

            "error": "Campaign already approved"
        }), 400

    contacts = Contact.query.filter_by(
        request_id=request_id
    ).all()

    if not contacts:

        return jsonify({

            "success": False,

            "error": "No contacts found"
        }), 400

    instances = (
        WhatsAppInstance.query
        .filter_by(
            status="Active"
        )
        .all()
    )

    if not instances:

        return jsonify({

            "success": False,

            "error": "No active WhatsApp instances"
        }), 500

    campaign.status = "Approved"

    campaign.approved_at = (
        get_local_now()
    )

    sent_count = 0

    failed_count = 0

    # --------------------------------------------------------
    # Send messages
    # --------------------------------------------------------

    for index, contact in enumerate(
        contacts
    ):

        instance = instances[
            index % len(instances)
        ]

        result = (
            WhatsAppService.send_text_message(
                contact.phone_number,
                campaign.message_text
            )
        )

        if result["success"]:

            contact.status = "Sent"

            contact.whatsapp_message_id = (
                result.get("message_id")
            )

            contact.sent_at = (
                get_local_now()
            )

            contact.error_message = None

            sent_count += 1

        else:

            contact.status = "Failed"

            contact.error_message = (
                result.get(
                    "error",
                    "WhatsApp API error"
                )
            )

            contact.sent_at = (
                get_local_now()
            )

            failed_count += 1

        instance.last_used = (
            get_local_now()
        )

    # --------------------------------------------------------
    # Do NOT fake delivery status
    # --------------------------------------------------------

    campaign.report_ready_at = (
        get_local_now()
        + timedelta(hours=6)
    )

    db.session.commit()

    return jsonify({

        "success": True,

        "message": (
            f"Campaign #{request_id} "
            "processed"
        ),

        "sent": sent_count,

        "failed": failed_count,

        "total": len(contacts)
    })


# ============================================================
# WHATSAPP WEBHOOK VERIFICATION
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
        and token == WHATSAPP_VERIFY_TOKEN
    ):

        return challenge, 200

    return (
        "Verification failed",
        403
    )


# ============================================================
# WHATSAPP WEBHOOK
# ============================================================

@app.route(
    "/webhook/whatsapp",
    methods=["POST"]
)
def whatsapp_webhook():

    try:

        data = request.get_json(
            silent=True
        ) or {}

        print(
            "WhatsApp webhook received:"
        )

        print(
            json.dumps(
                data,
                indent=2
            )
        )

        if data.get(
            "object"
        ) != "whatsapp_business_account":

            return jsonify({
                "success": False,
                "error": "Invalid webhook object"
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

                    whatsapp_status = (
                        status_data.get(
                            "status"
                        )
                    )

                    if not message_id:

                        continue

                    print(
                        "Message:",
                        message_id,
                        "Status:",
                        whatsapp_status
                    )

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

                    portal_status = (
                        status_map.get(
                            whatsapp_status
                        )
                    )

                    if not portal_status:

                        continue

                    contact = (
                        Contact.query
                        .filter_by(
                            whatsapp_message_id=(
                                message_id
                            )
                        )
                        .first()
                    )

                    if not contact:

                        print(
                            "Contact not found "
                            "for message ID:",
                            message_id
                        )

                        continue

                    contact.status = (
                        portal_status
                    )

                    # ------------------------------------------------
                    # Handle failure
                    # ------------------------------------------------

                    if portal_status == "Failed":

                        errors = (
                            status_data.get(
                                "errors",
                                []
                            )
                        )

                        if errors:

                            first_error = (
                                errors[0]
                            )

                            contact.error_message = (

                                first_error.get(
                                    "title"
                                )

                                or first_error.get(
                                    "message"
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
            str(error)
        )

        db.session.rollback()

        return jsonify({

            "success": False,

            "error": str(error)

        }), 500


# ============================================================
# ADMIN USERS
# ============================================================

@app.route("/admin/users")
@login_required
def manage_users():

    if current_user.user_type != "admin":

        return redirect(
            url_for("dashboard")
        )

    users = User.query.all()

    return render_template(
        "admin/users.html",
        users=users
    )


# ============================================================
# CREATE USER
# ============================================================

@app.route(
    "/admin/user/create",
    methods=["POST"]
)
@login_required
def create_user():

    if current_user.user_type != "admin":

        return jsonify({
            "error": "Unauthorized"
        }), 403

    username = request.form.get(
        "username"
    )

    password = request.form.get(
        "password"
    )

    user_type = request.form.get(
        "user_type",
        "client"
    )

    credits = request.form.get(
        "credits",
        0
    )

    if not username or not password:

        return jsonify({

            "error":
                "Username and password are required"

        }), 400

    if User.query.filter_by(
        username=username
    ).first():

        return jsonify({

            "error":
                "Username already exists"

        }), 400

    new_user = User(

        username=username,

        password=generate_password_hash(
            password
        ),

        user_type=user_type,

        credits=int(credits)
    )

    db.session.add(
        new_user
    )

    db.session.commit()

    flash(
        f"User '{username}' created successfully.",
        "success"
    )

    return jsonify({

        "success": True,

        "message":
            "User created successfully"
    })


# ============================================================
# DELETE USER
# ============================================================

@app.route(
    "/admin/user/delete/<int:user_id>",
    methods=["POST"]
)
@login_required
def delete_user(user_id):

    if current_user.user_type != "admin":

        return jsonify({
            "error": "Unauthorized"
        }), 403

    user = db.get_or_404(
        User,
        user_id
    )

    if (
        user.username
        == DEFAULT_ADMIN_USERNAME
    ):

        return jsonify({

            "error":
                "Cannot delete main admin"

        }), 400

    db.session.delete(
        user
    )

    db.session.commit()

    flash(
        f"User '{user.username}' deleted.",
        "warning"
    )

    return jsonify({

        "success": True
    })


# ============================================================
# EDIT USER
# ============================================================

@app.route(
    "/admin/user/edit/<int:user_id>",
    methods=["POST"]
)
@login_required
def edit_user(user_id):

    if current_user.user_type != "admin":

        return jsonify({
            "error": "Unauthorized"
        }), 403

    user = db.get_or_404(
        User,
        user_id
    )

    username = request.form.get(
        "username"
    )

    password = request.form.get(
        "password"
    )

    user_type = request.form.get(
        "user_type"
    )

    credits = request.form.get(
        "credits"
    )

    if username:

        user.username = username

    if password:

        user.password = (
            generate_password_hash(
                password
            )
        )

    if user_type:

        user.user_type = user_type

    if credits is not None:

        user.credits = int(
            credits
        )

    db.session.commit()

    flash(
        f"User '{user.username}' updated.",
        "success"
    )

    return jsonify({

        "success": True
    })


# ============================================================
# ADD WHATSAPP INSTANCE
# ============================================================

@app.route(
    "/admin/instance/add",
    methods=["POST"]
)
@login_required
def add_instance():

    if current_user.user_type != "admin":

        return jsonify({
            "error": "Unauthorized"
        }), 403

    name = request.form.get(
        "name"
    )

    phone = request.form.get(
        "phone_number"
    )

    if (
        phone
        and WhatsAppInstance.query
        .filter_by(
            phone_number=phone
        )
        .first()
    ):

        return jsonify({

            "error":
                "Phone number already exists"

        }), 400

    new_instance = WhatsAppInstance(

        name=name,

        phone_number=phone,

        status="Active"
    )

    db.session.add(
        new_instance
    )

    db.session.commit()

    flash(
        f"WhatsApp Instance '{name}' added.",
        "success"
    )

    return jsonify({

        "success": True,

        "message":
            "Instance added successfully"
    })


# ============================================================
# DELETE INSTANCE
# ============================================================

@app.route(
    "/admin/instance/delete/<int:inst_id>",
    methods=["POST"]
)
@login_required
def delete_instance(inst_id):

    if current_user.user_type != "admin":

        return jsonify({
            "error": "Unauthorized"
        }), 403

    instance = db.get_or_404(
        WhatsAppInstance,
        inst_id
    )

    db.session.delete(
        instance
    )

    db.session.commit()

    flash(
        f"WhatsApp Instance "
        f"'{instance.name}' deleted.",
        "warning"
    )

    return jsonify({

        "success": True
    })


# ============================================================
# REJECT CAMPAIGN
# ============================================================

@app.route(
    "/admin/reject/<int:request_id>",
    methods=["POST"]
)
@login_required
def reject_request(request_id):

    if current_user.user_type != "admin":

        return jsonify({
            "error": "Unauthorized"
        }), 403

    campaign = db.get_or_404(
        MessageRequest,
        request_id
    )

    if campaign.status != "Rejected":

        client = db.session.get(
            User,
            campaign.user_id
        )

        if client:

            client.credits += len(
                campaign.contacts
            )

    campaign.status = "Rejected"

    db.session.commit()

    flash(
        f"Campaign #{request_id} rejected.",
        "warning"
    )

    return jsonify({

        "success": True
    })


# ============================================================
# OLD CSV REPORT PROCESSING
#
# Kept for compatibility with your existing UI.
#
# IMPORTANT:
# This should NOT be used as the real WhatsApp delivery
# mechanism. The webhook is now the source of truth.
# ============================================================

@app.route(
    "/admin/campaign/process-report",
    methods=["POST"]
)
@login_required
def process_campaign_report():

    if current_user.user_type != "admin":

        return jsonify({
            "error": "Unauthorized"
        }), 403

    req_id = request.form.get(
        "request_id"
    )

    success_rate = request.form.get(
        "success_rate",
        type=int
    )

    status_file = request.files.get(
        "status_file"
    )

    if (
        not req_id
        or success_rate is None
        or success_rate < 0
        or success_rate > 100
    ):

        return jsonify({
            "error":
                "Invalid parameters provided"
        }), 400

    campaign = db.get_or_404(
        MessageRequest,
        req_id
    )

    contacts = campaign.contacts

    if not contacts:

        return jsonify({
            "error":
                "No contacts found"
        }), 400

    # --------------------------------------------------------
    # If a CSV is uploaded, retain existing functionality.
    # --------------------------------------------------------

    uploaded_statuses = {}

    csv_file_uploaded = False

    if (
        status_file
        and status_file.filename != ""
    ):

        csv_file_uploaded = True

        try:

            stream = io.StringIO(
                status_file.stream
                .read()
                .decode("utf-8"),
                newline=None
            )

            reader = csv.reader(
                stream
            )

            for row in reader:

                if (
                    not row
                    or len(row) < 2
                ):
                    continue

                if (
                    "phone"
                    in row[0].lower()
                    or "status"
                    in row[1].lower()
                ):
                    continue

                phone = "".join(
                    filter(
                        str.isdigit,
                        row[0]
                    )
                )

                status = row[1].strip()

                status_lower = (
                    status.lower()
                )

                if (
                    "deliver"
                    in status_lower
                    or "success"
                    in status_lower
                    or "sent"
                    in status_lower
                ):

                    norm_status = "Delivered"

                else:

                    norm_status = "Failed"

                if phone:

                    uploaded_statuses[
                        phone
                    ] = norm_status

        except Exception as error:

            return jsonify({

                "error":
                    f"Error parsing CSV: {error}"

            }), 400

    updated_count = 0

    remaining_contacts = []

    if csv_file_uploaded:

        for contact in contacts:

            clean_phone = (
                normalize_phone_number(
                    contact.phone_number
                )
            )

            matched_status = (
                uploaded_statuses
                .get(clean_phone)
            )

            if not matched_status:

                for (
                    uploaded_phone,
                    uploaded_status
                ) in uploaded_statuses.items():

                    if (
                        uploaded_phone.endswith(
                            clean_phone
                        )
                        or clean_phone.endswith(
                            uploaded_phone
                        )
                    ):

                        matched_status = (
                            uploaded_status
                        )

                        break

            if matched_status:

                contact.status = (
                    matched_status
                )

                contact.is_csv_matched = True

                updated_count += 1

            else:

                contact.is_csv_matched = False

                remaining_contacts.append(
                    contact
                )

    else:

        for contact in contacts:

            if contact.is_csv_matched:

                updated_count += 1

            else:

                remaining_contacts.append(
                    contact
                )

    # --------------------------------------------------------
    # IMPORTANT:
    # We no longer randomly generate WhatsApp delivery
    # statuses here.
    #
    # Real delivery comes from the Meta webhook.
    # --------------------------------------------------------

    campaign.status = "Completed"

    campaign.report_ready_at = (
        get_local_now()
    )

    db.session.commit()

    flash(
        f"Campaign #{req_id} report updated.",
        "success"
    )

    return jsonify({

        "success": True,

        "matched": updated_count,

        "remaining": len(
            remaining_contacts
        )
    })


# ============================================================
# VIEW REPORT
# ============================================================

@app.route(
    "/report/<int:request_id>"
)
@login_required
def view_report(request_id):

    campaign = db.get_or_404(
        MessageRequest,
        request_id
    )

    if (
        current_user.user_type != "admin"
        and campaign.user_id
        != current_user.id
    ):

        flash(
            "Unauthorized access",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    now = get_local_now()

    is_ready = (

        campaign.report_ready_at
        and now >= campaign.report_ready_at

    ) or campaign.status == "Completed"

    # --------------------------------------------------------
    # DO NOT randomly change Sent -> Delivered.
    #
    # Meta webhook is responsible for this.
    # --------------------------------------------------------

    return render_template(
        "common/report.html",
        request=campaign,
        is_ready=is_ready
    )


# ============================================================
# DOWNLOAD NUMBERS
# ============================================================

@app.route(
    "/report/<int:request_id>/numbers/download"
)
@login_required
def download_numbers(request_id):

    campaign = db.get_or_404(
        MessageRequest,
        request_id
    )

    if (
        current_user.user_type != "admin"
        and campaign.user_id
        != current_user.id
    ):

        flash(
            "Unauthorized access",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    output = io.StringIO()

    writer = csv.writer(
        output
    )

    writer.writerow([
        "Phone Number"
    ])

    for contact in campaign.contacts:

        writer.writerow([
            contact.phone_number
        ])

    output.seek(0)

    return Response(

        output.getvalue(),

        mimetype="text/csv",

        headers={

            "Content-Disposition":
                (
                    "attachment;"
                    f"filename=numbers_campaign_"
                    f"{request_id}.csv"
                )
        }
    )


# ============================================================
# DOWNLOAD REPORT
# ============================================================

@app.route(
    "/report/<int:request_id>/download"
)
@login_required
def download_report(request_id):

    campaign = db.get_or_404(
        MessageRequest,
        request_id
    )

    if (
        current_user.user_type != "admin"
        and campaign.user_id
        != current_user.id
    ):

        flash(
            "Unauthorized access",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    output = io.StringIO()

    writer = csv.writer(
        output
    )

    writer.writerow([
        "Phone Number",
        "Status",
        "Sent At",
        "WhatsApp Message ID",
        "Error Message"
    ])

    for contact in campaign.contacts:

        writer.writerow([

            contact.phone_number,

            contact.status,

            (
                contact.sent_at.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                if contact.sent_at
                else "N/A"
            ),

            contact.whatsapp_message_id
            or "",

            contact.error_message
            or ""
        ])

    output.seek(0)

    return Response(

        output.getvalue(),

        mimetype="text/csv",

        headers={

            "Content-Disposition":
                (
                    "attachment;"
                    f"filename=report_campaign_"
                    f"{request_id}.csv"
                )
        }
    )


# ============================================================
# DOWNLOAD MEDIA
# ============================================================

@app.route(
    "/download-media/<int:request_id>/<media_type>"
)
@app.route(
    "/download-media/<int:request_id>/<media_type>/<download_filename>"
)
@login_required
def download_media(
    request_id,
    media_type,
    download_filename=None
):

    campaign = db.get_or_404(
        MessageRequest,
        request_id
    )

    if (
        current_user.user_type != "admin"
        and campaign.user_id
        != current_user.id
    ):

        return jsonify({
            "error": "Unauthorized"
        }), 403

    filename = None

    if (
        media_type == "image1"
        and campaign.image1
    ):

        filename = campaign.image1

    elif (
        media_type == "image2"
        and campaign.image2
    ):

        filename = campaign.image2

    elif (
        media_type == "image3"
        and campaign.image3
    ):

        filename = campaign.image3

    elif (
        media_type == "image4"
        and campaign.image4
    ):

        filename = campaign.image4

    elif (
        media_type == "pdf_file"
        and campaign.pdf_file
    ):

        filename = campaign.pdf_file

    elif (
        media_type == "video_file"
        and campaign.video_file
    ):

        filename = campaign.video_file

    if not filename:

        return jsonify({
            "error": "File not found"
        }), 404

    if not download_filename:

        download_filename = filename

    filepath = os.path.join(
        app.config["MEDIA_FOLDER"],
        filename
    )

    if not os.path.exists(
        filepath
    ):

        return jsonify({
            "error":
                "File not found on disk"
        }), 404

    return send_from_directory(

        app.config["MEDIA_FOLDER"],

        filename,

        as_attachment=True,

        download_name=download_filename,

        mimetype="application/octet-stream"
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    try:

        db.session.execute(
            db.text("SELECT 1")
        )

        return jsonify({

            "status": "ok",

            "database": "connected",

            "whatsapp": "configured"

        }), 200

    except Exception as error:

        return jsonify({

            "status": "error",

            "error": str(error)

        }), 500


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    app.run(

        debug=False,

        host="0.0.0.0",

        port=int(
            os.getenv(
                "PORT",
                "5000"
            )
        )
    )
