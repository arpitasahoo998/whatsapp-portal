from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timedelta

db = SQLAlchemy()


def get_local_now():
    """
    Returns current time in IST.
    """
    return datetime.utcnow() + timedelta(hours=5, minutes=30)


class User(db.Model, UserMixin):

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

    # ---------------------------------------------------------
    # Media paths
    # ---------------------------------------------------------

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

    # ---------------------------------------------------------
    # Dates
    # ---------------------------------------------------------

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
        db.ForeignKey("message_request.id"),
        nullable=False
    )

    phone_number = db.Column(
        db.String(20),
        nullable=False
    )

    # Pending
    # Sent
    # Delivered
    # Read
    # Failed

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

    # ---------------------------------------------------------
    # IMPORTANT:
    # Meta WhatsApp message ID
    # ---------------------------------------------------------

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
