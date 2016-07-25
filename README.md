# heltour
Swiss system pairings generator for chess tournaments.


# install
These install instructions have been test on Arch and Ubuntu linux. Other OSes should work, but the install 
may vary slightly.

1. Create a local settings file. In the heltour/local folder, copy one of the existing modules and name it "host_name.py" where "host_name" is your machine's hostname (with non-alphanumeric characters replaced by underscores).
2. `./start.sh`
3. `source env/bin/activate`
4. `fab up`
5. `fab createdb`
6. `python manage.py migrate`
7. `python manage.py createsuperuser`
8. `fab runserver`
