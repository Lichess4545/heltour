import os
import sys
import strabulous

from fabric.api import (
    local,
    sudo,
    env,
    run,
    settings,
    shell_env,
)
from fabric import colors
from fabric.contrib.console import confirm

from baste import (
    Git,
    OrderedDict,
    project_relative,
    python_dependency,
    PgLoadPlain,
    RsyncDeployment,
    StatusCommand,
)

os.environ.setdefault("HELTOUR_ENV", "LIVE")


# -------------------------------------------------------------------------------
def import_db_name():
    from heltour.settings import DATABASES
    return DATABASES['default']['NAME']


# -------------------------------------------------------------------------------
def import_db_user():
    from heltour.settings import DATABASES
    return DATABASES['default']['USER']


# -------------------------------------------------------------------------------
def get_password():
    from heltour.settings import DATABASES
    return DATABASES['default']['PASSWORD']


# -------------------------------------------------------------------------------
# Figure out where we are on the directory system

relative_path_to_this_module = os.path.dirname(os.path.abspath(sys.modules[__name__].__file__))
absolute_path_to_this_module = os.path.abspath(relative_path_to_this_module)

PYTHON_VERSION = "python{0}.{1}".format(*sys.version_info)
PROJECT_NAME = 'heltour'
PYTHON_PACKAGE_NAME = PROJECT_NAME
PASSWORD_FILE_NAME = '%s.txt' % PROJECT_NAME
LIVE_BACKUP_SCRIPT_PATH = "/home/lichess4545/web/www.lichess4545.com/current/sysadmin/backup.sh"
env.roledefs = {
    'live': ['lichess4545@radio.lichess.ovh'],
    'staging': ['lichess4545@radio.lichess.ovh'],
    'vagrant': ['example@0.0.0.0'],
}

# TODO: we don't have any of these yet, but I prefer these over git submodules.
#       mostly because I don't always use git, and git submodules are frustratingly
#       limited to git. :(
python_repos = OrderedDict([(repo.name, repo) for repo in []])
static_file_repos = OrderedDict([(repo.name, repo) for repo in []])
all_repos = python_repos.copy()
all_repos.update(static_file_repos)
all_repos['baste'] = Git('env/src/baste', 'https://lakin.wecker@bitbucket.org/strabs/baste.git')
all_repos['container'] = Git('.', 'https://github.com/Lichess4545/heltour.git')

# -------------------------------------------------------------------------------
st = status = StatusCommand(all_repos)


# -------------------------------------------------------------------------------
def update():
    """
    Update all of the dependencies to their latest versions.
    """
    for repo in list(all_repos.values()):
        repo.update()

    for repo in list(python_repos.values()):
        python_dependency(repo.name, PYTHON_VERSION)

    python_dependency('heltour', PYTHON_VERSION)


up = update  # defines 'up' as the shortcut for 'update'


# -------------------------------------------------------------------------------
def deploylive():
    manage_py = project_relative("manage.py")
    local("rm -r static")
    local("mkdir static")
    local("python %s compilestatic" % manage_py)
    local("python %s collectstatic --noinput" % manage_py)
    if confirm(colors.red(
        "This will deploy to the live server (LIVE ENV) and restart the server. Are you sure?")):
        remote_directory = "/home/lichess4545/web/www.lichess4545.com"
        local_directory = project_relative(".") + "/"
        RsyncDeployment(
            remote_directory,
            local_directory
        )(
            exclude=['env', 'data', 'lichess4545@marta.lichess.ovh', 'certs']
        )
        run(
            "echo \"/home/lichess4545/web/www.lichess4545.com/current/\" > /home/lichess4545/web/www.lichess4545.com/env/lib/python3.9/site-packages/heltour.pth")

        if confirm(colors.red("Would you like to update the dependencies?")):
            run(
                "/home/lichess4545/web/www.lichess4545.com/current/sysadmin/update-requirements-live.sh")
        if confirm(colors.red("Would you like to run the migrations?")):
            run("/home/lichess4545/web/www.lichess4545.com/current/sysadmin/migrate-live.sh")
        if confirm(colors.red("Would you like to invalidate the caches?")):
            run("/home/lichess4545/web/www.lichess4545.com/current/sysadmin/invalidate-live.sh")

        if confirm(colors.red("Would you like to restart the server?")):
            sudo("/usr/sbin/service heltour-live restart", shell=False)
            sudo("/usr/sbin/service heltour-live-api restart", shell=False)
            sudo("/usr/sbin/service heltour-live-celery restart", shell=False)

        if confirm(colors.red("Would you like to reload nginx?")):
            sudo("/usr/sbin/service nginx reload", shell=False)


# -------------------------------------------------------------------------------
def deploystaging():
    manage_py = project_relative("manage_staging.py")
    local("rm -r static")
    local("mkdir static")
    local("python %s compilestatic" % manage_py)
    local("python %s collectstatic --noinput" % manage_py)
    if confirm(colors.red(
        "This will deploy to the live server (STAGING ENV) and restart the server. Are you sure?")):
        remote_directory = "/home/lichess4545/web/staging.lichess4545.com"
        local_directory = project_relative(".") + "/"
        RsyncDeployment(
            remote_directory,
            local_directory
        )(
            exclude=['env', 'data', 'lichess4545@marta.lichess.ovh', 'certs']
        )
        run(
            "echo \"/home/lichess4545/web/staging.lichess4545.com/current/\" > /home/lichess4545/web/staging.lichess4545.com/env/lib/python3.9/site-packages/heltour.pth")

        if confirm(colors.red("Would you like to update the dependencies?")):
            run(
                "/home/lichess4545/web/staging.lichess4545.com/current/sysadmin/update-requirements-staging.sh")
        if confirm(colors.red("Would you like to run the migrations?")):
            run("/home/lichess4545/web/staging.lichess4545.com/current/sysadmin/migrate-staging.sh")
        if confirm(colors.red("Would you like to invalidate the caches?")):
            run(
                "/home/lichess4545/web/staging.lichess4545.com/current/sysadmin/invalidate-staging.sh")

        if confirm(colors.red("Would you like to restart the server?")):
            sudo("/usr/sbin/service heltour-staging restart", shell=False)
            sudo("/usr/sbin/service heltour-staging-api restart", shell=False)
            sudo("/usr/sbin/service heltour-staging-celery restart", shell=False)

        if confirm(colors.red("Would you like to reload nginx?")):
            sudo("/usr/sbin/service nginx reload", shell=False)


# -------------------------------------------------------------------------------
def restartlive():
    if confirm(colors.red("Would you like to invalidate the caches?")):
        run("/home/lichess4545/web/www.lichess4545.com/current/sysadmin/invalidate-live.sh")

    if confirm(colors.red("Would you like to restart the server?")):
        sudo("/usr/sbin/service heltour-live restart", shell=False)
        sudo("/usr/sbin/service heltour-live-api restart", shell=False)
        sudo("/usr/sbin/service heltour-live-celery restart", shell=False)


# -------------------------------------------------------------------------------
def restartstaging():
    if confirm(colors.red("Would you like to invalidate the caches?")):
        run("/home/lichess4545/web/staging.lichess4545.com/current/sysadmin/invalidate-staging.sh")

    if confirm(colors.red("Would you like to restart the server?")):
        sudo("/usr/sbin/service heltour-staging restart", shell=False)
        sudo("/usr/sbin/service heltour-staging-api restart", shell=False)
        sudo("/usr/sbin/service heltour-staging-celery restart", shell=False)


# -------------------------------------------------------------------------------
def restartchesster():
    if confirm(colors.red("Would you like to restart chesster?")):
        sudo("/usr/sbin/service chesster restart", shell=False)


# -------------------------------------------------------------------------------
def createdb():
    DATABASE_NAME = import_db_name()
    DATABASE_USER = import_db_user()
    strabulous.createdb(DATABASE_NAME, DATABASE_USER, get_password)


# -------------------------------------------------------------------------------
def latestdb():
    DATABASE_NAME = import_db_name()
    DATABASE_USER = import_db_user()
    if not env.roles:
        print("Usage: fab -R [vagrant|staging|live] latestdb")
        return

    if env.roles == ['live']:
        LIVE_LATEST_SQL_FILE_PATH = "/home/lichess4545/backups/heltour-sql/hourly/latest.sql.bz2"
        strabulous.latest_live_db(LIVE_BACKUP_SCRIPT_PATH, LIVE_LATEST_SQL_FILE_PATH, DATABASE_NAME,
                                  DATABASE_USER, get_password)
    elif env.roles == ['vagrant']:
        local_db = "/home/vagrant/heltour/data/latestdb.sql.bz2"
        with settings(warn_only=True):
            PgLoadPlain(local_db, DATABASE_NAME, DATABASE_USER)()
    elif env.roles == ['staging']:
        local("mkdir -p {}".format(project_relative("data")))
        local_target = project_relative("data/latestdb.sql.bz2")
        devdb_source = "http://staging.lichess4545.com/devdb.sql.bz2"
        local("wget -O {} {}".format(local_target, devdb_source))
        PgLoadPlain(local_target, DATABASE_NAME, DATABASE_USER)()


# -------------------------------------------------------------------------------
def runserver():
    manage_py = project_relative("manage.py")
    local("python %s runserver 0.0.0.0:8000" % manage_py)


# -------------------------------------------------------------------------------
def cleansedb():
    manage_py = project_relative("manage.py")
    local("python %s cleansedb" % manage_py)
    local("python %s deleterevisions" % manage_py)


# -------------------------------------------------------------------------------
def runapiworker():
    manage_py = project_relative("manage.py")
    with shell_env(HELTOUR_APP="API_WORKER"):
        local("python %s runserver 0.0.0.0:8880" % manage_py)


