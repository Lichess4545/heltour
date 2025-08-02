# Litour (formerly heltour)

League management software for chess leagues on Lichess, now branded as lots.lichess.ca.

# Quick Start

## Prerequisites

- Docker and Docker Compose
- Nix (for development environment)

## Development Setup

```bash
# 1. Start the required services (PostgreSQL, Redis, MailHog)
invoke docker-up

# 2. Copy the development environment file
cp .env.dev .env

# 3. Enter the nix development environment
nix develop

# 4. Run database migrations
invoke migrate

# 5. Create a superuser account
invoke createsuperuser

# 6. Start the development server
invoke runserver
```

The site will be available at <http://localhost:8000>

### Additional Services

- **MailHog Web UI**: <http://localhost:8025> (view sent emails)
- **API Worker** (optional): `invoke runapiworker` (runs on port 8880)
- **Celery Worker** (optional): `invoke celery` (runs background tasks)

## Common Development Commands

```bash
# Docker services management
invoke docker-up      # Start PostgreSQL, Redis, MailHog
invoke docker-down    # Stop all services
invoke docker-status  # Check service status

# Django commands
invoke runserver      # Start dev server on 0.0.0.0:8000
invoke migrate        # Run database migrations
invoke makemigrations # Create new migrations
invoke shell          # Django shell
invoke test           # Run tests
invoke collectstatic  # Collect static files
invoke compilestatic  # Compile SCSS files

# Dependencies
invoke update         # Update all dependencies via Poetry
```

## Configuration

All configuration is done through environment variables. The `.env.dev` file contains defaults for local development.

Key settings:

- Database: PostgreSQL on localhost:5432
- Redis: localhost:6379
- Email: MailHog on localhost:1025 (SMTP) / 8025 (Web UI)
- Static files: SCSS compilation via Ruby sass gem (auto-installed in nix shell)

## Development Tips

- The nix environment automatically installs all required tools including Python 3.11, Poetry, Ruby, and sass
- Virtual environment is created automatically when entering nix shell
- Ensure that your editor has an [EditorConfig plugin](https://editorconfig.org/#download) enabled
- JaVaFo pairing tool is included in `thirdparty/javafo.jar`

## Stopping Services

```bash
# Stop services but keep data
invoke docker-down

# Stop services and remove all data
docker compose down -v
```

## Historical Note

This project was previously known as heltour and served lichess4545. It has been rebranded to support lots.lichess.ca (Lichess Online Tournament System).
