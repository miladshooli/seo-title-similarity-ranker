#!/usr/bin/env bash
# One-shot installer for Debian/Ubuntu. Run as root.
# Usage: SEARCHAPI_KEY=xxxx bash deploy/setup.sh
set -euo pipefail

APP_DIR=/opt/jina-ranker
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Installing system packages (flask, requests, gunicorn, nginx)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y python3-flask python3-requests gunicorn nginx

echo "==> Copying app to $APP_DIR"
mkdir -p "$APP_DIR/templates"
cp "$REPO_DIR/app.py" "$APP_DIR/app.py"
cp "$REPO_DIR/templates/index.html" "$APP_DIR/templates/index.html"

echo "==> Installing systemd service"
cp "$REPO_DIR/deploy/jina-ranker.service" /etc/systemd/system/jina-ranker.service
# Inject optional server-side default keys only if provided as env vars
for v in SEARCHAPI_KEY SERPER_KEY JINA_API_KEY; do
  val="${!v:-}"
  [ -n "$val" ] && sed -i "/^\[Service\]/a Environment=\"$v=$val\"" /etc/systemd/system/jina-ranker.service
done

echo "==> Installing nginx site"
cp "$REPO_DIR/deploy/nginx.conf" /etc/nginx/sites-available/jina-ranker
ln -sf /etc/nginx/sites-available/jina-ranker /etc/nginx/sites-enabled/jina-ranker
rm -f /etc/nginx/sites-enabled/default

echo "==> Starting services"
systemctl daemon-reload
systemctl enable --now jina-ranker
nginx -t && systemctl restart nginx

echo "==> Done. App is on http://<server-ip>/"
echo "    For HTTPS:  certbot --nginx -d your.domain.com --redirect"
