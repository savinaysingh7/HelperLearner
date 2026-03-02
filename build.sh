#!/usr/bin/env bash
# Build script for Render.com deployments.
# Runs on every deploy: install deps → collect static → migrate DB.

set -o errexit  # exit on error

echo "==> Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Collecting static files..."
python manage.py collectstatic --no-input

echo "==> Running database migrations..."
python manage.py migrate --no-input

echo "==> Build complete!"
