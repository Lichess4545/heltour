"""Providing a richer backup system than just every hour for 4 days.


In this file, we attempt to provide backups as follows:

    1 backup per hour for 24 hours.
    1 backup per day for 7 days
    1 backup per week for 4 weeks
    1 backup per month for 6 months.
"""
import commands
import datetime
import itertools
import os

test_monthly_backups = """
/var/backups/heltour-sql/monthly/heltour-2015-02-01-0021.sql.bz2
/var/backups/heltour-sql/monthly/heltour-2015-03-01-0021.sql.bz2
/var/backups/heltour-sql/monthly/heltour-2015-04-01-0021.sql.bz2
/var/backups/heltour-sql/monthly/heltour-2015-05-01-0021.sql.bz2
/var/backups/heltour-sql/monthly/heltour-2015-06-01-0021.sql.bz2
/var/backups/heltour-sql/monthly/heltour-2015-07-01-0021.sql.bz2
/var/backups/heltour-sql/monthly/heltour-2015-08-01-0021.sql.bz2
"""

test_weekly_backups = """
/var/backups/heltour-sql/weekly/heltour-2015-08-18-0021.sql.bz2
/var/backups/heltour-sql/weekly/heltour-2015-08-25-0021.sql.bz2
/var/backups/heltour-sql/weekly/heltour-2015-09-01-0021.sql.bz2
/var/backups/heltour-sql/weekly/heltour-2015-09-08-0021.sql.bz2
/var/backups/heltour-sql/weekly/heltour-2015-09-15-0021.sql.bz2
"""

test_daily_backups = """
/var/backups/heltour-sql/daily/heltour-2015-09-09-0021.sql.bz2
/var/backups/heltour-sql/daily/heltour-2015-09-09-0021.sql.bz2
/var/backups/heltour-sql/daily/heltour-2015-09-10-0021.sql.bz2
/var/backups/heltour-sql/daily/heltour-2015-09-11-0021.sql.bz2
/var/backups/heltour-sql/daily/heltour-2015-09-12-0021.sql.bz2
/var/backups/heltour-sql/daily/heltour-2015-09-13-0021.sql.bz2
/var/backups/heltour-sql/daily/heltour-2015-09-14-0021.sql.bz2
/var/backups/heltour-sql/daily/heltour-2015-09-15-0021.sql.bz2
/var/backups/heltour-sql/daily/heltour-2015-09-16-0021.sql.bz2
/var/backups/heltour-sql/daily/heltour-2015-09-17-0021.sql.bz2
"""

test_hourly_backups = """
/var/backups/heltour-sql/hourly/heltour-2015-09-14-2321.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-0321.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-1721.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-0721.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-18-0921.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-1421.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-14-0121.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-0921.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-18-0021.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-1621.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-1021.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-0821.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-14-1721.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-2021.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-1821.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-0521.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-13-1921.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-0921.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-2121.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-0521.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-0421.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-1921.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-0221.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-0821.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-13-2221.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-1621.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-0521.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-14-0621.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-0221.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-18-0121.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-18-0421.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-0421.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-0421.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-0621.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-18-1421.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-0621.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-1121.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-2021.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-14-1221.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-1321.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-18-1521.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-2221.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-0321.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-14-0021.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-14-2021.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-13-2121.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-1721.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-18-1221.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-0221.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-14-1521.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-14-0421.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-1321.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-14-0321.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-0021.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-1421.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-14-1821.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-1921.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-14-0921.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-13-2321.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-1521.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-14-0721.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-1421.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-1721.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-13-2021.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-0021.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-14-0821.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-1821.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-14-1021.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-1921.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-14-2121.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-0121.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-2221.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-1121.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-2321.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-0821.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-1521.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-0621.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-0721.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-2121.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-1821.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-1221.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-2021.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-14-1321.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-13-1721.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-18-1021.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-18-0621.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-0321.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-18-1321.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-2321.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-1121.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-18-0221.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-14-1121.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-14-1921.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-18-0521.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-2221.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-0121.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-18-0721.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-14-0221.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-2321.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-14-1421.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-0021.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-1021.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-1621.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-14-1621.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-18-0821.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-1321.sql.bz2
/var/backups/heltour-sql/hourly/latest.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-18-1121.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-1021.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-1521.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-18-0321.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-0721.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-13-1821.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-0921.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-0121.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-15-2121.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-13-1621.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-16-1221.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-17-1221.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-14-0521.sql.bz2
/var/backups/heltour-sql/hourly/heltour-2015-09-14-2221.sql.bz2
"""

DEBUG=False
#-------------------------------------------------------------------------------
def run(command):
    if DEBUG:
        print command
    else:
        return commands.getoutput(command)

#-------------------------------------------------------------------------------
def find_backups(target_directory, pattern="*.sql.bz2"):
    """Returns the set of backups from a given directory that match a pattern.
    """
    return run("find %s -name \"%s\"" % (target_directory, pattern))

#-------------------------------------------------------------------------------
def parse_backups(backup_string, date_format="%Y-%m-%d-%H%M"):
    """Use this to parse the output of a find command.

    returns a sorted tuple of datetime objects and paths.
    """
    potential_paths = [path for path in backup_string.split("\n") if path]
    paths = []
    for path in potential_paths:
        try:
            backup_time = datetime.datetime.strptime(path, date_format)
            paths.append((backup_time, path))
        except ValueError:
            continue
    return sorted(paths)


#-------------------------------------------------------------------------------
def monthly_cutoff(months_ago):
    now = datetime.datetime.now()
    start_of_month = now.replace(day=1, hour=0, minute=0)
    return (start_of_month - datetime.timedelta(days=28*(months_ago-1))).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

#-------------------------------------------------------------------------------
def weekly_cutoff(weeks_ago):
    now = datetime.datetime.now()
    start_of_week = now
    while start_of_week.weekday() != 0:
        start_of_week -= datetime.timedelta(days=1)

    return start_of_week - datetime.timedelta(weeks=weeks_ago)

#-------------------------------------------------------------------------------
def daily_cutoff(days_ago):
    now = datetime.datetime.now()
    return now - datetime.timedelta(days=days_ago)

#-------------------------------------------------------------------------------
def hourly_cutoff(hours_ago):
    now = datetime.datetime.now()
    return now - datetime.timedelta(hours=hours_ago)

#-------------------------------------------------------------------------------
def beginning_of_month():
    now = datetime.datetime.now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

#-------------------------------------------------------------------------------
def beginning_of_week():
    now = datetime.datetime.now()
    start_of_week = now
    while start_of_week.weekday() != 0:
        start_of_week -= datetime.timedelta(days=1)
    return start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)

#-------------------------------------------------------------------------------
def beginning_of_day():
    now = datetime.datetime.now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)

#-------------------------------------------------------------------------------
def remove_backups(files, cutoff_time):
    """Use this tool to remove backups older than given input from a directory.
    """
    def older_than(item):
        item_time, item = item
        return item_time < cutoff_time
    files_to_remove = itertools.ifilter(older_than, files)
    for item in files_to_remove:
        date_time, file_path = item
        run("rm %s" % file_path)

#-------------------------------------------------------------------------------
def add_to_backups(current_files, potential_files, cutoff_time, target_dir):
    """Copies the appropriate file into this backup rotation.
    """
    # First figure out if we have a backup in the current rotation that's after
    # the cutoff time. If not, we will try and find one in the potential files.
    for backup_time, backup in current_files:
        if backup_time >= cutoff_time:
            return

    # If we get here, none of the backups are appropriate
    for backup_time, backup in potential_files:
        if backup_time >= cutoff_time:
            run("cp %s %s" % (backup, target_dir))
            return


if __name__ == "__main__":

    base_format = "/var/backups/heltour-sql/%s/heltour-%%Y-%%m-%%d-%%H%%M.sql.bz2"
    hourly_format = base_format % "hourly"
    daily_format = base_format % "daily"
    weekly_format = base_format % "weekly"
    monthly_format = base_format % "monthly"

    base_directory = "/var/backups/heltour-sql/%s/"
    hourly_directory = base_directory % "hourly"
    daily_directory = base_directory % "daily"
    weekly_directory = base_directory % "weekly"
    monthly_directory = base_directory % "monthly"

    if DEBUG:
        hourly_find_output = test_hourly_backups
        daily_find_output = test_daily_backups
        weekly_find_output = test_weekly_backups
        monthly_find_output = test_monthly_backups
    else:
        hourly_find_output = find_backups(hourly_directory)
        daily_find_output = find_backups(daily_directory)
        weekly_find_output = find_backups(weekly_directory)
        monthly_find_output = find_backups(monthly_directory)

    hourly_backups = parse_backups(hourly_find_output, date_format=hourly_format)
    daily_backups = parse_backups(daily_find_output, date_format=daily_format)
    weekly_backups = parse_backups(weekly_find_output, date_format=weekly_format)
    monthly_backups = parse_backups(monthly_find_output, date_format=monthly_format)

    if DEBUG: print "Monthly"
    remove_backups(monthly_backups, monthly_cutoff(12))
    if DEBUG: print beginning_of_month()
    add_to_backups(
            monthly_backups,
            hourly_backups,
            beginning_of_month(),
            "/var/backups/heltour-sql/monthly/",
        )

    if DEBUG: print "weekly"
    if DEBUG: print beginning_of_week()
    remove_backups(weekly_backups, weekly_cutoff(8))
    add_to_backups(
            weekly_backups,
            hourly_backups,
            beginning_of_week(),
            "/var/backups/heltour-sql/weekly/",
        )

    if DEBUG: print "daily"
    if DEBUG: print beginning_of_day()
    remove_backups(daily_backups, daily_cutoff(14))
    add_to_backups(
            daily_backups,
            hourly_backups,
            beginning_of_day(),
            "/var/backups/heltour-sql/daily/"
        )

    if DEBUG: print "hourly"
    remove_backups(hourly_backups, hourly_cutoff(5*24))

    print parse_backups(test_hourly_backups, date_format=hourly_format)
