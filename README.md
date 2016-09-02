# heltour
League management software for the Lichess4545 league.

# requirements
* Python
* Pip
* Postgres (Ubuntu packages postgresql and postgresql-server-dev-9.5)
* Fabric (pip install fabric)
* Virtualenv (Ubuntu package virtualenv)
* Mercurial (for Baste installation)

# install
These install instructions have been test on Arch and Ubuntu linux. Other OSes should work, but the install
may vary slightly.

1. Create a local settings file. In the heltour/local folder, copy one of the existing modules and name it "host_name.py" where "host_name" is your machine's hostname (with non-alphanumeric characters replaced by underscores).
2. `./start.sh`
3. `source env/bin/activate`
4. `fab up`
5. `fab createdb`
6. `fab -R dev latestdb`
8. `fab runserver`

## default admin user password:
The `fab -R dev latestdb` command downloads an example database that has two leagues that are ongoing in them. The default username is `admin` with password of `09876default1234`.

### Optional Components
- To generate pairings, download [JaVaFo](http://www.rrweb.org/javafo/current/javafo.jar) and set JAVAFO_COMMAND to 'java -jar /path/to/javafo.jar'
