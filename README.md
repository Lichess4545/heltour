# heltour
League management software for the Lichess4545 league.

## Setup

* [Install docker](https://docs.docker.com/get-started/get-docker/)
* in a terminal run the following command:
```shell
docker compose up -d redis postges
docker compose run web python manage.py migrate --settings=heltour.settings_development
docker compose run web python manage.py createsuperuser --settings=heltour.settings_development
Username (leave blank to use 'root'): admin
Email address: admin@example.com
Password: <put whatever here>
Password (again): <if it complains just ignore it!>
Superuser created successfully.
docker compose up web
```

### Optional Components
- To generate pairings, download [JaVaFo](http://www.rrweb.org/javafo/current/javafo.jar) and set JAVAFO_COMMAND to 'java -jar /path/to/javafo.jar'


## Environmental variables

| Name | Default | Description |
|-|-|-|
| `DJANGO_SECRET_KEY` | `abc123` | a super secret key that django needs you to keep safe |
| `DJANGO_DEBUG` |  `FALSE` | puts django into debug mode, useful for local developement but definately needs to be off in production |
| `DJANGO_TESTING` | `FALSE` | tells the code we are running tests. |
| `DJANGO_LOGGING_CONFIG` | | django logging config in JSON format. if no config is provided will default to sensible norms |
| `DJANGO_LOGGING_LEVEL` | `DEBUG` | assuming that no logging config is provided, this variable controls the log level of django's logging |
| `DJANGO_DATABASE_CONFIG` | | django database config in JSON format. if no config is provided the application will assume a single postgres database, and look for additional configuration information from the environment |
| `DJANGO_DB_HOST` | `localhost` | the database host |
| `DJANGO_DB_PORT` | `5432` | the database port |
| `DJANGO_DB_NAME` |  | the database name |
| `DJANGO_DB_USER` |  | the database user |
| `DJANGO_DB_PASS` |  | the database password |
| `DJANGO_CACHE_URL` | `redis://localhost:6379/1` | the redis URL for django's caching |
| `DJANGO_CACHEOPS_URL` | `redis://localhost:6379/1` | the redis URL for cacheops |
| `CELERY_BROKER_URL` | `redis://localhost:6379/1` | the redis URL for the celery broker |
| `HELTOUR_LINK_PROTOCOL` | `https` | the protocol to use when making requests to other parts of the application, set to `http` for local development |
| `HELTOUR_APP` |  | set to `API_WORKER` to enable the api worker instead of the main web app |
| `HELTOUR_API_WORKER_HOST` | `https://localhost:8800` | the host for the API worker app |
| `HELTOUR_GOOGLE_SERVICE_ACCOUNT_KEYFILE_PATH` |  | path to service account key for accessing google services |
| `HELTOUR_SLACK_API_TOKEN_FILE_PATH` | | path to file containing the slack API token |
| `HELTOUR_SLACK_WEBHOOK_FILE_PATH` | | ??? |
| `HELTOUR_LICHESS_API_TOKEN_FILE_PATH` | | path to file containing the lichess API token |
| `HELTOUR_FCM_API_KEY_FILE_PATH` | | ??? |
| `HELTOUR_STAGING` | `False`| indicates that we are in the staging environment (or not!)|

