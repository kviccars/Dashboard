#!/bin/bash

# Exit on any error
set -e

echo "Starting Django application..."

# Create database directory if it doesn't exist
mkdir -p /app/data

# Set proper permissions for the database directory
chmod 755 /app/data

# Check if database file exists, if not create it
if [ ! -f "/app/data/db.sqlite3" ]; then
    echo "Creating new database file..."
    touch /app/data/db.sqlite3
    chmod 664 /app/data/db.sqlite3
fi

# Run database migrations
echo "Running database migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Create superuser if it doesn't exist (optional)
echo "Creating superuser if needed..."
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    print('Creating superuser admin...')
    User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    print('Superuser created successfully')
else:
    print('Superuser already exists')
" || true

echo "Starting Gunicorn server..."
exec "$@"
