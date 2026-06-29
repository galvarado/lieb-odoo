#!/bin/bash
set -e

HOST="33629308@lieb-18-0-staging-33629308.dev.odoo.com"
REMOTE="/home/odoo/src/user/lieb_puros_heridos/"
LOCAL="$(dirname "$0")/lieb_puros_heridos/"

rsync -avz --delete \
  --exclude="__pycache__" \
  --exclude="*.pyc" \
  "$LOCAL" "$HOST:$REMOTE"

echo ""
echo "Sync done. Run on server:"
echo "  ssh $HOST 'odoo-update lieb_puros_heridos'"
