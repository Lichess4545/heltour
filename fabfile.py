import os
import sys
import datetime
import strabulous

from fabric.api import (
    local,
    sudo,
    lcd,
    env,
    hosts,
    put,
    run,
    get,
    settings,
    shell_env,
)
from fabric import colors
from fabric.contrib.console import confirm

from baste import (
    DiffCommand,
    Git,
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
import os.path
import sys

relative_path_to_this_module = os.path.dirname(os.path.abspath(sys.modules[__name__].__file__))
absolute_path_to_this_module = os.path.abspath(relative_path_to_this_module)

PYTHON_VERSION = "python{0}.{1}".format(*sys.version_info)
PROJECT_NAME = 'heltour'
PYTHON_PACKAGE_NAME = PROJECT_NAME
PASSWORD_FILE_NAME = '%s.txt' % PROJECT_NAME
LIVE_BACKUP_SCRIPT_PATH = "/home/lichess4545/web/www.lichess4545.com/current/sysadmin/backup.sh"
env.roledefs = {
    'live': ['lichess4545@marta.lichess.ovh'],
    'staging': ['lichess4545@marta.lichess.ovh'],
}

# TODO: we don't have any of these yet, but I prefer these over git submodules.
#       mostly because I don't always use git, and git submodules are frustratingly
#       limited to git. :(
python_repos = OrderedDict([(repo.name, repo) for repo in []])
static_file_repos = OrderedDict([(repo.name, repo) for repo in []])
all_repos = python_repos.copy()
all_repos.update(static_file_repos)
all_repos['baste'] = Git('env/src/baste', 'git@bitbucket.org:strabs/baste.git')
all_repos['container'] = Git('.', 'git@github.com:lakinwecker/heltour.git', 'master')

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
    local("pip install -r {}".format(project_relative("requirements.txt")))


up = update  # defines 'up' as the shortcut for 'update'


# -------------------------------------------------------------------------------
def deploylive():
    manage_py = project_relative("manage.py")
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
            "echo \"/home/lichess4545/web/www.lichess4545.com/current/\" > /home/lichess4545/web/www.lichess4545.com/env/lib/python3.6/site-packages/heltour.pth")

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
            "echo \"/home/lichess4545/web/staging.lichess4545.com/current/\" > /home/lichess4545/web/staging.lichess4545.com/env/lib/python3.6/site-packages/heltour.pth")

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
        print("Usage: fab -R [staging|live] latestdb")
        return

    if env.roles == ['live']:
        LIVE_LATEST_SQL_FILE_PATH = "/home/lichess4545/backups/heltour-sql/hourly/latest.sql.bz2"
        strabulous.latest_live_db(LIVE_BACKUP_SCRIPT_PATH, LIVE_LATEST_SQL_FILE_PATH, DATABASE_NAME,
                                  DATABASE_USER, get_password)
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


# -------------------------------------------------------------------------------
def letsencrypt(real_cert=False):
    domain = "lichess4545.com"
    domain2 = "lichess4545.tv"
    domain3 = "staging.lichess4545.com"
    domains = [
        domain,
        "www.{0}".format(domain),
        domain2,
        "www.{0}".format(domain2),
        domain3,
    ]
    country = "CA"
    state = "Alberta"
    town = "Calgary"
    email = "lakin.wecker@gmail.com"

    now = datetime.datetime.now()
    outdir = project_relative(now.strftime("certs/%Y-%m"))
    if os.path.exists(outdir):
        print(colors.red("{0} exists, bailing to avoid overwriting files".format(outdir)))
        return
    key = "{0}/privkey1.pem".format(outdir)
    csr = "{0}/signreq.der".format(outdir)
    tmpdir = "{0}/tmp".format(outdir)
    ssl_conf = "{0}/openssl.cnf".format(tmpdir)
    local("mkdir -p {0}".format(tmpdir))
    with lcd(outdir):
        # Create an openssl.cnf that we can use.
        sans = ",".join(["DNS:{0}".format(d) for d in domains])
        local('cat /etc/ssl/openssl.cnf > "{0}"'.format(ssl_conf))
        local('echo "[SAN]" >> "{0}"'.format(ssl_conf))
        local('echo "subjectAltName={1}" >> "{0}"'.format(ssl_conf, sans))
        # Create the signing request.
        local(
            'openssl req -new -newkey rsa:2048 -sha256 -nodes -keyout "{key}" -out "{csr}" -outform der -subj "/C={country}/ST={state}/L={town}/O={domain}/emailAddress={email}/CN={domain}" -reqexts SAN -config "{ssl_conf}"'.format(
                key=key,
                csr=csr,
                country=country,
                state=state,
                town=town,
                domain=domain,
                email=email,
                ssl_conf=ssl_conf,
            ))

        domain_args = " ".join(["-d {0}".format(d) for d in domains])
        log_dir = "{0}/log".format(outdir)
        lib_dir = "{0}/lib".format(outdir)
        etc_dir = "{0}/etc".format(outdir)
        test_cert = "--test-cert"
        if real_cert:
            test_cert = ""
        local(
            'letsencrypt certonly --text {test_cert} --manual {domain_args} --config-dir {etc_dir} --logs-dir {log_dir} --work-dir {lib_dir} --email "{email}" --csr "{csr}"'.format(
                domain_args=domain_args,
                log_dir=log_dir,
                lib_dir=lib_dir,
                etc_dir=etc_dir,
                email=email,
                csr=csr,
                test_cert=test_cert
            ))
    if real_cert and confirm("Install cert?"):
        privkey = os.path.join(outdir, "privkey1.pem")
        chain = os.path.join(outdir, "0001_chain.pem")
        privkey_target = "/home/lichess4545/web/lichess4545.com.key"
        chain_target = "/home/lichess4545/web/lichess4545.com.pem"
        put(privkey, privkey_target)
        put(chain, chain_target)
