# WhatsApp Portal - Production Deployment Guide

This guide provides step-by-step instructions for deploying the WhatsApp Portal to a production Linux server (e.g., Ubuntu 20.04 or 22.04) using **PostgreSQL**, **Gunicorn**, **Nginx**, and **Systemd**.

## 1. Prerequisites
Update your system packages and install the necessary dependencies including PostgreSQL:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install python3-pip python3-dev python3-venv build-essential libssl-dev libffi-dev python3-setuptools nginx postgresql postgresql-contrib libpq-dev -y
```

## 2. PostgreSQL Database Setup
Configure your PostgreSQL database and create a user for the application:

```bash
# Log in to the PostgreSQL prompt
sudo -u postgres psql

# Run these SQL commands (replace 'your_password' with a strong password)
CREATE DATABASE whatsapp_portal;
CREATE USER whatsapp_user WITH ENCRYPTED PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE whatsapp_portal TO whatsapp_user;
\q
```

## 3. Transfer the Code
Upload or clone your project repository to your production server. A standard location is `/var/www/`.

```bash
sudo mkdir -p /var/www/whatsapp_portal
# (Transfer your files into /var/www/whatsapp_portal)

# Change ownership to your current user (replace 'your_user' with your actual username)
sudo chown -R $USER:www-data /var/www/whatsapp_portal
cd /var/www/whatsapp_portal
```

## 4. Set Up the Virtual Environment
Create an isolated Python environment for your application and install the dependencies:

```bash
python3 -m venv venv
source venv/bin/activate

# Install the application dependencies
pip install wheel
pip install -r requirements.txt

# Install Gunicorn (the production WSGI server)
pip install gunicorn
```

## 5. Verify Directory Permissions
The application needs read/write access to certain directories to save uploaded media files.

```bash
# Create the instance and media directories if they do not exist
mkdir -p static/media
mkdir -p uploads

# Grant group ownership to www-data (the Nginx user)
sudo chgrp -R www-data static/media uploads
sudo chmod -R 775 static/media uploads
```

## 6. Test Gunicorn Locally
Before setting up the background service, verify that Gunicorn can run your application successfully. Don't forget to pass the database URL:

```bash
export DATABASE_URL="postgresql://whatsapp_user:your_password@localhost/whatsapp_portal"
gunicorn --bind 0.0.0.0:5000 app:app
```
*If it starts without errors, stop it by pressing `Ctrl + C`.*

## 7. Create a Systemd Service for Gunicorn
Systemd will automatically start Gunicorn when the server boots and restart it if it crashes.

1. Create a new service file:
```bash
sudo nano /etc/systemd/system/whatsapp_portal.service
```

2. Paste the following configuration (Ensure you replace `your_user` with your actual Linux username and update `your_password`):
```ini
[Unit]
Description=Gunicorn instance to serve WhatsApp Portal
After=network.target

[Service]
User=your_user
Group=www-data
WorkingDirectory=/var/www/whatsapp_portal
Environment="PATH=/var/www/whatsapp_portal/venv/bin"
Environment="FLASK_ENV=production"
Environment="DATABASE_URL=postgresql://whatsapp_user:your_password@localhost/whatsapp_portal"
ExecStart=/var/www/whatsapp_portal/venv/bin/gunicorn --workers 3 --bind unix:whatsapp_portal.sock -m 007 app:app

[Install]
WantedBy=multi-user.target
```

3. Start and enable the service:
```bash
sudo systemctl start whatsapp_portal
sudo systemctl enable whatsapp_portal
sudo systemctl status whatsapp_portal
```
*(Verify that the status says "active (running)".)*

## 8. Configure Nginx Reverse Proxy
Nginx will handle all incoming web traffic, serve your static files directly (for maximum speed), and pass Python requests to Gunicorn.

1. Create a new Nginx configuration file:
```bash
sudo nano /etc/nginx/sites-available/whatsapp_portal
```

2. Paste the following configuration (Replace `your_domain_or_IP` with your actual domain name or server IP address):
```nginx
server {
    listen 80;
    server_name your_domain_or_IP;

    # Increase max upload size for media attachments
    client_max_body_size 50M;

    location / {
        include proxy_params;
        proxy_pass http://unix:/var/www/whatsapp_portal/whatsapp_portal.sock;
    }

    # Serve static files directly via Nginx for performance
    location /static {
        alias /var/www/whatsapp_portal/static;
        expires 30d;
    }
}
```

3. Enable the configuration and restart Nginx:
```bash
# Link the file to the sites-enabled directory
sudo ln -s /etc/nginx/sites-available/whatsapp_portal /etc/nginx/sites-enabled

# Test Nginx syntax to ensure there are no typos
sudo nginx -t

# Restart Nginx to apply changes
sudo systemctl restart nginx
```

## 9. Firewall Configuration (UFW)
If you have a firewall enabled, ensure HTTP (and SSH) traffic is allowed:

```bash
sudo ufw allow 'Nginx Full'
sudo ufw allow OpenSSH
sudo ufw enable
```

## 10. Secure with SSL (Optional but Highly Recommended)
If you are using a domain name, secure your site with a free Let's Encrypt SSL certificate:

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your_domain.com
```

---

## 🛠️ Maintenance Commands
If you ever need to push new code updates to your server in the future, use these commands:

```bash
cd /var/www/whatsapp_portal
# Pull/upload your new code here...

# Restart Gunicorn to apply Python changes
sudo systemctl restart whatsapp_portal
```
