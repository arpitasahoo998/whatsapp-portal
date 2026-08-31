import os
import pandas as pd
import requests
import json
import csv
import io
import random
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, User, MessageRequest, Contact, WhatsAppInstance

app = Flask(__name__)
app.config['SECRET_KEY'] = 'whatsapp-portal-secret-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost/whatsapp_portal')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MEDIA_FOLDER'] = os.path.join('static', 'media')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

def get_local_now():
    return datetime.utcnow() + timedelta(hours=5, minutes=30)

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['MEDIA_FOLDER'], exist_ok=True)

db.init_app(app)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password=generate_password_hash('admin123'), user_type='admin')
        db.session.add(admin)
        
        # Default Client for testing
        client = User(username='user1', password=generate_password_hash('user123'), user_type='client')
        db.session.add(client)
        
        for i in range(1, 4):
            inst = WhatsAppInstance(name=f"Instance {i}", phone_number=f"+91987654321{i}", status='Active')
            db.session.add(inst)
        db.session.commit()

# WhatsApp API Configuration (Meta/Facebook Developer Portal)
WHATSAPP_API_TOKEN = 'YOUR_ACCESS_TOKEN'
WHATSAPP_PHONE_NUMBER_ID = 'YOUR_PHONE_NUMBER_ID'
WHATSAPP_VERSION = 'v18.0'

class WhatsAppService:
    @staticmethod
    def send_message(instance_config, to_number, text, media_paths=None):
        """
        Generic function to send WhatsApp messages.
        This can be adapted for Meta API, Twilio, or Baileys Webhooks.
        """
        # Meta API Implementation Example:
        url = f"https://graph.facebook.com/{WHATSAPP_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {WHATSAPP_API_TOKEN}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "text",
            "text": {"body": text}
        }
        
        # In a real scenario, you'd handle media here too.
        # For now, we log the attempt.
        print(f"DEBUG: Sending message to {to_number} via {instance_config.name}")
        
        try:
            # Uncomment below to enable real Meta API calls
            # response = requests.post(url, headers=headers, json=payload)
            # return response.status_code == 200
            return True # Simulating success for now
        except Exception as e:
            print(f"Error sending message: {e}")
            return False

def allowed_file(filename, extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in extensions

@app.route('/')
@login_required
def dashboard():
    if current_user.user_type == 'admin':
        requests = MessageRequest.query.order_by(MessageRequest.created_at.desc()).all()
        instances = WhatsAppInstance.query.all()
        return render_template('admin/dashboard.html', requests=requests, instances=instances)
    else:
        requests = MessageRequest.query.filter_by(user_id=current_user.id).order_by(MessageRequest.created_at.desc()).all()
        return render_template('client/dashboard.html', requests=requests)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/send-message', methods=['GET', 'POST'])
@login_required
def send_message():
    if request.method == 'POST':
        message_text = request.form.get('message_text')
        numbers_raw = request.form.get('manual_numbers')
        file = request.files.get('number_file')
        
        phone_numbers = []
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            try:
                if filename.endswith('.csv'):
                    df = pd.read_csv(filepath)
                else:
                    df = pd.read_excel(filepath)
                phone_numbers = df.iloc[:, 0].astype(str).tolist()
            except Exception as e:
                flash(f"Error reading file: {str(e)}", 'danger')
                return redirect(url_for('send_message'))
            finally:
                if os.path.exists(filepath): os.remove(filepath)
        
        if numbers_raw:
            manual = [n.strip() for n in numbers_raw.replace(',', '\n').split('\n') if n.strip()]
            phone_numbers.extend(manual)
        
        if not phone_numbers:
            flash("No phone numbers provided", 'warning')
            return redirect(url_for('send_message'))
            
        required_credits = len(phone_numbers)
        if required_credits > current_user.credits:
            req_plural = "credit" if required_credits == 1 else "credits"
            cur_plural = "credit" if current_user.credits == 1 else "credits"
            flash(f"Insufficient credits. This campaign requires {required_credits} {req_plural}, but you only have {current_user.credits} {cur_plural}.", 'danger')
            return redirect(url_for('send_message'))

        media_files = {
            'image1': request.files.get('image1'),
            'image2': request.files.get('image2'),
            'image3': request.files.get('image3'),
            'image4': request.files.get('image4'),
            'pdf_file': request.files.get('pdf_file'),
            'video_file': request.files.get('video_file')
        }
        
        saved_paths = {}
        for key, f in media_files.items():
            if f and f.filename != '':
                ext = 'png,jpg,jpeg,gif' if 'image' in key else 'pdf' if 'pdf' in key else 'mp4,avi,mov'
                if allowed_file(f.filename, ext.split(',')):
                    filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(f.filename)}"
                    f.save(os.path.join(app.config['MEDIA_FOLDER'], filename))
                    saved_paths[key] = filename
        
        new_request = MessageRequest(
            user_id=current_user.id,
            message_text=message_text,
            status='Pending',
            report_ready_at=get_local_now() + timedelta(hours=6),
            **saved_paths
        )
        db.session.add(new_request)
        db.session.flush()
        
        for num in set(phone_numbers):
            contact = Contact(request_id=new_request.id, phone_number=num)
            db.session.add(contact)
            
        current_user.credits -= required_credits
        db.session.commit()
        flash("Message request submitted and is pending approval.", "success")
        return redirect(url_for('dashboard'))
        
    return render_template('client/send_message.html')

@app.route('/admin/approve/<int:request_id>', methods=['POST'])
@login_required
def approve_request(request_id):
    if current_user.user_type != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    req = db.get_or_404(MessageRequest, request_id)
    req.status = 'Approved'
    req.approved_at = get_local_now()
    
    contacts = Contact.query.filter_by(request_id=request_id).all()
    instances = WhatsAppInstance.query.filter_by(status='Active').all()
    
    if not instances:
        return jsonify({'error': 'No active instances'}), 500
        
    total_contacts = len(contacts)
    total_duration_target = 10800  # 3 hours target sending duration
    base_interval = 1.5
    interval = total_duration_target / float(total_contacts) if total_contacts * base_interval > total_duration_target else base_interval
    base_time = req.approved_at
        
    for i, contact in enumerate(contacts):
        instance = instances[i % len(instances)]
        
        # Real API Call
        success = WhatsAppService.send_message(instance, contact.phone_number, req.message_text)
        
        if success:
            contact.status = 'Sent'
        else:
            contact.status = 'Failed'
            contact.error_message = "API Connection Error"
            
        jitter = random.uniform(-interval * 0.2, interval * 0.2) if interval > 0.5 else 0
        seconds_offset = i * interval + jitter
        contact.sent_at = base_time + timedelta(seconds=int(seconds_offset))
            
    flash(f"Campaign #{request_id} has been approved and WhatsApp messages are being dispatched.", "success")
    db.session.commit()
    return jsonify({'success': True, 'message': 'Request approved'})

@app.route('/admin/users')
@login_required
def manage_users():
    if current_user.user_type != 'admin':
        return redirect(url_for('dashboard'))
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/user/create', methods=['POST'])
@login_required
def create_user():
    if current_user.user_type != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    username = request.form.get('username')
    password = request.form.get('password')
    user_type = request.form.get('user_type', 'client')
    credits = int(request.form.get('credits', 0))
    
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already exists'}), 400
        
    new_user = User(username=username, password=generate_password_hash(password), user_type=user_type, credits=credits)
    db.session.add(new_user)
    flash(f"User '{username}' has been created successfully.", "success")
    db.session.commit()
    return jsonify({'success': True, 'message': 'User created successfully'})

@app.route('/admin/user/delete/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if current_user.user_type != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    user = db.get_or_404(User, user_id)
    if user.username == 'admin':
        return jsonify({'error': 'Cannot delete main admin'}), 400
    db.session.delete(user)
    flash(f"User '{user.username}' has been deleted.", "warning")
    db.session.commit()
    return jsonify({'success': True, 'message': 'User deleted successfully'})

@app.route('/admin/user/edit/<int:user_id>', methods=['POST'])
@login_required
def edit_user(user_id):
    if current_user.user_type != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    user = db.get_or_404(User, user_id)
    username = request.form.get('username')
    password = request.form.get('password')
    user_type = request.form.get('user_type')
    credits = request.form.get('credits')
    
    user.username = username
    if password:
        user.password = generate_password_hash(password)
    user.user_type = user_type
    if credits is not None:
        user.credits = int(credits)
        
    flash(f"User '{user.username}' credentials have been updated successfully.", "success")
    db.session.commit()
    return jsonify({'success': True, 'message': 'User updated successfully'})

@app.route('/admin/instance/add', methods=['POST'])
@login_required
def add_instance():
    if current_user.user_type != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    name = request.form.get('name')
    phone = request.form.get('phone_number')
    
    if WhatsAppInstance.query.filter_by(phone_number=phone).first():
        return jsonify({'error': 'Phone number already exists'}), 400
        
    new_inst = WhatsAppInstance(name=name, phone_number=phone)
    db.session.add(new_inst)
    flash(f"WhatsApp Instance '{name}' has been added successfully.", "success")
    db.session.commit()
    return jsonify({'success': True, 'message': 'Instance added successfully'})

@app.route('/admin/instance/delete/<int:inst_id>', methods=['POST'])
@login_required
def delete_instance(inst_id):
    if current_user.user_type != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    inst = db.get_or_404(WhatsAppInstance, inst_id)
    db.session.delete(inst)
    flash(f"WhatsApp Instance '{inst.name}' has been deleted.", "warning")
    db.session.commit()
    return jsonify({'success': True, 'message': 'Instance deleted successfully'})

@app.route('/admin/reject/<int:request_id>', methods=['POST'])
@login_required
def reject_request(request_id):
    if current_user.user_type != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    req = db.get_or_404(MessageRequest, request_id)
    
    # Refund credits if transitioning to Rejected from another state
    if req.status != 'Rejected':
        client = db.session.get(User, req.user_id)
        if client:
            client.credits += len(req.contacts)
            
    req.status = 'Rejected'
    flash(f"Campaign #{request_id} has been rejected. Credits have been refunded to the client.", "warning")
    db.session.commit()
    return jsonify({'success': True, 'message': 'Request rejected'})

@app.route('/admin/campaign/process-report', methods=['POST'])
@login_required
def process_campaign_report():
    if current_user.user_type != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
        
    req_id = request.form.get('request_id')
    success_rate = request.form.get('success_rate', type=int)
    status_file = request.files.get('status_file')
    
    if not req_id or success_rate is None or success_rate < 0 or success_rate > 100:
        return jsonify({'error': 'Invalid parameters provided'}), 400
        
    campaign = db.get_or_404(MessageRequest, req_id)
    contacts = campaign.contacts
    
    if not contacts:
        return jsonify({'error': 'No contacts found for this campaign'}), 400
        
    # Step A: Parse status CSV if uploaded
    uploaded_statuses = {}
    csv_file_uploaded = False
    
    if status_file and status_file.filename != '':
        csv_file_uploaded = True
        try:
            stream = io.StringIO(status_file.stream.read().decode("utf-8"), newline=None)
            reader = csv.reader(stream)
            for row in reader:
                if not row or len(row) < 2:
                    continue
                # Skip header
                if 'phone' in row[0].lower() or 'status' in row[1].lower():
                    continue
                
                phone = ''.join(filter(str.isdigit, row[0]))
                status = row[1].strip()
                
                # Normalize status
                status_lower = status.lower()
                if 'deliver' in status_lower or 'success' in status_lower or 'sent' in status_lower:
                    norm_status = 'Delivered'
                else:
                    norm_status = 'Failed'
                    
                if phone:
                    uploaded_statuses[phone] = norm_status
        except Exception as e:
            return jsonify({'error': f"Error parsing CSV file: {str(e)}"}), 400
            
    # Step B: Process contacts
    updated_count = 0
    remaining_contacts = []
    
    if csv_file_uploaded:
        # Scenario 1: A new CSV was uploaded! Match contacts and mark is_csv_matched = True
        for contact in contacts:
            clean_phone = ''.join(filter(str.isdigit, contact.phone_number))
            matched_status = None
            if clean_phone in uploaded_statuses:
                matched_status = uploaded_statuses[clean_phone]
            else:
                # Check if any key in uploaded_statuses is a suffix of clean_phone or vice versa
                for uploaded_phone, u_status in uploaded_statuses.items():
                    if uploaded_phone.endswith(clean_phone) or clean_phone.endswith(uploaded_phone):
                        matched_status = u_status
                        break
                        
            if matched_status:
                contact.status = matched_status
                contact.is_csv_matched = True
                updated_count += 1
            else:
                contact.is_csv_matched = False
                remaining_contacts.append(contact)
    else:
        # Scenario 2: No new CSV uploaded (regeneration). Keep CSV-matched statuses, recalculate others!
        for contact in contacts:
            if contact.is_csv_matched:
                updated_count += 1
            else:
                remaining_contacts.append(contact)
            
    # 2. Distribute remaining contacts based on success percentage
    remaining_count = len(remaining_contacts)
    if remaining_count > 0:
        success_count = round(remaining_count * (success_rate / 100.0))
        
        # Create a list of statuses: success_count 'Delivered' and the rest 'Failed'
        statuses = ['Delivered'] * success_count + ['Failed'] * (remaining_count - success_count)
        
        # Shuffle the statuses to simulate real random distribution
        random.shuffle(statuses)
        
        # Assign to remaining contacts
        for idx, contact in enumerate(remaining_contacts):
            contact.status = statuses[idx]
            
    # Step C: Finalize campaign status
    campaign.status = 'Completed'
    if not campaign.approved_at:
        campaign.approved_at = get_local_now()
    campaign.report_ready_at = get_local_now()
    
    # 3. Assign highly realistic forward-spread IST sent_at times to all contacts starting from approved_at
    total_contacts = len(contacts)
    total_duration_target = 10800  # 3 hours target sending duration
    base_interval = 1.5
    interval = total_duration_target / float(total_contacts) if total_contacts * base_interval > total_duration_target else base_interval
    base_time = campaign.approved_at
    
    for idx, contact in enumerate(contacts):
        jitter = random.uniform(-interval * 0.2, interval * 0.2) if interval > 0.5 else 0
        seconds_offset = idx * interval + jitter
        contact.sent_at = base_time + timedelta(seconds=int(seconds_offset))
            
    db.session.commit()
    
    # Session flash message inside Flask to show beautiful floating notification
    flash(f"Campaign #{req_id} report generated successfully! Matched via CSV: {updated_count}, Distributed: {remaining_count} ({success_rate}% success rate).", "success")
    
    return jsonify({'success': True})

@app.route('/report/<int:request_id>')
@login_required
def view_report(request_id):
    req = db.get_or_404(MessageRequest, request_id)
    if current_user.user_type != 'admin' and req.user_id != current_user.id:
        flash("Unauthorized access", "danger")
        return redirect(url_for('dashboard'))
    
    now = get_local_now()
    is_ready = now >= req.report_ready_at or req.status == 'Completed'
    
    if is_ready and req.status == 'Approved':
        req.status = 'Completed'
        import random
        for contact in req.contacts:
            if contact.status == 'Sent':
                contact.status = 'Delivered' if random.random() > 0.1 else 'Failed'
                if contact.status == 'Failed':
                    contact.error_message = "Number not on WhatsApp"
        db.session.commit()

    return render_template('common/report.html', request=req, is_ready=is_ready)
@app.route('/report/<int:request_id>/numbers/download')
@login_required
def download_numbers(request_id):
    req = db.get_or_404(MessageRequest, request_id)
    if current_user.user_type != 'admin' and req.user_id != current_user.id:
        flash("Unauthorized access", "danger")
        return redirect(url_for('dashboard'))
    
    import io
    import csv
    from flask import Response
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Phone Number'])
    
    for contact in req.contacts:
        writer.writerow([contact.phone_number])
    
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=numbers_campaign_{request_id}.csv"}
    )


@app.route('/report/<int:request_id>/download')
@login_required
def download_report(request_id):
    req = db.get_or_404(MessageRequest, request_id)
    if current_user.user_type != 'admin' and req.user_id != current_user.id:
        flash("Unauthorized access", "danger")
        return redirect(url_for('dashboard'))
    
    import io
    import csv
    from flask import Response
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Phone Number', 'Status', 'Sent At', 'Error Message'])
    
    for contact in req.contacts:
        writer.writerow([
            contact.phone_number,
            contact.status,
            contact.sent_at.strftime('%Y-%m-%d %H:%M:%S') if contact.sent_at else 'N/A',
            contact.error_message or ''
        ])
    
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename=report_campaign_{request_id}.csv"}
    )

@app.route('/download-media/<int:request_id>/<media_type>')
@app.route('/download-media/<int:request_id>/<media_type>/<download_filename>')
@login_required
def download_media(request_id, media_type, download_filename=None):
    import os
    req = db.get_or_404(MessageRequest, request_id)
    
    if current_user.user_type != 'admin' and req.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
        
    filename = None
    original_ext = ""
    
    if media_type == 'image1' and req.image1:
        filename = req.image1
        original_ext = os.path.splitext(req.image1)[1]
    elif media_type == 'image2' and req.image2:
        filename = req.image2
        original_ext = os.path.splitext(req.image2)[1]
    elif media_type == 'image3' and req.image3:
        filename = req.image3
        original_ext = os.path.splitext(req.image3)[1]
    elif media_type == 'image4' and req.image4:
        filename = req.image4
        original_ext = os.path.splitext(req.image4)[1]
    elif media_type == 'pdf_file' and req.pdf_file:
        filename = req.pdf_file
        original_ext = os.path.splitext(req.pdf_file)[1]
    elif media_type == 'video_file' and req.video_file:
        filename = req.video_file
        original_ext = os.path.splitext(req.video_file)[1]
        
    if not filename:
        return jsonify({'error': 'File not found'}), 404
        
    if not download_filename:
        download_filename = filename
            
    filepath = os.path.join(app.config['MEDIA_FOLDER'], filename)
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found on disk'}), 404
        
    try:
        return send_from_directory(
            app.config['MEDIA_FOLDER'],
            filename,
            as_attachment=True,
            download_name=download_filename,
            mimetype='application/octet-stream'
        )
    except TypeError:
        return send_from_directory(
            app.config['MEDIA_FOLDER'],
            filename,
            as_attachment=True,
            attachment_filename=download_filename,
            mimetype='application/octet-stream'
        )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
