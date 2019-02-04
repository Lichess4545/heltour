import click
import random
import json
import re
import math
import terminal

from itertools import combinations
from functools import partial

class Player:
    pref_score = 0
    team = None
    board = None
    req_met = False
    def __init__(self, name, rating, friends, avoid, date, alt, previous_season_alt):
        self.name = name
        self.rating = rating
        self.friends = friends
        self.avoid = avoid
        self.date = date
        self.alt = alt
        self.previous_season_alt = previous_season_alt

    @classmethod
    def player_from_json(cls, player):
        return cls(
            player['name'],
            player['rating'],
            player['friends'],
            player['avoid'],
            player['date_created'],
            player['prefers_alt'],
            player.get('previous_season_alternate') == 'alternate'
        )

    def __repr__(self):
        return str((self.name, self.board, self.rating, self.req_met))
    def __lt__(self, other):
        return True
    def setPrefScore(self):
        self.pref_score = 0
        for friend in self.friends:
            if friend in self.team.getBoards():
                self.pref_score += 1
            else:
                self.pref_score -= 1
        for avoid in self.avoid:
            if avoid in self.team.getBoards():
                self.pref_score -= 1
        #player with more than 5 choices can be <5 preference even if all teammates are preferred
    def setReqMet(self):
        self.req_met = False
        if not self.friends:
            self.req_met = None
        for friend in self.friends:
            if friend in self.team.getBoards():
                self.req_met = True

class Team:
    def __init__(self, boards):
        self.boards = [None for x in range(boards)]
    def __str__(self):
        return str((self.boards, self.team_pref_score, self.getMean()))
    def __repr__(self):
        return "Team:{0}".format(id(self))
    def __lt__(self, other):
        return True
    def changeBoard(self, board, new_player):
        #updates the player on a board and updates that player's team attribute
        if self.boards[board]:
            self.boards[board].team = None
        self.boards[board] = new_player
        if new_player.team:
            new_player.team.boards[board] = None
        new_player.team = self
    def getMean(self):
        ratings = [board.rating for board in self.boards]
        mean = sum(ratings) / len(ratings)
        return mean
    def getBoards(self):
        return self.boards
    def getPlayer(self, board):
        return self.boards[board]
    def setTeamPrefScore(self):
        self.team_pref_score = sum([x.pref_score for x in self.boards])

def updatePref(players, teams): #update preference scores
    for player in players:
        player.setPrefScore()
    for team in teams:
        team.setTeamPrefScore()

def updateSort(players, teams): #based on preference score high to low
    players.sort(key=lambda player: (player.team.team_pref_score, player.pref_score), reverse = False)
    teams.sort(key=lambda team: team.team_pref_score, reverse = False)

def split_into_equal_groups_by_rating(players, group_number):
    players.sort(key=lambda player: player.rating, reverse=True)
    avg = len(players) / float(group_number)
    players_split = []
    last = 0.0
    while round(last) < len(players):
        players_split.append(players[int(round(last)):int(round(last + avg))])
        last += avg
    return players_split


def get_rating_bounds_of_split(split):
    min_ratings = [min([p.rating for p in board]) for board in split]
    max_ratings = [max([p.rating for p in board]) for board in split]
    min_ratings[-1] = 0
    max_ratings[0] = 5000
    return list(zip(min_ratings, max_ratings))


def total_happiness(teams):
    return sum([team.team_pref_score for team in teams])


def team_rating_range(teams):
    means = [team.getMean() for team in teams]
    return max(means) - min(means)


def squared_diff(a, b):
    return (a - b)**2


def variance(mean, xs):
    return sum([squared_diff(mean, x) for x in xs]) / len(xs)


def team_rating_variance(teams, league_mean=None):
    if not league_mean:
        league_mean = sum([team.getMean() for team in teams]) / len(teams)
    return variance(league_mean, [team.getMean() for team in teams])


def flatten(lst):
    return [item for sub_lst in lst for item in sub_lst]


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

    # if output == "readable":
    #
    # elif output == "json":
    #     print(json.dumps(generate_json_output_object()))


def get_player_data(players):
    # input file is JSON data with the following keys: rating, name, in_slack, account_status, date_created,
    # prefers_alt, friends, avoid, has_20_games.
    with open(players,'r') as infile:
        playerdata = json.load(infile)
    return playerdata

    # print("This data was read from file.")

    # put player data into Player objects


def make_league(playerdata, boards, balance):

    players = []
    for player in playerdata:
        if player['has_20_games'] and player['in_slack']:
            players.append(Player.player_from_json(player))
        else:
            pass
            # print("{0} skipped".format(player['name']))
    players.sort(key=lambda player: player.rating, reverse=True)

    # Split into those that want to be alternates vs those that do not.
    alternates = [p for p in players if p.alt]
    players = [p for p in players if not p.alt]

    # splits list of Player objects into 6 near equal lists, sectioned by rating
    players_split = split_into_equal_groups_by_rating(players, boards)
    team_rating_bounds = get_rating_bounds_of_split(players_split)

    num_teams = int(math.ceil((len(players_split[0])*balance)/2.0)*2)
    # print(f"Targetting {num_teams} teams")

    # separate latest joining players into alternate lists as required
    for n, board in enumerate(players_split):
        board.sort(key=lambda player: (0 if player.previous_season_alt else 1, player.date))
        alternates.extend(board[num_teams:])
        del board[num_teams:]
        board.sort(key=lambda player: player.rating, reverse=True)

    alts_split = split_into_equal_groups_by_rating(alternates, boards)
    alt_rating_bounds = get_rating_bounds_of_split(alts_split)

    players = flatten(players_split)

    #print len(players)
    #print num_teams
    #print alts_split

    for n, board in enumerate(players_split):
        for player in board:
            player.board = n

    def convert_name_list(string_of_names, players):
        pattern = r"([^-_a-zA-Z0-9]|^){0}([^-_a-zA-Z0-9]|$)"
        return [player for player in players
                if re.search(pattern.format(player.name), string_of_names, flags=re.I)]

    for player in players:
        filtered_players = [p for p in players if p.board != player.board]
        player.friends = convert_name_list(player.friends, filtered_players)
        player.avoid = convert_name_list(player.avoid, filtered_players)

    # randomly shuffle players
    for board in players_split:
        random.shuffle(board)

    teams = []
    for n in range(num_teams):
        teams.append(Team(boards))
    for n, board in enumerate(players_split):
        for team, player in enumerate(board):
            teams[team].changeBoard(n, player)

    updatePref(players, teams)
    updateSort(players, teams)

    def swapPlayers(teama, playera, teamb, playerb, board):
        #swap players between teams - ensure players are same board for input
        teama.changeBoard(board,playerb)
        teamb.changeBoard(board,playera)

    def testSwap(teama, playera, teamb, playerb, board):
        #try a swap and return the preference change if this swap was made
        prior_pref = teama.team_pref_score + teamb.team_pref_score
        swapPlayers(teama, playera, teamb, playerb, board) #swap players forwards
        updatePref(players, teams)
        post_pref = teama.team_pref_score + teamb.team_pref_score
        swapPlayers(teama, playerb, teamb, playera, board) #swap players back
        updatePref(players, teams)
        return post_pref - prior_pref #more positive = better swap

    # take player from least happy team
    # calculate the overall preference score if player were to swap to each of the preferences' teams or preference swaps into their team.
    # swap player into the team that makes the best change to overall preference
    # check if the swap has increased the overall preference rating
    # if swap made, resort list by preference score and start at the least happy player again
    # if no improving swaps are available, go to the next player
    # if end of the list reached with no swaps made: stop

    p = 0
    while p < len(players):
        player = players[p] #least happy player
        swaps = []
        for friend in player.friends:
            # test both direction swaps for each friend and whichever is better, add the swap ID and score to temp
            # friends list
            # board check is redundant due to earlier removal of same board requests
            if friend.board != player.board and friend.team != player.team:
                #test swap friend to player team (swap1)
                swap1_ID = (friend.team, friend, player.team, player.team.getPlayer(friend.board), friend.board)
                swap1_score = testSwap(*swap1_ID)
                #test swap player to friend team (swap2)
                swap2_ID = (player.team, player, friend.team, friend.team.getPlayer(player.board), player.board)
                swap2_score = testSwap(*swap2_ID)
                swaps.append(max((swap1_score, swap1_ID),(swap2_score, swap2_ID)))
        for avoid in player.avoid:
            #test moving player to be avoided to the best preferred team
            if player.team == avoid.team: #otherwise irrelevant
                for swap_team in teams:
                    swap_ID = (avoid.team, avoid, swap_team, swap_team.getPlayer(avoid.board), avoid.board)
                    swap_score = testSwap(*swap_ID)
                    swaps.append((swap_score,swap_ID))
        swaps.sort()
        if swaps and swaps[-1][0] > 0: # there is a swap to make and it improves the preference score
            swapPlayers(*(swaps[-1][1]))
            # print(swaps[-1])
            updatePref(players, teams)
            updateSort(players, teams)
            p = 0
        else: # go to the next player in the list
            p += 1

    for player in players:
        player.setReqMet()

    return {'teams': teams,
            'players': players,
            'alternates': alternates,
            'team_rating_bounds': team_rating_bounds,
            'alt_rating_bounds': alt_rating_bounds,
            'alts_split': alts_split}


# Reduce variance functions

def intersection(lst1, lst2):
    return set(lst1).intersection(set(lst2))


# Does this swap have a neutral effect on happiness
def is_neutral_swap(swap):
    def count_on_team(attr, player, team):
        n = len(intersection(getattr(player, attr), team.boards))
        n += len([p for p in team.boards if player in getattr(p, attr)])
        return n

    count_friends_on_team = partial(count_on_team, 'friends')
    count_avoids_on_team = partial(count_on_team, 'avoid')

    pa, pb = swap
    pre_swap_score = count_friends_on_team(pa, pa.team) \
                     + count_friends_on_team(pb, pb.team) \
                     - count_avoids_on_team(pa, pa.team) \
                     - count_avoids_on_team(pb, pb.team)

    post_swap_score = count_friends_on_team(pa, pb.team) \
                     + count_friends_on_team(pb, pa.team) \
                     - count_avoids_on_team(pa, pb.team) \
                     - count_avoids_on_team(pb, pa.team)

    if pre_swap_score != post_swap_score:
        return False
    return True


def get_swaps(teams):
    num_boards = len(teams[0].boards)
    boards = [[team.boards[i] for team in teams] for i in range(num_boards)]
    swaps = [[swap for swap in combinations(board, 2) if is_neutral_swap(swap)] for board in boards]
    return flatten(swaps)


def rating_variance_improvement(league_mean, n_boards, swap):
    def score(a, b):
        return variance(league_mean, [a, b])

    pa, pb = swap
    a_mean = pa.team.getMean()
    b_mean = pb.team.getMean()
    initial_score = score(a_mean, b_mean)

    # calculating change in mean if we swapped the players.
    rating_diff = pb.rating - pa.rating
    a_mean = a_mean + rating_diff/n_boards
    b_mean = b_mean - rating_diff/n_boards
    new_score = score(a_mean, b_mean)

    # lower is better
    return new_score - initial_score


def get_best_swap(swaps, fun):
    best_swap = min(swaps, key=fun)
    return best_swap, fun(best_swap)


def perform_swap(swap):
    pa, pb = swap
    ta = pa.team
    tb = pb.team
    board = pa.board
    ta.changeBoard(board, pb)
    tb.changeBoard(board, pa)


def update_swaps(swaps, swap_performed, teams):
    pa, pb = swap_performed
    affected_players = pa.team.boards + pb.team.boards
    # remove all swaps involving players affected by the swap.
    swaps = [swap for swap in swaps
             if not intersection(swap, affected_players)]

    # find new neutral swaps involving the players affected by swap.
    for player in affected_players:
        board = player.board
        players_on_board = [team.boards[board] for team in teams
                            if not team.boards[board] in affected_players]
        swaps.extend([(player, p) for p in players_on_board
                      if is_neutral_swap((player, p))])

    swaps.extend([swap for swap in zip(pa.team.boards, pb.team.boards)
                  if is_neutral_swap(swap)])

    return swaps


def reduce_variance(teams):
    # players = flatten([team.boards for team in teams])

    league_mean = sum([team.getMean() for team in teams]) / len(teams)
    n_boards = len(teams[0].boards)

    swaps = get_swaps(teams)

    eval_fun = partial(rating_variance_improvement, league_mean, n_boards)
    best_swap, swap_value = get_best_swap(swaps, eval_fun)

    # infinite loop possibility here?
    i = 0
    max_iterations = 200
    epsilon = 0.0000001
    while swap_value <= -epsilon and i < max_iterations:
        # variance = team_rating_variance(teams, league_mean)
        # updatePref(players, teams)
        # score = total_happiness(teams)
        # print()
        # print("i: ", i)
        # print("variance: ", variance)
        # print("score: ", score)
        # print("swap_value: ", swap_value)
        # print("best_swap: ", best_swap)
        i += 1
        perform_swap(best_swap)
        swaps = update_swaps(swaps, best_swap, teams)
        best_swap, swap_value = get_best_swap(swaps, eval_fun)

    # means = [team.getMean() for team in teams]
    # print("means: ", sorted(means))
    return teams


# Output stuff

def generate_print_output(league):
    players, alternates, teams, team_rating_bounds, alt_rating_bounds, alts_split =\
        league['players'], league['alternates'], league['teams'], \
        league['team_rating_bounds'], league['alt_rating_bounds'], league['alts_split']
    boards = len(teams[0].boards)
    num_teams = len(teams)
    terminal.separator()

    print("Team rating range: ", team_rating_range(teams))
    print("Team rating variance: ", team_rating_variance(teams))
    print("Total happiness: ", total_happiness(teams))
    print(f"Using: {len(players)} players and {len(alternates)} alternates")
    print(terminal.green(f"Previous Season Alternates"))
    print(terminal.blue(f"Requested Alternate"))
    print("TEAMS")
    terminal.smallheader("Team #")
    for i in range(boards):
        n,x = team_rating_bounds[i]
        terminal.largeheader(f"Board #{i+1} [{n},{x})")
    terminal.largeheader("Mean rating")
    print()
    for team_i in range(num_teams):
        terminal.smallcol(f"#{team_i+1}")
        for board_i in range(boards):
            team = teams[team_i]
            player = team.boards[board_i]
            short_name = player.name[:20]
            player_name = f"{short_name} ({player.rating})"
            terminal.largecol(player_name, terminal.green if player.previous_season_alt else None)
        terminal.largecol("{0:.2f}".format(team.getMean()))
        print()
    print()
    print("ALTERNATES")
    terminal.smallheader(" ")
    for i in range(boards):
        n,x = alt_rating_bounds[i]
        terminal.largeheader(f"Board #{i+1} [{n},{x})")
    print()
    for player_i in range(max([len(a) for a in alts_split])):
        terminal.smallcol(" ")
        for board_i in range(boards):
            board = alts_split[board_i]
            player_name = ""
            if player_i < len(board):
                player = board[player_i]
                short_name = player.name
                short_name = player.name[:20]
                player_name = f"{short_name} ({player.rating})"
            terminal.largecol(player_name, terminal.blue if player.alt else None)
        print()


# WIP for upload format for heltour
def generate_json_output_object(teams, alts_split):
    jsonoutput = []
    # [{"action":"change-member",
    #   "team_number": 1,
    #   "board_number": 1,
    #   "player": {"name": "lemonworld",
    #              "is_captain": False,
    #              "is_vice_captain": False}}]

    for t, team in enumerate(teams):
        for b, board in enumerate(team.boards):
            pp = {"action": "change-member",
                  "team_number": t+1,
                  "board_number": b+1,
                  "player": {"name": board.name,
                             "is_captain": False,
                             "is_vice_captain": False}}
            jsonoutput.append(pp)

    for b, board in enumerate(alts_split):
        print(board)
        for _, pp in enumerate(board):
            pp = {"action": "create-alternate",
                  "board_number": b+1,
                  "player_name": pp.name}
            jsonoutput.append(pp)

    return jsonoutput

if __name__ == "__main__":
    run()
