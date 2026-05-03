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
- **Development Environment**: devenv 2.x with automatic setup
- **Services**: PostgreSQL, Redis, and Mailpit run locally via `devenv up` (no Docker required for dev)

## Development Setup

### Getting Started

```bash
# Create your local .env file from the development template
cp .env.dev .env

# Enter the development environment (automatically sets up virtualenv and installs dependencies)
devenv shell

# Start all services and processes (postgres, redis, mailpit, django, apiworker, celery)
devenv up

# In another shell (also inside `devenv shell`), run initial setup
invoke migrate
invoke createsuperuser
```

The devenv shell automatically:

- Sets up Python 3.11 virtual environment
- Installs all Python dependencies via Poetry
- Installs Ruby and the sass gem for SCSS compilation
- Configures all necessary paths and environment variables

### Common Development Tasks

```bash
# Process orchestration (postgres, redis, mailpit, django, apiworker, celery, watch-games)
devenv up

# Database operations
invoke createdb         # Create new database
invoke migrate          # Run database migrations
invoke makemigrations   # Create new migrations

# Running individual processes (when not using `devenv up`)
invoke runserver        # Run Django dev server on 0.0.0.0:8000
invoke runapiworker     # Run API worker on port 8880
invoke celery           # Run Celery worker for background tasks

# Dependency management
invoke update           # Update all dependencies to latest versions (alias: up)
poetry install          # Install dependencies (automatic in devenv shell)
poetry add <package>    # Add new dependency

# Testing
invoke test             # Run all tests
invoke test -t heltour.tournament.tests.test_models # Run specific test module

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
  - `tournament_core/` - Pure Python tournament calculation library (no database dependencies)
  - `api_worker/` - Background API worker application
  - `settings.py` - Single settings file using environment variables
  - `comments/` - Custom comments app

### Key Models (in `tournament/models.py`)

- `League`, `Season`, `Round` - Tournament structure
- `Player`, `Team`, `TeamMember` - Participant management
- `TeamPairing`, `PlayerPairing` - Game pairings
- `Registration`, `AlternateAssignment` - Registration system

### Tournament Core Module (`tournament_core/`)

A clean, database-independent module for tournament calculations:

- **Structure** (`structure.py`):
  - `Game`, `Match`, `Round`, `Tournament` - Pure data classes using frozen dataclasses
  - Helper functions for creating matches (single game, team, bye)
  - Tournament calculation methods that return results

- **Tiebreaks** (`tiebreaks.py`):
  - `MatchResult`, `CompetitorScore` - Data classes for results
  - Tiebreak calculation functions: Sonneborn-Berger, Buchholz, Head-to-Head, Games Won
  - Functions work with both team and individual tournaments

- **Scoring** (`scoring.py`):
  - `ScoringSystem` - Configurable scoring (standard 2-1-0, alternative 3-1-0, etc.)
  - Handles game points, match points, and bye scoring

### Database to Structure Transformation (`tournament/db_to_structure.py`)

Functions to convert Django ORM models to tournament_core structures:

- `season_to_tournament_structure()` - Main entry point
- `team_tournament_to_structure()` - Handles team tournaments with board pairings
- `lone_tournament_to_structure()` - Handles individual tournaments
- Properly handles color alternation in team matches

### Environment Configuration

- All configuration is handled via environment variables using django-environ
- Copy `.env.dev` to `.env` for local development
- Settings are read from environment variables with sensible defaults
- API keys are read directly from environment variables
- Key environment files:
  - `.env.dev` - Development defaults (PostgreSQL, Redis, Mailpit pre-configured)
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

## Code Formatting

- **Ruff**: We use ruff for formatting this project
  - Ensure all code changes are formatted using ruff
  - This helps maintain consistent code style and readability

## Testing

Tests are located in `heltour/tournament/tests/`. The project uses Django's unittest framework. Run specific test categories:

- Models: `test_models.py`
- Admin: `test_admin.py`
- API: `test_api.py`
- Views: `test_views.py`
- Background tasks: `test_tasks.py`
- DB to Structure transformations: `test_db_to_structure.py`

Pure Python tests for tournament calculations are in `heltour/tournament_core/tests/`.

## Important Notes

- The application supports both team-based and individual (lone) tournament formats
- Celery workers handle background tasks like API syncing and notifications
- JaVaFo (Java tool) can be used for sophisticated pairing generation (located at `thirdparty/javafo.jar`)
- Task automation uses Invoke (replaced Fabric) - see `tasks.py` for available commands
- SCSS compilation requires Ruby sass gem (automatically installed in devenv shell)
- The project was migrated from multiple settings files to a single environment-based configuration
- Branding has been updated from lichess4545 to lots.lichess.ca

## Historical Context

This project was originally called heltour and served lichess4545. It has been rebranded to Litour for lots.lichess.ca (Lichess Online Tournament System). The codebase still uses "heltour" in many places for backwards compatibility.

## Important Instructions for Claude

### Command Execution Policy

- **DO NOT** run any commands - the user will run all commands themselves
- **DO NOT** use `devenv shell`, `invoke`, `poetry`, or any other shell commands
- **DO NOT** attempt to start servers, run tests, or execute any development tasks
- You should only:
  - Read and analyze code
  - Write and edit code files
  - Provide command suggestions when asked
  - Explain what commands would do

### Testing Policy

- **NEVER** run tests - the user will run tests themselves
- When test-related changes are made, you may suggest which test commands the user could run
- Do not assume tests need to be run after code changes

### Git Policy

- **NEVER** execute any git commands whatsoever
- **DO NOT** make commits, pushes, or any git operations
- Only use read-only git information that is provided in the environment
- If git information is needed, ask the user to provide it

### General Guidelines

- Focus solely on code reading, writing, and analysis
- The user will handle all command execution and environment setup
- Ask for clarification if needed before making assumptions
- Respect the existing code structure and patterns
- Do not create new files unless absolutely necessary

### Migration Policy

- **NEVER** create Django migration files manually
- **DO NOT** run makemigrations or migrate commands
- **DO NOT** create any files in migration directories
- When model changes are made, inform the user that they need to run makemigrations
- The user will handle all migration creation and execution

## Tournament Core Module and Testing

### Tournament Core Architecture

The `tournament_core` module provides a clean, database-independent representation of tournaments:

- **Pure Python Implementation**: No Django dependencies, just dataclasses and calculation logic
- **Key Components**:
  - `structure.py`: Defines `Game`, `Match`, `Round`, and `Tournament` dataclasses
  - `tiebreaks.py`: Implements tiebreak calculations (Sonneborn-Berger, Buchholz, Head-to-Head, Games Won)
  - `scoring.py`: Configurable scoring systems (standard 2-1-0, alternative 3-1-0, etc.)
  - `db_to_structure.py`: Transforms Django ORM models to tournament_core structures
  - `builder.py`: Fluent API for building tournament structures
  - `assertions.py`: Fluent assertion interface for testing tournament standings

### Testing Best Practices

#### Use Tournament Builder for Tests

The `tournament_core/builder.py` provides a fluent `TournamentBuilder` class for creating tournament structures easily:

```python
# Team tournament example
builder = TournamentBuilder()
builder.league("Test League", "TL", "team")
builder.season("TL", "Spring 2024", rounds=3, boards=2)
builder.team("Dragons", ("Alice", 2000), ("Bob", 1900))
builder.team("Knights", ("Charlie", 1950), ("David", 1850))
builder.round(1)
builder.match("Dragons", "Knights", "1-0", "1/2-1/2")  # Dragons win 1.5-0.5
builder.complete()
tournament = builder.build()

# Individual tournament example
builder = TournamentBuilder()
builder.league("Chess Club", "CC", "lone")
builder.season("CC", "Winter 2024", rounds=3)
builder.player("Alice", 2100)
builder.player("Bob", 2000)
builder.round(1)
builder.game("Alice", "Bob", "1-0")
builder.complete()
tournament = builder.build()
```

#### Fluent Assertion Interface

The `tournament_core/assertions.py` provides a fluent interface for testing tournament standings:

```python
from heltour.tournament_core.assertions import assert_tournament

# Assert team tournament standings
assert_tournament(tournament).team("Dragons").assert_()
    .wins(2).losses(0).draws(1)
    .match_points(5).game_points(4.5)
    .games_won(3)  # For team tournaments
    .position(1)

# Assert individual tournament standings
assert_tournament(tournament).player("Alice").assert_()
    .wins(2).losses(1).draws(0)
    .match_points(4).game_points(2.0)
    .byes(1)
    .position(2)

# Assert tiebreak scores
assert_tournament(tournament).player("Alice").assert_()
    .tiebreak("sonneborn_berger", 3.5)
    .tiebreak("buchholz", 6.0)
```

**Important Notes for Team Tournament Assertions**:

- Match results are provided from the first team's perspective
- `"1-0"` means the first team's player wins on that board
- On alternating boards (odd-numbered), colors are swapped automatically
- Example: `.match("Dragons", "Knights", "1-0", "1-0")` means Dragons win both boards

#### Database Test Requirements

- **Team Tournaments MUST Have Board Pairings**: The system will error if TeamPairing objects lack TeamPlayerPairing children
- **Avoid Circular Dependencies**: Create rounds as `is_completed=False`, add all pairings and board results, then mark as completed
- **No Synthetic Data**: The system does not support aggregate-only scores; all results must come from actual games

#### Testing Workflow

1. For pure logic tests, use `tournament_core` structures directly
2. For integration tests, create complete database structures with board pairings
3. Use `season_to_tournament_structure()` to convert database models to tournament_core
4. All calculations flow through the tournament_core module for consistency

### Important Design Decisions

1. **No Legacy Support**: We don't support "legacy matches" - all team matches must have board results
2. **Clean Error Handling**: The system raises clear errors when data is incomplete rather than guessing
3. **Immutable Structures**: Tournament_core uses frozen dataclasses for thread safety and clarity
4. **Separation of Concerns**: Database models handle persistence; tournament_core handles calculations
5. **Name Mappings**: The builder adds `name_to_id` mappings to tournaments for assertion convenience

### Future Testing Improvements

The goal is to make tournament testing simple and reliable:

- Expand `TournamentBuilder` with more convenience methods
- Create fixture generators for common tournament scenarios
- Add property-based testing for tiebreak calculations
- Ensure all edge cases (byes, forfeits, odd player counts) are well-tested
