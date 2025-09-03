# Django Dashboard Docker Setup

This directory contains everything needed to run the Django Dashboard application in Docker containers.

## Files Created

- **Dockerfile**: Main container definition
- **docker-compose.yml**: Multi-container orchestration
- **.dockerignore**: Files to exclude from Docker build
- **entrypoint.sh**: Startup script for database migrations and setup
- **DOCKER_README.md**: This documentation

## Quick Start

### Option 1: Using Docker Compose (Recommended)

```bash
# Navigate to the Django project directory
cd Dashboard

# Build and start the application
docker-compose up --build

# Run in background
docker-compose up -d --build

# View logs
docker-compose logs -f web

# Stop the application
docker-compose down
```

### Option 2: Using Docker directly

```bash
# Navigate to the Django project directory
cd Dashboard

# Build the image
docker build -t django-dashboard .

# Run the container (uses a named volume for DB persistence)
docker volume create dashboard_db_data
docker run -p 8000:8000 \
  -v dashboard_db_data:/app/data \
  -e DOCKER_ENV=1 \
  --name dashboard \
  django-dashboard

# Run in background
docker run -d -p 8000:8000 \
  -v dashboard_db_data:/app/data \
  -e DOCKER_ENV=1 \
  --name dashboard \
  django-dashboard
```

## Access the Application

Once running, access the application at:
- **Main App**: http://localhost:8000
- **Admin Panel**: http://localhost:8000/admin

### Default Credentials
The entrypoint script creates a default superuser:
- **Username**: admin
- **Password**: admin123
- **Email**: admin@example.com

**⚠️ Change these credentials in production!**

## Environment Variables

You can customize the deployment with environment variables:

```bash
# Example with custom settings
docker run -p 8000:8000 \
  -e DEBUG=0 \
  -e DJANGO_SETTINGS_MODULE=Dashboard.settings \
  django-dashboard
```

## Data Persistence

The Docker setup includes:
- **SQLite Database**: Stored in `/data` directory, mounted as a volume to persist data
- **Static Files**: Collected automatically on startup
- **Automatic Database Creation**: Database file is created automatically if it doesn't exist

## Development vs Production

### Development
```bash
# Navigate to Dashboard directory and use docker-compose for development
cd Dashboard
docker-compose up --build
```

### Production
```bash
# Navigate to Dashboard directory and use specific production settings
cd Dashboard
docker run -p 8000:8000 \
  -e DEBUG=0 \
  -e ALLOWED_HOSTS=your-domain.com \
  -e DOCKER_ENV=1 \
  -v dashboard_db_data:/app/data \
  --name dashboard \
  django-dashboard
```

## Container Features

- **Health Checks**: Automatic health monitoring
- **Non-root User**: Runs as 'appuser' for security
- **Automatic Migrations**: Database setup on startup
- **Static Files**: Automatically collected
- **Gunicorn**: Production WSGI server with 3 workers

## Troubleshooting

### View Container Logs
```bash
# Docker Compose
docker-compose logs web

# Direct Docker
docker logs dashboard
```

### Access Container Shell
```bash
# Docker Compose
docker-compose exec web bash

# Direct Docker
docker exec -it dashboard bash
```

### Rebuild After Changes
```bash
# Docker Compose
docker-compose down
docker-compose up --build

# Direct Docker
docker stop dashboard
docker rm dashboard
docker build -t django-dashboard .
docker run -p 8000:8000 django-dashboard
```

## Security Notes

1. **Change default admin credentials** after first login
2. **Set proper ALLOWED_HOSTS** for production
3. **Use environment variables** for sensitive settings
4. **Consider using PostgreSQL** for production instead of SQLite
5. **Set DEBUG=0** in production

## Microsoft 365 Configuration

After starting the container, configure your Microsoft 365 settings:

1. Go to http://localhost:8000/settings/
2. Enter your:
   - Tenant ID
   - Client ID  
   - Client Secret
   - SharePoint Hostname
   - Timesheet Site Path
   - Timesheet List Name

The application will then be able to connect to your SharePoint data.
