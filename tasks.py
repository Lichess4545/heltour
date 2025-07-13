from invoke import task
from pathlib import Path

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.absolute()

# Note: .env file is automatically loaded by Django settings
# No need to load it here to avoid duplication


def project_relative(path):
    """Convert a relative path to an absolute path relative to the project root."""
    return str(PROJECT_ROOT / path)


@task
def update(c):
    """Update all dependencies to their latest versions using poetry."""
    c.run("poetry update")


@task
def runserver(c):
    """Run the Django development server on 0.0.0.0:8000."""
    manage_py = project_relative("manage.py")
    c.run(f"python -u {manage_py} runserver 0.0.0.0:8000", pty=True)


@task
def runapiworker(c):
    """Run the API worker server on port 8880."""
    manage_py = project_relative("manage.py")
    with c.prefix("export HELTOUR_APP=API_WORKER"):
        c.run(f"python {manage_py} runserver 0.0.0.0:8880")


@task
def celery(c):
    """Run Celery worker for background tasks."""
    c.run("celery -A heltour worker -l info", pty=True)


@task
def migrate(c):
    """Run Django database migrations."""
    manage_py = project_relative("manage.py")
    c.run(f"python {manage_py} migrate")


@task
def makemigrations(c):
    """Create new Django migrations."""
    manage_py = project_relative("manage.py")
    c.run(f"python {manage_py} makemigrations")


@task
def shell(c):
    """Start Django shell."""
    manage_py = project_relative("manage.py")
    c.run(f"python {manage_py} shell")


@task(help={"test": "Specific test module, class, or method to run"})
def test(c, test=""):
    """Run Django tests. Optionally specify a specific test path."""
    manage_py = project_relative("manage.py")
    test_cmd = f"python {manage_py} test --settings=heltour.test_settings"
    if test:
        c.run(f"{test_cmd} {test}")
    else:
        c.run(test_cmd)


@task
def collectstatic(c):
    """Collect static files."""
    manage_py = project_relative("manage.py")
    c.run(f"python {manage_py} collectstatic --noinput")


@task
def compilestatic(c):
    """Compile static files."""
    manage_py = project_relative("manage.py")
    c.run(f"python {manage_py} compilestatic")


@task
def createsuperuser(c):
    """Create a Django superuser."""
    manage_py = project_relative("manage.py")
    c.run(f"python {manage_py} createsuperuser", pty=True)


@task
def docker_up(c):
    """Start Docker Compose services (PostgreSQL, Redis, MailHog)."""
    c.run("docker compose up -d", pty=True)


@task
def docker_down(c):
    """Stop Docker Compose services."""
    c.run("docker compose down", pty=True)


@task
def docker_status(c):
    """Show status of Docker Compose services."""
    c.run("docker compose ps", pty=True)


@task(
    help={
        "tag": "Tag for the images (default: latest)",
        "registry": "Docker registry to prefix images with",
        "target": "Specific target to build (default: all including verify)",
        "push": "Push images after building",
        "production": "Build only production images (skip verify)",
    }
)
def docker_bake(c, tag="latest", registry="", target="", push=False, production=False):
    """Build Docker images using docker buildx bake."""
    env = {}

    if tag:
        env["TAG"] = tag

    if registry:
        env["REGISTRY"] = registry

    cmd = "docker buildx bake -f docker/docker-bake.hcl"

    if target:
        cmd += f" {target}"
    elif production:
        cmd += " production"
    # else: default group includes verify

    if push:
        cmd += " --push"

    env_str = " ".join(f"{k}={v}" for k, v in env.items())
    if env_str:
        cmd = f"{env_str} {cmd}"

    c.run(cmd, pty=True)


# Alias
docker_build = docker_bake


@task(
    help={
        "minimal": "Create minimal dataset for quick testing",
        "full": "Create full dataset with all features",
        "clear": "Clear existing data before seeding (USE WITH CAUTION!)",
        "leagues": "Number of leagues to create (default: 2)",
        "players": "Number of players to create (default: 50)",
    }
)
def seed(c, minimal=False, full=False, clear=False, leagues=2, players=50):
    """Seed the database with test data for development."""
    manage_py = project_relative("manage.py")

    cmd = f"python {manage_py} seed_database"

    if minimal:
        cmd += " --minimal"
    elif full:
        cmd += " --full"
    else:
        cmd += f" --leagues {leagues} --players {players}"

    if clear:
        cmd += " --clear"

    c.run(cmd, pty=True)


@task
def seed_minimal(c):
    """Seed database with minimal test data."""
    seed(c, minimal=True)


@task
def seed_full(c):
    """Seed database with full test data."""
    seed(c, full=True)


@task
def reset_db(c):
    """Reset database to empty state with migrations applied."""
    manage_py = project_relative("manage.py")

    # Get confirmation
    print("WARNING: This will DELETE ALL DATA in the database!")
    confirm = input("Are you sure you want to reset the database? (yes/no): ")

    if confirm.lower() != "yes":
        print("Aborted.")
        return

    # Use Django's flush command which truncates all tables but keeps structure
    print("Flushing database...")
    c.run(f"python {manage_py} flush --no-input", pty=True)

    # Run migrations to ensure everything is up to date
    print("Running migrations...")
    c.run(f"python {manage_py} migrate", pty=True)

    print(
        "Database reset complete. The database is now empty with all migrations applied."
    )


@task
def reset_db_hard(c):
    """Drop and recreate the database (PostgreSQL only)."""

    print("WARNING: This will DROP and RECREATE the database!")
    confirm = input(
        "Are you sure you want to completely recreate the database? (yes/no): "
    )

    if confirm.lower() != "yes":
        print("Aborted.")
        return

    # This requires appropriate PostgreSQL permissions
    # and assumes DATABASE_URL is set correctly
    print("Dropping and recreating database...")

    # Get database name from DATABASE_URL
    import os
    from urllib.parse import urlparse

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        return

    parsed = urlparse(db_url)
    db_name = parsed.path[1:]  # Remove leading slash

    if not db_name:
        print("ERROR: Could not parse database name from DATABASE_URL")
        return

    # Drop and recreate database
    c.run(f"dropdb {db_name} --if-exists", warn=True)
    c.run(f"createdb {db_name}")

    # Run migrations
    manage_py = project_relative("manage.py")
    print("Running migrations...")
    c.run(f"python {manage_py} migrate", pty=True)

    print(f"Database '{db_name}' recreated and migrations applied.")


# Shortcuts
up = update
