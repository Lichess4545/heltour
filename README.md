# heltour
Swiss system pairings generator for chess tournaments.


# install
These install instructions have been test on Arch and Ubuntu linux. Other OSes should work, but the install 
may vary slightly.

1. `./start.sh`
2. `source env/bin/activate`
3. `fab up`
4. `fab createdb`
5. `python manage.py migrate`
6. `python manage.py createsuperuser`
7. `fab runserver`

