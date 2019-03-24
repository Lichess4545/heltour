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
These install instructions have been test on Arch and Ubuntu linux. Other OSes should work, but the install may vary slightly.

1. Create a local settings file. In the heltour/local folder, copy one of the existing modules and name it "host_name.py" where "host_name" is your machine's hostname (with non-alphanumeric characters replaced by underscores).
2. `./start.sh`
3. `source env/bin/activate`
4. `fab up`
5. `fab createdb`
6. `fab -R dev latestdb`
8. `fab runserver`

# sass compilation / CSS
The styles can be found in `/static-assets`
Compilation works as follows:
1. `cd static-assets`
2. `npm install`
3. `grunt`
4. Optionally: Install https://chrome.google.com/webstore/detail/livereload/jnihajbhpnppcggbcgedagnkighmdlei?hl=en so the browser reloads automatically for each style change.

# development
Use [4545vagrant](https://github.com/lakinwecker/4545vagrant) as development environment.

Ensure that your editor has an [EditorConfig plugin](https://editorconfig.org/#download) enabled.

# create admin account
Run `python manage.py createsuperuser` to create a new admin account.

### Optional Components
- To generate pairings, download [JaVaFo](http://www.rrweb.org/javafo/current/javafo.jar) and set JAVAFO_COMMAND to 'java -jar /path/to/javafo.jar'
