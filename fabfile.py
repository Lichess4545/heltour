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
    local("pip install -r {}".format(project_relative("requirements.txt")))

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

        if confirm(colors.red("Would you like to install new nginx config?")):
            sudo("cp /var/www/heltour.lakin.ca/current/sysadmin/heltour.lakin.ca.conf /etc/nginx/sites-available/heltour.lakin.ca.conf")
        if confirm(colors.red("Would you like to reload nginx?")):
            sudo("service nginx reload")

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

#-------------------------------------------------------------------------------
def letsencrypt(real_cert=False):
    domain = "lichess4545.tv"
    domain2 = "lichess4545.com"
    domains = [
        domain,
        "www.{0}".format(domain),
        domain2,
        "www.{0}".format(domain2)
    ]
    country = "CA"
    state = "Alberta"
    town = "Calgary"
    email = "lakin.wecker@gmail.com"

    now = datetime.datetime.now()
    outdir = project_relative(now.strftime("certs/%Y-%m"))
    if os.path.exists(outdir):
        print colors.red("{0} exists, bailing to avoid overwriting files".format(outdir))
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
        local('openssl req -new -newkey rsa:2048 -sha256 -nodes -keyout "{key}" -out "{csr}" -outform der -subj "/C={country}/ST={state}/L={town}/O={domain}/emailAddress={email}/CN={domain}" -reqexts SAN -config "{ssl_conf}"'.format(
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
        local('letsencrypt certonly --text {test_cert} --manual {domain_args} --config-dir {etc_dir} --logs-dir {log_dir} --work-dir {lib_dir} --email "{email}" --csr "{csr}"'.format(
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
        privkey_target = "/var/ssl/lichess4545.com.key"
        chain_target = "/var/ssl/lichess4545.com.pem"
        put(privkey, privkey_target)
        put(chain, chain_target)
