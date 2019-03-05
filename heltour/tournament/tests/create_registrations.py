from argparse import ArgumentParser
from types import SimpleNamespace


def create_registrations(season, count):
    league = season.league
    players = (Player.objects
               .filter(profile__perfs__has_key=league.rating_type)
               .exclude(**{f'profile__perfs__{league.rating_type}__has_key': 'prov'}))
    players = [p for p in players if User.objects.filter(username=p.lichess_username).exists()]
    return [create_reg(season, player.lichess_username, classical_rating=player.rating_for(league))
            for player in players[:count]]

def approve_reg(reg):
    try:
        user = User.objects.get(username=reg.lichess_username)
    except Exception as e:
        print(reg.lichess_username)
        raise e
    workflow = ApproveRegistrationWorkflow(reg)
    workflow.approve_reg(SimpleNamespace(user=user), None, False, False, season, 0, 0)


def truncate_registrations(season):
    Registration.objects.filter(season=season).delete()

if __name__ == '__main__':
    parser = ArgumentParser(description='Create a bunch of useful registrations for testing purposes')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--season-id', dest='season_id', help='Season id')
    group.add_argument('--season-name', dest='season_name', help='Season name')

    group = parser.add_mutually_exclusive_group()
    group.add_argument('--league-id', dest='league_id', help='League id')
    group.add_argument('--league-name', dest='league_name', help='League name')

    parser.add_argument('--truncate', action='store_true',
                        help='First delete all current registrations for this season')
    parser.add_argument('--approve', action='store_true',
                        help='Immdediately approve all registrations')

    parser.add_argument('count', type=int, help='number of registrations to create')
    args = parser.parse_args()

    # Now that cl args are validated we load the environment
    import os, sys

    proj_path = "/home/vagrant/heltour/heltour"
    # This is so Django knows where to find stuff.
    sys.path.append(proj_path)

    # This is so my local_settings.py gets loaded.
    os.chdir(proj_path)

    # This is so models get loaded.
    from django.core.wsgi import get_wsgi_application

    os.environ.setdefault("HELTOUR_ENV", "LIVE")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "heltour.settings")

    application = get_wsgi_application()


    from heltour.tournament.models import *
    from django.contrib.auth.models import User
    from heltour.tournament.tests.test_models import create_reg
    from heltour.tournament.workflows import ApproveRegistrationWorkflow

    if args.season_id:
        season = Season.objects.get(pk=args.season_id)
    elif args.season_name:
        if args.league_id:
            season = Season.objects.get(league_id=args.league_id, name=args.season_name)
        elif args.league_name:
            season = Season.objects.get(league__name=args.league_name, name=args.season_name)
        else:
            parser.print_help()
            exit()
    else:
        parser.print_help()
        exit()

    if args.truncate:
        truncate_registrations(season)

    registrations = create_registrations(season, args.count)
    if args.approve:
        for reg in registrations:
            approve_reg(reg)
