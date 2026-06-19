from invoke import task
from pathlib import Path
import os
import environ

from django.conf import settings
from heltour.tournament.lichessapi import test_oauth_token, test_whoami

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.absolute()

# Initialize environ
env = environ.Env()

# Read .env file if it exists
environ.Env.read_env(os.path.join(PROJECT_ROOT, ".env"))


def project_relative(path):
    """Convert a relative path to an absolute path relative to the project root."""
    return str(PROJECT_ROOT / path)


@task
def tokentest(c):
    result = test_oauth_token(settings.LICHESS_API_TOKEN)
    print("Token test result:", result)


@task
def whoami(c):
    result = test_whoami()
    print("Whoami test result:", result)


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
    with c.prefix("export HELTOUR_APP=api_worker"):
        c.run(f"python {manage_py} runserver 0.0.0.0:8880")


@task
def runapi(c):
    """Run the new FastAPI service (heltour.api) on port 8001."""
    # Bind to :: so both IPv4 (via mapped) and IPv6 work — Firefox prefers ::1
    # for `localhost` and silently fails with NS_ERROR_CONNECT_REFUSED if we
    # only bind 0.0.0.0.
    c.run(
        "uvicorn heltour.api.main:app --reload --host :: --port 8001",
        pty=True,
    )


@task
def openapi(c):
    """Export the FastAPI OpenAPI schema to ./openapi.json."""
    script = project_relative("scripts/export_openapi.py")
    c.run(f"python {script} > openapi.json")


@task
def fuzz(c, base_url="http://localhost:8001"):
    """Run Schemathesis against a running API service."""
    c.run(
        f"schemathesis run --experimental=openapi-3.1 "
        f"--base-url={base_url} openapi.json",
        pty=True,
    )


@task(help={"skip_install": "Skip 'bun install' (use existing node_modules)."})
def build_api_client(c, skip_install=False):
    """Generate the OpenAPI schema, bundle the TS API client, copy into static."""
    openapi(c)
    frontend_dir = project_relative("frontend")
    api_client_dir = project_relative("frontend/api-client")
    static_js_dir = project_relative("heltour/tournament/static/tournament/js")
    os.makedirs(static_js_dir, exist_ok=True)
    if not skip_install:
        with c.cd(frontend_dir):
            c.run("bun install", pty=True)
    with c.cd(api_client_dir):
        c.run("bun run generate", pty=True)
        c.run("bun run bundle", pty=True)
    for name in ("litour-api-client.iife.js", "litour-api-client.iife.js.map"):
        src = os.path.join(api_client_dir, "dist", name)
        if os.path.exists(src):
            c.run(f"cp {src} {static_js_dir}/")


@task
def run_ui(c):
    """Run the Next.js UI dev server (frontend/ui) on port 3000."""
    ui_dir = project_relative("frontend/ui")
    with c.cd(ui_dir):
        c.run("bun run dev", pty=True)


@task(help={"purge": "Delete all heltour tasks."})
def celery(c, purge=False):
    """Run Celery worker for background tasks."""
    if purge:
        c.run("celery -A heltour purge")
    else:
        c.run("celery -A heltour worker -l info", pty=True)


@task
def watch_games(c):
    """Stream lichess games for active pairings and update them in real time."""
    manage_py = project_relative("manage.py")
    c.run(f"python -u {manage_py} watch_games", pty=True)


@task(
    optional=["app"],
    help={"app": "Optionally specify app or specific migration, e.g. 'invoke migrate -a \"tournament 0001\"'"},
)
def migrate(c, app=""):
    """Run Django database migrations."""
    manage_py = project_relative("manage.py")
    migrate_cmd = f"python {manage_py} migrate"
    c.run(f"{migrate_cmd} {app}")


@task
def makemigrations(c):
    """Create new Django migrations."""
    manage_py = project_relative("manage.py")
    c.run(f"python {manage_py} makemigrations")


@task(
    optional=["app"],
    help={"app": "Optionally specify app."}
)
def showmigrations(c, app=""):
    """Show Django database migrations."""
    manage_py = project_relative("manage.py")
    show_cmd = f"python {manage_py} showmigrations"
    c.run(f"{show_cmd} {app}")


@task
def shell(c):
    """Start Django shell."""
    manage_py = project_relative("manage.py")
    c.run(f"python {manage_py} shell", pty=True)


@task(
    help={"tests": "Specific test module(s), class(es), or method(s) to run"},
    iterable=["tests"]
)
def test(c, tests=None):
    """Run Django tests. Optionally specify test path(s)."""
    manage_py = project_relative("manage.py")
    test_cmd = f"python {manage_py} test --settings=heltour.test_settings"
    if tests:
        # Join all test paths with spaces
        test_paths = " ".join(tests)
        c.run(f"{test_cmd} {test_paths}")
    else:
        c.run(test_cmd)


@task
def collectstatic(c):
    """Collect static files."""
    manage_py = project_relative("manage.py")
    c.run(f"python {manage_py} collectstatic --noinput")


@task
def compilescss(c):
    """Compile SCSS files to CSS for production."""
    manage_py = project_relative("manage.py")
    c.run(f"python {manage_py} compilescss")


@task
def createsuperuser(c):
    """Create a Django superuser."""
    manage_py = project_relative("manage.py")
    c.run(f"python {manage_py} createsuperuser", pty=True)


@task(
    help={
        "username": "Username (default: admin)",
        "password": "Password (default: test12345)",
        "email": "Email (default: admin@example.com)",
    }
)
def make_admin(c, username="admin", password="test12345", email="admin@example.com"):
    """Create or update a Django superuser non-interactively (default: admin / test12345)."""
    import shlex

    manage_py = project_relative("manage.py")
    script = (
        "from django.contrib.auth import get_user_model; "
        "U = get_user_model(); "
        f"u, created = U.objects.update_or_create("
        f"username={username!r}, "
        f"defaults={{'email': {email!r}, 'is_staff': True, "
        f"'is_superuser': True, 'is_active': True}}); "
        f"u.set_password({password!r}); u.save(); "
        "print(('Created' if created else 'Updated') + ' superuser ' + u.username)"
    )
    c.run(f"python {manage_py} shell -c {shlex.quote(script)}", pty=True)


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
    from urllib.parse import urlparse

    db_url = env.str("DATABASE_URL", default="")
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        return

    parsed = urlparse(db_url)
    db_name = parsed.path[1:]  # Remove leading slash
    db_host = parsed.hostname or "localhost"
    db_port = parsed.port or 5432
    db_user = parsed.username or ""
    db_pass = parsed.password or ""

    if not db_name:
        print("ERROR: Could not parse database name from DATABASE_URL")
        return

    # Build connection parameters
    conn_params = []
    if db_host:
        conn_params.append(f"--host={db_host}")
    if db_port:
        conn_params.append(f"--port={db_port}")
    if db_user:
        conn_params.append(f"--username={db_user}")
    
    conn_string = " ".join(conn_params)
    
    # Set PGPASSWORD environment variable for the commands
    env_vars = ""
    if db_pass:
        env_vars = f"PGPASSWORD='{db_pass}' "

    # Drop and recreate database
    c.run(f"{env_vars}dropdb {conn_string} {db_name} --if-exists", warn=True)
    c.run(f"{env_vars}createdb {conn_string} {db_name}")

    # Run migrations
    manage_py = project_relative("manage.py")
    print("Running migrations...")
    c.run(f"python {manage_py} migrate", pty=True)

    print(f"Database '{db_name}' recreated and migrations applied.")


@task(
    help={
        "dump_file": "Path to a specific .dump file (default: latest wucc_backup_*.dump in project root)",
        "yes": "Skip the confirmation prompt",
    }
)
def restore_db(c, dump_file=None, yes=False):
    """Restore the local database from a pg_dump custom-format (-F c) backup.

    Drops and recreates the database referenced by DATABASE_URL, then
    pg_restores the dump into it.
    """
    import glob
    from urllib.parse import urlparse

    if dump_file is None:
        candidates = sorted(glob.glob(project_relative("wucc_backup_*.dump")))
        if not candidates:
            print(
                "ERROR: No wucc_backup_*.dump files found in the project root. "
                "Pass --dump-file=<path> to specify one explicitly."
            )
            return
        # Filenames embed YYYYMMDD_HHMMSS, so lexicographic sort == chronological.
        dump_file = candidates[-1]

    if not os.path.isfile(dump_file):
        print(f"ERROR: Dump file not found: {dump_file}")
        return

    db_url = env.str("DATABASE_URL", default="")
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        return

    parsed = urlparse(db_url)
    db_name = parsed.path[1:]
    db_host = parsed.hostname or "localhost"
    db_port = parsed.port or 5432
    db_user = parsed.username or ""
    db_pass = parsed.password or ""

    if not db_name:
        print("ERROR: Could not parse database name from DATABASE_URL")
        return

    print(f"Will restore from: {dump_file}")
    print(f"Target: {db_user}@{db_host}:{db_port}/{db_name}")
    print("WARNING: This will DROP and RECREATE the local database!")
    if not yes:
        confirm = input("Continue? (yes/no): ")
        if confirm.lower() != "yes":
            print("Aborted.")
            return

    conn_params = []
    if db_host:
        conn_params.append(f"--host={db_host}")
    if db_port:
        conn_params.append(f"--port={db_port}")
    if db_user:
        conn_params.append(f"--username={db_user}")
    conn_string = " ".join(conn_params)

    env_vars = ""
    if db_pass:
        env_vars = f"PGPASSWORD='{db_pass}' "

    print(f"Dropping database '{db_name}'...")
    c.run(
        f"{env_vars}dropdb {conn_string} {db_name} --if-exists",
        warn=True,
    )
    print(f"Creating database '{db_name}'...")
    c.run(f"{env_vars}createdb {conn_string} {db_name}")
    print(f"Restoring from {dump_file}...")
    c.run(
        f"{env_vars}pg_restore {conn_string} --dbname={db_name} "
        f"--no-owner --no-privileges --verbose '{dump_file}'",
        pty=True,
    )
    print(f"Database '{db_name}' restored from {dump_file}")


@task
def docker_stage_up(c, build=False):
    if build:
        c.run("docker compose -f deploy/litour-staging/compose.yml up -d --build", pty=True)
    else:
        c.run("docker compose -f deploy/litour-staging/compose.yml up -d", pty=True)


@task
def docker_stage_down(c):
    c.run("docker compose -f deploy/litour-staging/compose.yml down", pty=True)


@task(
    help={
        "league_name": "League name (default: Lone Test League)",
        "season_name": "Season name (default: Test Season)",
        "rounds": "Number of rounds (default: 7)",
        "players": "Number of players (default: 400)",
        "clear": "Clear existing league data first",
        "pairing_type": "Pairing algorithm: swiss-dutch or swiss-dutch-baku-accel",
    }
)
def seed_lone(
    c,
    league_name="Lone Test League",
    season_name="Test Season",
    rounds=7,
    players=400,
    clear=False,
    pairing_type="swiss-dutch",
):
    """Seed a test lone (individual Swiss) tournament."""
    manage_py = project_relative("manage.py")
    cmd = (
        f"python {manage_py} seed_test_lone_tournament"
        f" --league-name '{league_name}'"
        f" --season-name '{season_name}'"
        f" --rounds {rounds}"
        f" --players {players}"
        f" --pairing-type {pairing_type}"
    )
    if clear:
        cmd += " --clear-existing"
    c.run(cmd, pty=True)


@task(
    help={
        "base_url": "FastAPI base URL for schemathesis (default: http://localhost:8001).",
    }
)
def preflight(c, base_url="http://localhost:8001"):
    """Run every CI check back-to-back. Assumes `invoke runapi` is running.

    Mirrors `.github/workflows/api-contract.yml` plus the Django test suite.
    Each step runs even if a previous one fails; a non-zero exit is returned
    if anything failed, with a summary at the end.
    """
    frontend_dir = project_relative("frontend")
    api_client_dir = project_relative("frontend/api-client")
    ui_dir = project_relative("frontend/ui")

    steps: list[tuple[str, str, str | None]] = [
        ("export openapi.json", f"python {project_relative('scripts/export_openapi.py')} > openapi.json", None),
        ("schemathesis", f"schemathesis run --experimental=openapi-3.1 --base-url={base_url} openapi.json", None),
        ("frontend install", "bun install --frozen-lockfile", frontend_dir),
        ("regenerate ts client", "bun run generate", api_client_dir),
        ("typecheck api-client", "bun run typecheck", api_client_dir),
        ("build api-client", "bun run build", api_client_dir),
        ("bundle api-client", "bun run bundle", api_client_dir),
        ("lint api-client", "bun run lint", api_client_dir),
        ("typecheck ui", "bun run typecheck", ui_dir),
        ("lint ui", "bun run lint", ui_dir),
        ("generated.ts drift check", "git diff --exit-code frontend/api-client/src/generated.ts", None),
        # Django tests last — slowest step, so fast-failing checks surface first.
        ("django tests", f"python {project_relative('manage.py')} test --settings=heltour.test_settings", None),
    ]

    results: list[tuple[str, bool]] = []
    for name, cmd, cwd in steps:
        print(f"\n=== {name} ===")
        if cwd is not None:
            with c.cd(cwd):
                result = c.run(cmd, warn=True, pty=True)
        else:
            result = c.run(cmd, warn=True, pty=True)
        results.append((name, result.ok))

    print("\n=== preflight summary ===")
    for name, ok in results:
        print(f"  {'OK  ' if ok else 'FAIL'}  {name}")

    if any(not ok for _, ok in results):
        from invoke.exceptions import Exit
        raise Exit("preflight: one or more checks failed", code=1)


# Shortcuts
up = update
