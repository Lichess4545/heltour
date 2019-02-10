import sys
try:
    import click
except ImportError:
    sys.exit("""You have to manually click to run this file.""")

import json
from heltour.tournament.teamgen import make_league, \
        total_happiness, team_rating_range, team_rating_variance, reduce_variance

from itertools import combinations
from functools import partial

class Terminal:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    def bold(txt):
        return Terminal.BOLD + txt + Terminal.ENDC
    def green(txt):
        return Terminal.OKGREEN + txt + Terminal.ENDC
    def blue(txt):
        return Terminal.OKBLUE + txt + Terminal.ENDC
    def header(txt):
        return Terminal.HEADER + txt + Terminal.ENDC
    def underline(txt):
        return Terminal.UNDERLINE + txt + Terminal.ENDC
    def smallheader(txt, wrap=None):
        if wrap:
            wrap = lambda x: Terminal.underline(wrap(x))
        else:
            wrap = lambda x: Terminal.underline(x)
        Terminal.smallcol(txt, wrap)
    def largeheader(txt, wrap=None):
        if wrap:
            wrap = lambda x: Terminal.underline(wrap(x))
        else:
            wrap = lambda x: Terminal.underline(x)
        Terminal.largecol(txt, wrap)
    def smallcol(txt, wrap=None):
        if not wrap:
            wrap = lambda x: x
        print(wrap(" {0: <6} |".format(txt)), end='')
    def largecol(txt, wrap=None):
        if not wrap:
            wrap = lambda x: x
        print(wrap(" {0: <27} |".format(txt)), end='')
    def separator():
        print("-{0:-<6}--".format(""), end='')
        for x in range(6):
            print("-{0: <27}--".format("-"*27), end='')
        print()


@click.command()
@click.option('--output', default="readable", type=click.Choice(['json', 'readable']))
@click.option('--players', help='the json file containing the players.', required=True)
@click.option('--boards', default=6, help='number of boards per team.')
@click.option('--balance', default=0.8, help='proportion of all players that will be full time')
@click.option('--count', default=100, help='Number of iterations to run happiness optimizer')
def run(players, output, boards, balance, count):
    player_data = get_player_data(players)

    leagues = [make_league(player_data, boards, balance) for _ in range(count)]

    max_happiness = max([total_happiness(l['teams']) for l in leagues])
    happy_leagues = [l for l in leagues if total_happiness(l['teams']) == max_happiness]
    print(f"{len(happy_leagues)} leagues of happiness {max_happiness} found")

    for i, league in enumerate(happy_leagues):
        print(f"Happy League {i}")
        generate_print_output(league)

    for league in happy_leagues:
        league['teams'] = reduce_variance(league['teams'])

    min_range_league = min(happy_leagues, key=lambda l: team_rating_range(l['teams']))
    print("Minimum rating range happy league")
    generate_print_output(min_range_league)


def get_player_data(players):
    # input file is JSON data with the following keys: rating, name, in_slack, account_status, date_created,
    # prefers_alt, friends, avoid, has_20_games.
    with open(players,'r') as infile:
        playerdata = json.load(infile)
    return playerdata

    # print("This data was read from file.")

    # put player data into Player objects


# Output stuff

def generate_print_output(league):
    players, alternates, teams, team_rating_bounds, alt_rating_bounds, alts_split =\
        league['players'], league['alternates'], league['teams'], \
        league['team_rating_bounds'], league['alt_rating_bounds'], league['alts_split']
    boards = len(teams[0].boards)
    num_teams = len(teams)
    Terminal.separator()

    print("Team rating range: ", team_rating_range(teams))
    print("Team rating variance: ", team_rating_variance(teams))
    print("Total happiness: ", total_happiness(teams))
    print(f"Using: {len(players)} players and {len(alternates)} alternates")
    print(Terminal.green(f"Previous Season Alternates"))
    print(Terminal.blue(f"Requested Alternate"))
    print("TEAMS")
    Terminal.smallheader("Team #")
    for i in range(boards):
        n,x = team_rating_bounds[i]
        Terminal.largeheader(f"Board #{i+1} [{n},{x})")
    Terminal.largeheader("Mean rating")
    print()
    for team_i in range(num_teams):
        Terminal.smallcol(f"#{team_i+1}")
        for board_i in range(boards):
            team = teams[team_i]
            player = team.boards[board_i]
            short_name = player.name[:20]
            player_name = f"{short_name} ({player.rating})"
            Terminal.largecol(player_name, Terminal.green if player.previous_season_alt else None)
        Terminal.largecol("{0:.2f}".format(team.get_mean()))
        print()
    print()
    print("ALTERNATES")
    Terminal.smallheader(" ")
    for i in range(boards):
        n,x = alt_rating_bounds[i]
        Terminal.largeheader(f"Board #{i+1} [{n},{x})")
    print()
    for player_i in range(max([len(a) for a in alts_split])):
        Terminal.smallcol(" ")
        for board_i in range(boards):
            board = alts_split[board_i]
            player_name = ""
            if player_i < len(board):
                player = board[player_i]
                short_name = player.name
                short_name = player.name[:20]
                player_name = f"{short_name} ({player.rating})"
            Terminal.largecol(player_name, Terminal.blue if player.alt else None)
        print()

if __name__ == "__main__":
    run()
