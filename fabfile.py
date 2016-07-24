import sys
import datetime
import strabulous

from fabric.api import (
    local,
    lcd,
    env,
    hosts,
    run,
    get,
    settings,
)
from fabric import colors
from fabric.contrib.console import confirm

from baste import (
        DiffCommand,
        Git,
        Mercurial,
        Mercurial,
        OrderedDict,
        project_relative,
        python_dependency,
        PgLoadPlain,
        RsyncDeployment,
        RsyncMedia,
        StatusCommand,
        Subversion,
        UbuntuPgCreateDbAndUser,
    )


#-------------------------------------------------------------------------------
def import_db_name():
    from heltour.settings import DATABASES
    return DATABASES['default']['NAME']

#-------------------------------------------------------------------------------
def import_db_user():
    from heltour.settings import DATABASES
    return DATABASES['default']['USER']



#-------------------------------------------------------------------------------
# Figure out where we are on the directory system
import os.path
import sys

relative_path_to_this_module = os.path.dirname(os.path.abspath(sys.modules[__name__].__file__))
absolute_path_to_this_module = os.path.abspath(relative_path_to_this_module)

PYTHON_VERSION = "python{0}.{1}".format(*sys.version_info)
PROJECT_NAME = 'heltour'
PYTHON_PACKAGE_NAME = PROJECT_NAME
PASSWORD_FILE_NAME = '%s.txt' % PROJECT_NAME
LIVE_BACKUP_SCRIPT_PATH = "/var/www/heltour.lakin.ca/current/sysadmin/backup.sh"
env.roledefs = {
        'live': ['lakin@heltour.lakin.ca'],
    }

# TODO: we don't have any of these yet, but I prefer these over git submodules.
#       mostly because I don't always use git, and git submodules are frustratingly
#       limited to git. :(
python_repos = OrderedDict([(repo.name, repo) for repo in []])
static_file_repos = OrderedDict([(repo.name, repo) for repo in []])
all_repos = python_repos.copy()
all_repos.update(static_file_repos)
all_repos['baste'] = Mercurial('env/src/baste', 'ssh://hg@bitbucket.org/lakin.wecker/baste')
all_repos['container'] = Git('.', 'git@github.com:lakinwecker/heltour.git', 'master')

#-------------------------------------------------------------------------------
st = status = StatusCommand(all_repos)

#-------------------------------------------------------------------------------
def update():
    """
    Update all of the dependencies to their latest versions.
    """
    for repo in all_repos.values():
        repo.update()

    for repo in python_repos.values():
        python_dependency(repo.name, PYTHON_VERSION)

    python_dependency('heltour', PYTHON_VERSION)

up = update # defines 'up' as the shortcut for 'update'

#-------------------------------------------------------------------------------
def deploy():
    manage_py = project_relative("manage.py")
    local("python %s collectstatic --noinput" % manage_py)
    if confirm(colors.red("This will deploy to the live server and restart the server. Are you sure?")):
        remote_directory = "/var/www/heltour.lakin.ca"
        local_directory = project_relative(".") + "/"
        RsyncDeployment(
                remote_directory,
                local_directory
            )(
                exclude=['env', 'data', 'lakin@heltour.lakin.ca']
            )

        if confirm(colors.red("Would you like to update the dependencies?")):
            run("/var/www/heltour.lakin.ca/current/sysadmin/update-requirements.sh")
        if confirm(colors.red("Would you like to run the migrations?")):
            run("/var/www/heltour.lakin.ca/current/sysadmin/migrate.sh")

        if confirm(colors.red("Would you like to restart the server?")):
            sudo("service heltour restart")

#-------------------------------------------------------------------------------
def createdb():
    DATABASE_NAME = import_db_name()
    DATABASE_USER = import_db_user()
    strabulous.createdb(PYTHON_PACKAGE_NAME, DATABASE_NAME, DATABASE_USER)

#-------------------------------------------------------------------------------
def latestdb():
    DATABASE_NAME = import_db_name()
    DATABASE_USER = import_db_user()
    if not env.roles:
        print "Usage: fab -R [dev|live] latestdb"
        return

    LIVE_LATEST_SQL_FILE_PATH = "/var/backups/heltour.lakin.ca-sql/latest.sql.bz2"
    strabulous.latest_live_db(LIVE_BACKUP_SCRIPT_PATH, LIVE_LATEST_SQL_FILE_PATH, PYTHON_PACKAGE_NAME, DATABASE_NAME, DATABASE_USER)

#-------------------------------------------------------------------------------
def runserver():
    manage_py = project_relative("manage.py")
    local("python %s runserver 0.0.0.0:8000" % manage_py)
