from invoke import task
from pathlib import Path
import os
import environ

PROJECT_ROOT = Path(__file__).parent.absolute()

env = environ.Env()
environ.Env.read_env(os.path.join(PROJECT_ROOT, ".env"))


def project_relative(path):
    return str(PROJECT_ROOT / path)


@task
def update(c):
    """Update all dependencies to their latest versions using poetry."""
    c.run("poetry update")


@task
def runserver(c, port=8000):
    """Run the Django development server on 0.0.0.0:<port> (default 8000; devenv passes its allocated port)."""
    manage_py = project_relative("manage.py")
    c.run(f"python -u {manage_py} runserver 0.0.0.0:{port}", pty=True)


@task
def runapiworker(c, port=8880):
    """Run the API worker on 0.0.0.0:<port> (default 8880; devenv passes its allocated port). HELTOUR_APP=api_worker swaps in heltour.api_worker's urls/apps."""
    manage_py = project_relative("manage.py")
    with c.prefix("export HELTOUR_APP=api_worker"):
        c.run(f"python {manage_py} runserver 0.0.0.0:{port}")


@task
def celery(c, purge=False):
    """Run the Celery worker; --purge discards all pending tasks on the broker instead."""
    if purge:
        c.run("celery -A heltour purge")
    else:
        c.run("celery -A heltour worker -l info", pty=True)


@task(optional=["app"])
def migrate(c, app=""):
    """Run Django database migrations, optionally scoped to one app/migration."""
    manage_py = project_relative("manage.py")
    migrate_cmd = f"python {manage_py} migrate"
    c.run(f"{migrate_cmd} {app}")


@task
def makemigrations(c):
    """Create new Django migrations."""
    manage_py = project_relative("manage.py")
    c.run(f"python {manage_py} makemigrations")


@task(optional=["app"])
def showmigrations(c, app=""):
    """Show Django migration status, optionally scoped to one app."""
    manage_py = project_relative("manage.py")
    show_cmd = f"python {manage_py} showmigrations"
    c.run(f"{show_cmd} {app}")


@task
def shell(c):
    """Start the Django shell."""
    manage_py = project_relative("manage.py")
    c.run(f"python {manage_py} shell", pty=True)


@task(iterable=["tests"])
def test(c, tests=None):
    """Run the Django test suite, optionally scoped to specific test paths."""
    manage_py = project_relative("manage.py")
    test_cmd = f"python {manage_py} test --settings=heltour.test_settings"
    if tests:
        test_paths = " ".join(tests)
        c.run(f"{test_cmd} {test_paths}")
    else:
        c.run(test_cmd)


@task
def seed(c, flush=False):
    """Seed a small set of demo leagues (team, LoneWolf-style, Chess960-rated) for manual testing."""
    manage_py = project_relative("manage.py")
    cmd = f"python {manage_py} seed_test_data"
    if flush:
        cmd += " --flush"
    c.run(cmd, pty=True)


@task
def collectstatic(c):
    """Collect static files."""
    manage_py = project_relative("manage.py")
    c.run(f"python {manage_py} collectstatic --noinput")


@task
def compilescss(c):
    """Compile SCSS to CSS via django-sass-processor."""
    manage_py = project_relative("manage.py")
    c.run(f"python {manage_py} compilescss")


@task
def createsuperuser(c):
    """Create a Django superuser interactively."""
    manage_py = project_relative("manage.py")
    c.run(f"python {manage_py} createsuperuser", pty=True)


@task
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


@task
def docker_bake(c, tag="latest", registry="", target="", push=False, production=False):
    """Build Docker images via `docker buildx bake -f docker/docker-bake.hcl`."""
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

    if push:
        cmd += " --push"

    env_str = " ".join(f"{k}={v}" for k, v in env.items())
    if env_str:
        cmd = f"{env_str} {cmd}"

    c.run(cmd, pty=True)


# A plain variable, not @task(aliases=[...]) — invoke registers tasks by their
# own name, so this doesn't show up in `invoke --list` and `invoke docker-build`
# won't work. Use `invoke docker-bake`.
docker_build = docker_bake


DOCKER_TEST_COMPOSE = (
    "docker compose -f docker/compose.test.yml -p heltour-test "
    "--env-file docker/compose.test.env"
)


@task
def docker_test_up(c, build=True):
    """Build local images and bring up docker/compose.test.yml -- a local (non-Swarm) harness on http://localhost:8090."""
    if build:
        c.run("docker buildx bake -f docker/docker-bake.hcl production", pty=True)
    c.run(f"{DOCKER_TEST_COMPOSE} up -d", pty=True)
    print("Waiting for the site to come up on http://localhost:8090 ...")
    c.run(
        "for i in $(seq 1 60); do "
        "code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8090/ || true); "
        "case \"$code\" in 200|302) exit 0 ;; esac; "
        "sleep 2; "
        "done; "
        "echo 'Timed out waiting for http://localhost:8090' >&2; exit 1",
        pty=True,
    )
    print("heltour test stack is up: http://localhost:8090")
    print("Run `invoke docker-test-seed` to populate demo leagues.")


@task
def docker_test_seed(c, flush=False):
    """Run seed_test_data inside the running docker/compose.test.yml web container."""
    cmd = f"{DOCKER_TEST_COMPOSE} exec web python manage.py seed_test_data"
    if flush:
        cmd += " --flush"
    c.run(cmd, pty=True)
    print("Seeded. Visit http://localhost:8090")


@task
def docker_test_down(c):
    """Tear down docker/compose.test.yml and remove its volumes."""
    c.run(f"{DOCKER_TEST_COMPOSE} down -v", pty=True)


@task
def reset_db(c):
    """Flush all data and re-apply migrations, keeping the same database."""
    manage_py = project_relative("manage.py")

    print("WARNING: This will DELETE ALL DATA in the database!")
    confirm = input("Are you sure you want to reset the database? (yes/no): ")

    if confirm.lower() != "yes":
        print("Aborted.")
        return

    print("Flushing database...")
    c.run(f"python {manage_py} flush --no-input", pty=True)

    print("Running migrations...")
    c.run(f"python {manage_py} migrate", pty=True)

    print(
        "Database reset complete. The database is now empty with all migrations applied."
    )


@task
def reset_db_hard(c):
    """Drop and recreate the database named in DATABASE_URL, then migrate."""
    print("WARNING: This will DROP and RECREATE the database!")
    confirm = input(
        "Are you sure you want to completely recreate the database? (yes/no): "
    )

    if confirm.lower() != "yes":
        print("Aborted.")
        return

    print("Dropping and recreating database...")

    from urllib.parse import urlparse

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

    c.run(f"{env_vars}dropdb {conn_string} {db_name} --if-exists", warn=True)
    c.run(f"{env_vars}createdb {conn_string} {db_name}")

    manage_py = project_relative("manage.py")
    print("Running migrations...")
    c.run(f"python {manage_py} migrate", pty=True)

    print(f"Database '{db_name}' recreated and migrations applied.")


@task
def restore_db(c, dump_file=None, yes=False):
    """Drop, recreate, and pg_restore the database from a pg_dump -Fc file (default: newest *.dump in the project root)."""
    import glob
    from urllib.parse import urlparse

    if dump_file is None:
        candidates = sorted(glob.glob(project_relative("*.dump")))
        if not candidates:
            print(
                "ERROR: No .dump files found in the project root. "
                "Pass --dump-file=<path> to specify one explicitly."
            )
            return
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


# Same limitation as docker_build above — not `invoke`-visible; use `invoke update`.
up = update
