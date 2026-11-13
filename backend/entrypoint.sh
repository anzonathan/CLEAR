#!/bin/bash
set -e

echo "Running migrations..."
python manage.py migrate --noinput

echo "Seeding initial users..."
python manage.py seed_users

echo "Starting Daphne server..."
exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
