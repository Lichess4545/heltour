import os

from heltour.env import SecretFileEnv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

env = SecretFileEnv()
env.read_env(os.path.join(BASE_DIR, ".env"))


def required(name):
    return env.str(name)


def secret(name):
    return env.str(name, default="")


SECRET_KEY = required("SECRET_KEY")
DATABASE_URL = required("DATABASE_URL")

EMAIL_HOST_USER = secret("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = secret("EMAIL_HOST_PASSWORD")
LICHESS_API_TOKEN = secret("LICHESS_API_TOKEN")
SLACK_API_TOKEN = secret("SLACK_API_TOKEN")
SLACK_CHANNEL_BUILDER_TOKEN = secret("SLACK_CHANNEL_BUILDER_TOKEN")
SLACK_WEBHOOK_URL = secret("SLACK_WEBHOOK_URL")
GOOGLE_SERVICE_ACCOUNT_KEY = secret("GOOGLE_SERVICE_ACCOUNT_KEY")

DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
LINK_PROTOCOL = env.str("LINK_PROTOCOL", default="https")

HELTOUR_APP = env.str("HELTOUR_APP", default="tournament")
HELTOUR_ENV = env.str("HELTOUR_ENV", default="dev")
HELTOUR_VERSION = env.str("HELTOUR_VERSION", default="unknown")

STATIC_ROOT = env.str("STATIC_ROOT", default=os.path.join(BASE_DIR, "static"))
MEDIA_ROOT = env.str("MEDIA_ROOT", default=os.path.join(BASE_DIR, "media"))

REDIS_URL = env.str("REDIS_URL", default="redis://localhost:6379/1")
BROKER_URL = env.str("BROKER_URL", default=REDIS_URL)
API_WORKER_HOST = env.str("API_WORKER_HOST", default="http://localhost:8880")

EMAIL_HOST = env.str("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
SERVER_EMAIL = env.str("SERVER_EMAIL", default="noreply@lichess.org")
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", default="noreply@lichess.org")

LICHESS_DOMAIN = env.str("LICHESS_DOMAIN", default="https://lichess.org/")
LICHESS_NAME = env.str("LICHESS_NAME", default="lichess")
LICHESS_TOPLEVEL = env.str("LICHESS_TOPLEVEL", default="org")
LICHESS_OAUTH_CLIENTID = env.str("LICHESS_OAUTH_CLIENTID", default="heltour")
LICHESS_OAUTH_REDIRECT_SCHEME = env.str("LICHESS_OAUTH_REDIRECT_SCHEME", default="https://")

SLACK_ANNOUNCE_CHANNEL = env.str("SLACK_ANNOUNCE_CHANNEL", default="C2UP34BCZ")
SLACK_TEAM_ID = env.str("SLACK_TEAM_ID", default="T0CSGMP0R")
CHESSTER_USER_ID = env.str("CHESSTER_USER_ID", default="U020MSB1FV0")

JAVAFO_COMMAND = env.str("JAVAFO_COMMAND", default="java -jar ./thirdparty/javafo.jar")
SLEEP_UNIT = env.float("SLEEP_UNIT", default=1.0)
TEAMGEN_PROCESSES_NUMBER = env.int("TEAMGEN_PROCESSES_NUMBER", default=8)
