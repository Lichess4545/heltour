# heltour
League management software for the Lichess4545 league.

# requirements
* Python
* Pip
* poetry
* Postgres (Ubuntu packages postgresql and postgresql-server-dev-9.5)
* Fabric (pip install fabric)
* Virtualenv (Ubuntu package virtualenv)
* [Sass](https://sass-lang.com/install)

# install
These install instructions have been test on Arch and Ubuntu linux. Other OSes should work, but the install may vary slightly.

1. Create a local settings file. In the heltour/local folder, copy one of the existing modules and name it "host_name.py" where "host_name" is your machine's hostname (with non-alphanumeric characters replaced by underscores).
2. `./start.sh`
3. `source env/bin/activate`
4. `fab up`
5. `fab createdb`
6. `fab -R dev latestdb`
8. `fab runserver`

# development
Use [4545vagrant](https://github.com/lakinwecker/4545vagrant) as development environment.

Ensure that your editor has an [EditorConfig plugin](https://editorconfig.org/#download) enabled.

# create admin account
Run `python manage.py createsuperuser` to create a new admin account.

### Optional Components
- To generate pairings, download [JaVaFo](http://www.rrweb.org/javafo/current/javafo.jar) and set JAVAFO_COMMAND to 'java -jar /path/to/javafo.jar'


## Environmental variables

| Name | Default | Description |
|-|-|-|
| `DJANGO_SECRET_KEY` | `abc123` | a super secret key that django needs you to keep safe |
| `DJANGO_DEBUG` |  `FALSE` | puts django into debug mode, useful for local developement but definately needs to be off in production |
| `DJANGO_TESTING` | `FALSE` | tells the code we are running tests. |
| `HELTOUR_LINK_PROTOCOL` | `https` | the protocol to use when making requests to other parts of the application, set to `http` for local development |
| `HELTOUR_APP` |  | set to `API_WORKER` to enable the api worker instead of the main web app |
| `HELTOUR_API_WORKER_HOST` | `https://localhost:8800` | the host for the API worker app |
| `DJANGO_LOGGING_CONFIG` | | django logging config in JSON format. if no config is provided will default to sensible norms |
| `DJANGO_LOGGING_LEVEL` | `DEBUG` | assuming that no logging config is provided, this variable controls the log level of django's logging |
| `DJANGO_DATABASE_CONFIG` | | django database config in JSON format. if no config is provided the application will assume a single postgres database, and look for additional configuration information from the environment |
| `DJANGO_DB_HOST` | `localhost` | the database host |
| `DJANGO_DB_PORT` | `5432` | the database port |
| `DJANGO_DB_NAME` |  | the database name |
| `DJANGO_DB_USER` |  | the database user |
| `DJANGO_DB_PASS` |  | the database password |
| `CELERY_BROKER_URL` | `redis://localhost:6379/1` | the redis URL for the celery broker |
| `DJANGO_CACHE_URL` | `redis://localhost:6379/1` | the redis URL for django's caching |
| `DJANGO_CACHEOPS_URL` | `redis://localhost:6379/1` | the redis URL for cacheops |
| `HELTOUR_GOOGLE_SERVICE_ACCOUNT_KEYFILE_PATH` |  | path to service account key for accessing google services |
| `HELTOUR_SLACK_API_TOKEN_FILE_PATH` | | path to file containing the slack API token |
| `HELTOUR_SLACK_WEBHOOK_FILE_PATH` | | ??? |
| `HELTOUR_LICHESS_API_TOKEN_FILE_PATH` | | path to file containing the lichess API token |
| `HELTOUR_FCM_API_KEY_FILE_PATH` | | ??? |
| `HELTOUR_STAGING` | `False`| indicates that we are in the staging environment (or not!)|
| ``

