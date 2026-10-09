# Releases and deployment

## Release a version

Run `release` from the devenv shell on `main`. The working tree must be clean, and `main` must contain everything on `origin/main`.

```
release
```

The `release` command:

1. Picks the next version from the commit subjects since the last `v*` tag. A `feat` commit raises the minor version. Any other type raises the patch version. A `!` or a `BREAKING CHANGE` footer raises the major version.
2. Updates `CHANGELOG.md` and the version in `pyproject.toml`.
3. Asks you to confirm.
4. Pushes `main` and the new tag, then watches the Release workflow.

To choose the version yourself, pass a bump or a version:

```
release minor
release v2.1.0
```

The new tag starts the Release workflow in `.github/workflows/release.yml`. The Release workflow builds the image, publishes `ghcr.io/lichess4545/heltour:<version>` and creates a GitHub release. For a stable release, the Release workflow also moves the `latest` image tag and deploys the version to production. A prerelease does neither.

## Deploy a version

Run `deploy` from the devenv shell to put any published version into production, including a version older than the running one:

```
deploy 2.0.3
```

The `deploy` command starts the Deploy workflow in `.github/workflows/deploy.yml`. The Deploy workflow:

1. Checks that the `v2.0.3` tag and the `ghcr.io/lichess4545/heltour:2.0.3` image exist.
2. Commits the new image version to `deploy/prod/compose.yml` on `main`.
3. Calls the Portainer webhook, and Portainer redeploys the stack.

The Deploy workflow changes nothing when production already runs the requested version. Stable releases use the same workflow, so the next stable release after a rollback moves production forward again.

Watch the deploy:

```
gh run watch --repo Lichess4545/heltour
```

## Container image

Build the image and load it into docker:

```
nix build .#container
docker load --input result
```

The project builds one container image. Each heltour process runs that image with a different command.

| Command | Process |
| --- | --- |
| `heltour-web` (default) | gunicorn for the site on port 8000 |
| `heltour-apiworker` | gunicorn for the api worker on port 8880 |
| `heltour-celery` | the celery worker, which also runs celery beat |
| `heltour-migrate` | runs migrations, clears the cacheops cache and exits |
| `heltour-caddy` | caddy on port 8080, serving `/static` and `/media` and proxying everything else to `web:8000` |
| `heltour-manage` | `manage.py` with any arguments |

The image runs as `nobody` and contains the collected static files. Uploaded media lives in `/var/lib/heltour/media`, which the web and caddy containers share.

Environment variables configure the image, and `.env.example` lists them. heltour reads any variable `NAME` from the file named by `NAME_FILE`. Setting both `NAME` and `NAME_FILE` is an error.

## Production

Portainer runs `deploy/prod/compose.yml` as a Docker Swarm stack. The stack runs its own redis and uses an external postgres. The image line in `compose.yml` pins the heltour version, and only the Deploy workflow changes that line. The `migrate` service runs after every image change.

### First-time setup

1. Create the external `frontend` network and run Traefik on that network. Traefik routes to the caddy service through the labels in `compose.yml`, which use the `websecure` entrypoint and the `dnsresolver` certresolver.
2. Create these Docker secrets:

   | Secret | Holds |
   | --- | --- |
   | `heltour_database_url` | `DATABASE_URL`, a postgres URL |
   | `heltour_secret_key` | `SECRET_KEY` |
   | `heltour_email_host_user` | `EMAIL_HOST_USER` |
   | `heltour_email_host_password` | `EMAIL_HOST_PASSWORD` |
   | `heltour_lichess_api_token` | `LICHESS_API_TOKEN` |
   | `heltour_slack_api_token` | `SLACK_API_TOKEN` |
   | `heltour_slack_channel_builder_token` | `SLACK_CHANNEL_BUILDER_TOKEN` |
   | `heltour_slack_webhook` | `SLACK_WEBHOOK_URL` |
   | `heltour_google_service_account` | `GOOGLE_SERVICE_ACCOUNT_KEY`, the service account's JSON key |

   Each service in `compose.yml` mounts only the secrets that service uses. A new secret goes in the `secrets` and `environment` of every service that reads it.
3. Create the Portainer stack from this repository, with branch `main` and path `deploy/prod/compose.yml`. Enable the stack webhook and set these stack variables:

   | Variable | Value |
   | --- | --- |
   | `HELTOUR_EMAIL_HOST` | The SMTP host. Required. |
   | `HELTOUR_CELERY_REPLICAS` | `1` runs the celery worker and beat. `0`, the default, runs neither. Never set more than `1`, because beat runs inside the worker. |

4. Save the webhook URL as the `PORTAINER_PRODUCTION_WEBHOOK_URL` repository secret. Without that secret, the Deploy workflow updates `compose.yml` and skips the redeploy.
