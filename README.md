# WhatsApp Messaging Portal

A premium Python-based portal for managing WhatsApp message campaigns with approval workflows and reporting.

## Features
- **Modern UI**: Glassmorphism design with Dark Mode.
- **Campaign Management**: Send messages to multiple contacts via CSV/Excel or manual entry.
- **Media Attachments**: Support for 4 Images, 1 PDF, and 1 Video per campaign.
- **Admin Approval Queue**: Requests are held in "Pending" status until an admin approves them.
- **Virtual Number Rotation**: Simulates load balancing across multiple WhatsApp instances.
- **Delayed Reporting**: Final delivery status (Sent/Delivered/Failed) is compiled after a 6-hour window.

## Technology Stack
- **Backend**: Flask, SQLAlchemy (SQLite)
- **Data Processing**: Pandas, OpenPyxl
- **Frontend**: Vanilla CSS (Premium styling), Jinja2 templates

## Setup
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the application:
   ```bash
   python app.py
   ```
3. Default Credentials:
   - **Username**: admin
   - **Password**: admin123

## Workflow
1. **Client** logs in and submits a message with contacts and media.
2. **Admin** reviews the request in the Approval Queue.
3. **Admin** clicks "Accept". Messages are "Sent" immediately using virtual numbers.
4. **System** waits 6 hours to update "Delivered" or "Failed" statuses.
5. **Client** views the final report on their dashboard.
