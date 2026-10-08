# heltour
League management software for the Lichess4545 league.

# requirements
* Python
* Pip
* poetry
* Postgres (Ubuntu packages postgresql and postgresql-server-dev-9.5)
* Fabric (pip install fabric)
* Virtualenv (Ubuntu package virtualenv)

# install
These install instructions have been test on Arch and Ubuntu linux. Other OSes should work, but the install may vary slightly.

1. Copy `.env.example` to `.env` and fill it in. Settings come from env vars or `.env`; each one can instead be read from a file named by `<NAME>_FILE`.
2. `./start.sh`
3. `source env/bin/activate`
4. `fab up`
5. `fab createdb`
6. `fab -R dev latestdb`
8. `fab runserver`

# development
Use [4545vagrant](https://github.com/lakinwecker/4545vagrant) as development environment.

Ensure that your editor has an [EditorConfig plugin](https://editorconfig.org/#download) enabled.

Run the tests with `python manage.py test --settings=heltour.test_settings`.

# create admin account
Run `python manage.py createsuperuser` to create a new admin account.

### Optional Components
- To generate pairings, download [JaVaFo](http://www.rrweb.org/javafo/current/javafo.jar) and set JAVAFO_COMMAND to 'java -jar /path/to/javafo.jar'
