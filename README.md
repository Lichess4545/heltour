# heltour

League management software for the [Lichess4545](https://www.lichess4545.com) leagues.

## Run heltour locally

Install [devenv](https://devenv.sh) 2.4.0 or newer. devenv provides Python 3.11, the poetry environment, postgres, redis, [mailpit](https://mailpit.axllent.org) and the Java runtime for the [JaVaFo](http://www.rrweb.org/javafo/) pairing engine in `thirdparty/`.

```
cp .env.example .env
devenv up
```

`devenv up` starts postgres, redis, mailpit, django, the api worker and a celery worker. In a second terminal, create the database and an admin account:

```
devenv shell -- python manage.py migrate
devenv shell -- python manage.py createsuperuser
```

The site runs at <http://localhost:8000> and mailpit at <http://localhost:8025>. `.env.example` lists every setting. `LOG_LEVEL` sets the log level and defaults to `INFO`.

### Ports

Each service starts on its usual port, or on the next free port when the usual one is taken.

| Service | Usual port |
| --- | --- |
| postgres | 5432 |
| redis | 6379 |
| mailpit | 1025 for SMTP, 8025 for the web page |
| django | 8000 |
| api worker | 8880 |

`devenv processes list` shows the ports in use. devenv sets `DATABASE_URL`, `REDIS_URL`, `BROKER_URL`, `EMAIL_HOST`, `EMAIL_PORT`, `API_WORKER_HOST` and `CSRF_TRUSTED_ORIGINS` to match those ports. These values override `.env`. A `devenv shell` started while `devenv up` is running uses the same ports as the running services. A shell started before `devenv up` keeps the usual ports until you re-enter the shell or direnv reloads.

### Without devenv

Run `poetry install`, start postgres and redis, and set `DATABASE_URL`, `REDIS_URL` and `BROKER_URL` in `.env` to match. Then run:

```
poetry run python manage.py migrate
poetry run python manage.py runserver
```

## Tests

With `devenv up` running:

```
devenv shell -- python manage.py test --settings=heltour.test_settings
```

## Contributing

- Read [AI_POLICY.md](AI_POLICY.md) before you open a pull request.
- Write the pull request title as a [conventional commit](https://www.conventionalcommits.org), such as `feat: ...` or `fix: ...`. The squash merge uses the title as the commit subject on `main`, and the `release` command picks the next version from those subjects.
- Use an editor with [EditorConfig](https://editorconfig.org) support.
- Commit a new `python-deps.hash` with every change to `poetry.lock`. CI commits the hash for branches in this repository. On a fork, run `ci/python-deps-hash.sh` with nix installed and commit `python-deps.hash`.

[docs/deployment.md](docs/deployment.md) covers releases, the container image and production.
