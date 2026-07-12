# heltour
League management software for the Lichess4545 league.

# requirements
* [devenv](https://devenv.sh) (provides Python, Postgres, Redis, and poetry)
* [Docker](https://docs.docker.com/get-docker/) with buildx, for building/running the container images

# install
1. Copy `.env.example` to `.env` and fill in the values.
2. `devenv up -d` to start Postgres and Redis.
3. `poetry install` to install Python dependencies.
4. `poetry run invoke migrate` to set up the database.
5. `poetry run invoke runserver` to run the development server.

Run `poetry run invoke --list` to see all available development tasks (migrations, tests, celery, static assets, docker image builds, and more).

# development
Ensure that your editor has an [EditorConfig plugin](https://editorconfig.org/#download) enabled.

# deployment
Images are built with `docker buildx bake` (see `docker/docker-bake.hcl`) and published/deployed via the workflows in `.github/workflows/`. The production stack is defined in `deploy/prod/`.

# create admin account
Run `poetry run python manage.py createsuperuser` to create a new admin account.

### Optional Components
- Pairing generation uses the JaVaFo jar vendored at `thirdparty/javafo.jar` (the default `JAVAFO_COMMAND`); set `JAVAFO_COMMAND` to point at a different jar or JRE if needed.
