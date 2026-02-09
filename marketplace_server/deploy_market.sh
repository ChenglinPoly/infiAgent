#!/usr/bin/env bash
set -euo pipefail

# Deploy infiAgent Marketplace to a remote Linux server.
#
# Requirements:
# - SSH key auth (no interactive password)
# - Remote has systemd + nginx (script can install via apt if Debian/Ubuntu)
#
# Usage:
#   ./deploy_market.sh root@101.200.231.88
#
# Optional env:
#   REMOTE_DIR=/opt/infiagent-market
#   MARKET_PORT=18080
#   NGINX_PORT=80

TARGET="${1:-}"
if [[ -z "${TARGET}" ]]; then
  echo "Usage: $0 user@host"
  exit 1
fi

REMOTE_DIR="${REMOTE_DIR:-/opt/infiagent-market}"
MARKET_PORT="${MARKET_PORT:-18080}"
NGINX_PORT="${NGINX_PORT:-80}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[deploy] repo_root: ${REPO_ROOT}"
echo "[deploy] target: ${TARGET}"
echo "[deploy] remote_dir: ${REMOTE_DIR}"

# Upload only what we need
echo "[deploy] uploading files..."
rsync -av --delete \
  --exclude ".git/" \
  --exclude "desktop_app/" \
  --exclude "backend_build/" \
  --exclude "web_ui/" \
  --exclude "tests/" \
  --exclude "__pycache__/" \
  "${REPO_ROOT}/marketplace_server/" \
  "${REPO_ROOT}/skills/" \
  "${REPO_ROOT}/config/agent_library/" \
  "${TARGET}:${REMOTE_DIR}/"

echo "[deploy] provisioning remote..."
ssh -o StrictHostKeyChecking=accept-new "${TARGET}" bash -s <<EOF
set -euo pipefail

REMOTE_DIR="${REMOTE_DIR}"
MARKET_PORT="${MARKET_PORT}"
NGINX_PORT="${NGINX_PORT}"

cd "\${REMOTE_DIR}"

# Best-effort install deps (Debian/Ubuntu). If not available, user can install manually.
if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y python3 python3-venv python3-pip nginx
fi

# Python venv for marketplace
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r marketplace_server/requirements.txt

# systemd service
sed "s|/opt/infiagent-market|\${REMOTE_DIR}|g; s|--port 18080|--port \${MARKET_PORT}|g" marketplace_server/infiagent-market.service > /etc/systemd/system/infiagent-market.service
systemctl daemon-reload
systemctl enable --now infiagent-market

# nginx reverse proxy on port 80
cat > /etc/nginx/conf.d/infiagent_market.conf <<NGINX
server {
    listen ${NGINX_PORT};
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:${MARKET_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
NGINX

nginx -t
systemctl reload nginx

echo "[deploy] done. health check:"
curl -s "http://127.0.0.1:\${NGINX_PORT}/api/v1/health" || true
EOF

echo "[deploy] finished."

