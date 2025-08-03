# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is Litour (formerly heltour), a Django-based tournament management web application for online chess tournaments. It manages chess tournaments, player registrations, team formations, game pairings, round scheduling, and score tracking. The application is branded as lots.lichess.ca (League of Teams and Schedules).

## Technology Stack

- **Backend**: Django 4.2.x with Python 3.11
- **Database**: PostgreSQL 15
- **Task Queue**: Celery 5.3.6 with Redis 7 broker
- **Frontend**: jQuery 3.1.0, Bootstrap 3, SCSS (compiled with Ruby sass)
- **Dependency Management**: Poetry
- **Task Runner**: Invoke (replaced Fabric)
- **Development Environment**: Nix with automatic setup
- **Services**: Docker Compose for PostgreSQL, Redis, MailHog

## Development Setup

### Getting Started
```bash
# Start the required services (PostgreSQL, Redis, MailHog)
invoke docker-up

# Enter the development environment (automatically sets up virtualenv and installs dependencies)
nix develop

# Create your local .env file from the development template
cp .env.dev .env

# Run initial setup
invoke migrate
invoke createsuperuser

# Start the development server
invoke runserver
```

The nix environment automatically:
- Sets up Python 3.11 virtual environment
- Installs all Python dependencies via Poetry
- Installs Ruby and the sass gem for SCSS compilation
- Configures all necessary paths and environment variables

### Common Development Tasks

```bash
# Docker services management
invoke docker-up        # Start PostgreSQL, Redis, MailHog
invoke docker-down      # Stop all services
invoke docker-status    # Check service status

# Database operations
invoke createdb         # Create new database
invoke migrate          # Run database migrations
invoke makemigrations   # Create new migrations

# Running the application
invoke runserver        # Run Django dev server on 0.0.0.0:8000
invoke runapiworker     # Run API worker on port 8880
invoke celery           # Run Celery worker for background tasks

# Dependency management
invoke update           # Update all dependencies to latest versions (alias: up)
poetry install          # Install dependencies (automatic in nix shell)
poetry add <package>    # Add new dependency

# Testing
invoke test             # Run all tests
invoke test heltour.tournament.tests.test_models # Run specific test module

# Static files
invoke compilestatic    # Compile SCSS files
invoke collectstatic    # Collect static files

# Development utilities
invoke shell            # Start Django shell
invoke createsuperuser  # Create a Django superuser
invoke status           # Check git status (alias: st)
```


## Architecture & Code Structure

### Main Application Structure

- `heltour/` - Main Django application
  - `tournament/` - Core tournament management app containing models, views, admin customizations
  - `api_worker/` - Background API worker application
  - `settings.py` - Single settings file using environment variables
  - `comments/` - Custom comments app

### Key Models (in `tournament/models.py`)

- `League`, `Season`, `Round` - Tournament structure
- `Player`, `Team`, `TeamMember` - Participant management
- `TeamPairing`, `PlayerPairing` - Game pairings
- `Registration`, `AlternateAssignment` - Registration system

### Environment Configuration

- All configuration is handled via environment variables using django-environ
- Copy `.env.dev` to `.env` for local development
- Settings are read from environment variables with sensible defaults
- API keys are read directly from environment variables
- Key environment files:
  - `.env.dev` - Development defaults (PostgreSQL, Redis, MailHog pre-configured)
  - `.env.example` - Template with all available settings

### External Service Integrations

- **Lichess API** - OAuth authentication and game data
- **Slack API** - Notifications
- **Google Sheets API** - Data export
- **Firebase Cloud Messaging** - Push notifications

## Code Style Guidelines

Follow `.editorconfig` settings:

- Python: 4 spaces indentation, max 100 chars per line
- HTML/SCSS: 4 spaces indentation
- JavaScript: 2 spaces for files under lib/
- UTF-8 encoding, LF line endings

## Testing

Tests are located in `heltour/tournament/tests/`. The project uses Django's unittest framework. Run specific test categories:

- Models: `test_models.py`
- Admin: `test_admin.py`
- API: `test_api.py`
- Views: `test_views.py`
- Background tasks: `test_tasks.py`

## Important Notes

- The application supports both team-based and individual (lone) tournament formats
- Celery workers handle background tasks like API syncing and notifications
- JaVaFo (Java tool) can be used for sophisticated pairing generation (located at `thirdparty/javafo.jar`)
- Task automation uses Invoke (replaced Fabric) - see `tasks.py` for available commands
- SCSS compilation requires Ruby sass gem (automatically installed in nix shell)
- The project was migrated from multiple settings files to a single environment-based configuration
- Branding has been updated from lichess4545 to lots.lichess.ca

## Historical Context

This project was originally called heltour and served lichess4545. It has been rebranded to Litour for lots.lichess.ca (Lichess Online Tournament System). The codebase still uses "heltour" in many places for backwards compatibility.
