#!/bin/bash
# ==============================================
# Invoice Platform - VPS Deployment Script
# Run this on your VPS (Ubuntu/Debian)
# ==============================================

set -e

echo "=========================================="
echo "  Invoice Platform - VPS Deployment"
echo "=========================================="

# --- VARIABLES (CHANGE THESE) ---
APP_DIR="/home/deploy/invoice_platform"
REPO_URL="https://github.com/Connecta-Superadmin/zatca.git"
DOMAIN="YOUR_DOMAIN_OR_IP"   # <-- Change this
DB_NAME="zatca"
DB_USER="invoice_user"
DB_PASS="CHANGE_THIS_STRONG_PASSWORD"  # <-- Change this

# --- Step 1: System packages ---
echo "[1/8] Installing system packages..."
sudo apt update
sudo apt install -y python3 python3-pip python3-venv postgresql postgresql-contrib nginx git

# --- Step 2: PostgreSQL setup ---
echo "[2/8] Setting up PostgreSQL..."
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 || \
sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 || \
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"

# --- Step 3: Clone repo ---
echo "[3/8] Cloning repository..."
if [ -d "$APP_DIR" ]; then
    cd "$APP_DIR"
    git pull origin main
else
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

# --- Step 4: Virtual environment + dependencies ---
echo "[4/8] Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# --- Step 5: Create .env file ---
echo "[5/8] Creating .env file..."
if [ ! -f .env ]; then
    SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
    cat > .env << EOF
SECRET_KEY=$SECRET
DEBUG=False
ALLOWED_HOSTS=$DOMAIN,localhost,127.0.0.1
DATABASE_NAME=$DB_NAME
DATABASE_USER=$DB_USER
DATABASE_PASSWORD=$DB_PASS
DATABASE_HOST=localhost
DATABASE_PORT=5432

# OCR
AZURE_FORM_RECOGNIZER_ENDPOINT=
AZURE_FORM_RECOGNIZER_KEY=

# Odoo Integration
ODOO_URL=
ODOO_DB=
ODOO_USERNAME=
ODOO_PASSWORD=

# OpenAI
OPENAI_API_KEY=
EOF
    echo "  .env created - EDIT IT with your actual keys!"
else
    echo "  .env already exists, skipping."
fi

# --- Step 6: Django setup ---
echo "[6/8] Running Django setup..."
python manage.py collectstatic --noinput
python manage.py migrate
echo "  Creating superuser (if needed)..."
python manage.py shell -c "
from accounts.models import CustomUser
if not CustomUser.objects.filter(is_superuser=True).exists():
    CustomUser.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    print('  Superuser created: admin / admin123')
else:
    print('  Superuser already exists.')
"

# --- Step 7: Gunicorn service ---
echo "[7/8] Setting up Gunicorn service..."
sudo cp deploy/gunicorn.service /etc/systemd/system/invoice_platform.service
sudo systemctl daemon-reload
sudo systemctl enable invoice_platform
sudo systemctl restart invoice_platform

# --- Step 8: Nginx ---
echo "[8/8] Setting up Nginx..."
# Replace domain in nginx config
sed "s/YOUR_DOMAIN_OR_IP/$DOMAIN/g" deploy/nginx.conf | sudo tee /etc/nginx/sites-available/invoice_platform > /dev/null
sudo ln -sf /etc/nginx/sites-available/invoice_platform /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

echo ""
echo "=========================================="
echo "  DEPLOYMENT COMPLETE!"
echo "=========================================="
echo "  Site: http://$DOMAIN"
echo "  Admin: http://$DOMAIN/admin/"
echo ""
echo "  NEXT STEPS:"
echo "  1. Edit .env with your actual API keys"
echo "  2. Change the superuser password"
echo "  3. For SSL: sudo apt install certbot python3-certbot-nginx && sudo certbot --nginx -d $DOMAIN"
echo "=========================================="
