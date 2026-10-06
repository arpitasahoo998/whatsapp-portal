from datetime import datetime, timedelta

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


def get_local_now():
    """Return current India Standard Time (IST) as a naive datetime."""
    return datetime.utcnow() + timedelta(hours=5, minutes=30)


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
        db.ForeignKey("user.id", ondelete="CASCADE"),
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
        db.ForeignKey("message_request.id", ondelete="CASCADE"),
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

    # Meta WhatsApp Cloud API message ID.
    # Nullable because a message does not have an ID until Meta accepts it.
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
