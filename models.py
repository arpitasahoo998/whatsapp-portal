from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timedelta

db = SQLAlchemy()

def get_local_now():
    return datetime.utcnow() + timedelta(hours=5, minutes=30)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    user_type = db.Column(db.String(20), nullable=False, default='client') # 'admin' or 'client'
    credits = db.Column(db.Integer, nullable=False, default=0)

class MessageRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='requests')
    message_text = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='Pending') # Pending, Approved, Processing, Completed, Rejected
    
    # Media paths
    image1 = db.Column(db.String(255))
    image2 = db.Column(db.String(255))
    image3 = db.Column(db.String(255))
    image4 = db.Column(db.String(255))
    pdf_file = db.Column(db.String(255))
    video_file = db.Column(db.String(255))
    
    created_at = db.Column(db.DateTime, default=get_local_now)
    approved_at = db.Column(db.DateTime)
    report_ready_at = db.Column(db.DateTime)
    
    contacts = db.relationship('Contact', backref='request', lazy=True, cascade="all, delete-orphan")

class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('message_request.id'), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='Pending') # Pending, Sent, Delivered, Failed
    sent_at = db.Column(db.DateTime)
    error_message = db.Column(db.String(255))
    is_csv_matched = db.Column(db.Boolean, default=False)

class WhatsAppInstance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    phone_number = db.Column(db.String(20), unique=True)
    status = db.Column(db.String(20), default='Active') # Active, Banned
    last_used = db.Column(db.DateTime, default=get_local_now)
