import math
import os
import subprocess
import tempfile

import reversion
from django.db import transaction

from django.conf import settings
from heltour.tournament.models import (
    AlternateAssignment,
    KnockoutBracket,
    KnockoutSeeding,
    KnockoutAdvancement,
    LonePlayerPairing,
    PlayerAvailability,
    PlayerBye,
    SeasonPlayer,
    Team,
    TeamBye,
    TeamMember,
    TeamPairing,
    TeamPlayerPairing,
    find,
    lone_player_pairing_rank_dict,
)
from heltour.tournament_core.knockout import (
    generate_knockout_seedings_traditional,
    generate_knockout_seedings_adjacent,
    get_knockout_stage_name,
    validate_bracket_size,
    calculate_knockout_advancement,
    generate_next_round_pairings,
    create_knockout_tournament,
)


def generate_pairings(round_, overwrite=False):
    # Check if this is a knockout tournament
    if round_.season.league.pairing_type in ["knockout-single", "knockout-multi"]:
        if round_.season.league.competitor_type == "team":
            _generate_knockout_team_pairings(round_, overwrite)
        else:
            _generate_knockout_lone_pairings(round_, overwrite)
    else:
        # Swiss tournament logic
        if round_.season.league.competitor_type == "team":
            _generate_team_pairings(round_, overwrite)
        else:
            _generate_lone_pairings(round_, overwrite)


def _generate_team_pairings(round_, overwrite=False):
    with transaction.atomic():
        existing_pairings = TeamPairing.objects.filter(round=round_)
        if existing_pairings.count() > 0:
            if overwrite:
                delete_pairings(round_)
            else:
                raise PairingsExistException()
        else:
            # Always overwrite pairing byes
            TeamBye.objects.filter(round=round_, type="full-point-pairing-bye").delete()

        # Sort by seed rating/score
        teams = (
            Team.objects.filter(season=round_.season)
            .select_related("teamscore")
            .nocache()
        )
        for team in teams:
            if team.seed_rating is None:
                team.seed_rating = team.average_rating()
                with reversion.create_revision():
                    reversion.set_comment("Set seed rating.")
                    team.save()
        teams = sorted(
            teams,
            key=lambda team: team.get_teamscore().pairing_sort_key(),
            reverse=True,
        )

        previous_pairings = TeamPairing.objects.filter(
            round__season=round_.season, round__number__lt=round_.number
        ).order_by("round__number")

        # Run the pairing algorithm
        pairing_system = DutchTeamPairingSystem()
        team_pairings, team_byes = pairing_system.create_team_pairings(
            round_, teams, previous_pairings
        )

        # Save the team byes
        for team_bye in team_byes:
            with reversion.create_revision():
                reversion.set_comment("Generated pairings.")
                team_bye.save()

        # Save the team pairings and create the individual pairings based on the team pairings
        board_count = round_.season.boards
        for team_pairing in team_pairings:
            with reversion.create_revision():
                reversion.set_comment("Generated pairings.")
                team_pairing.save()

            white_player_list = _get_player_list(
                team_pairing.white_team, round_, board_count
            )
            black_player_list = _get_player_list(
                team_pairing.black_team, round_, board_count
            )
            for board_number in range(1, board_count + 1):
                white_player = white_player_list[board_number - 1]
                black_player = black_player_list[board_number - 1]
                if board_number % 2 == 0:
                    white_player, black_player = black_player, white_player
                with reversion.create_revision():
                    reversion.set_comment("Generated pairings.")
                    TeamPlayerPairing.objects.create(
                        team_pairing=team_pairing,
                        board_number=board_number,
                        white=white_player,
                        black=black_player,
                    )


# Create a list of players playing for the team this round
#
# The players and board numbers defined in AlternateAssignment are our invariants.
# Other players could end up in slightly different boards than expected if the board
# order changed since an alternate was assigned.
def _get_player_list(team, round_, board_count):
    team_members = [
        TeamMember.objects.filter(team=team, board_number=b).first()
        for b in range(1, board_count + 1)
    ]
    alternates = list(
        AlternateAssignment.objects.filter(round=round_, team=team).order_by(
            "board_number"
        )
    )

    player_list = [tm.player if tm is not None else None for tm in team_members]

    # Remove players that are being replaced by alternates
    for alt in reversed(alternates):
        if alt.replaced_player is not None:
            try:
                player_list.remove(alt.replaced_player)
            except ValueError:
                del player_list[alt.board_number - 1]
        else:
            del player_list[alt.board_number - 1]

    # Add assigned alternates at the appropriate board
    for alt in alternates:
        player_list.insert(alt.board_number - 1, alt.player)

    return player_list


def _generate_lone_pairings(round_, overwrite=False):
    with transaction.atomic():
        existing_pairings = LonePlayerPairing.objects.filter(round=round_)
        if existing_pairings.count() > 0:
            if overwrite:
                delete_pairings(round_)
            else:
                raise PairingsExistException()
        else:
            # Always overwrite pairing byes
            PlayerBye.objects.filter(
                round=round_, type="full-point-pairing-bye"
            ).delete()

        # Perform any registrations and withdrawals
        for reg in round_.playerlateregistration_set.select_related("player").nocache():
            reg.perform_registration()
        for wd in round_.playerwithdrawal_set.select_related("player").nocache():
            wd.perform_withdrawal()

        # Sort by seed rating/score
        season_players = (
            SeasonPlayer.objects.filter(season=round_.season)
            .select_related("player", "loneplayerscore", "season__league")
            .nocache()
        )
        for sp in season_players:
            if sp.seed_rating is None:
                sp.seed_rating = sp.player.rating_for(round_.season.league)
                with reversion.create_revision():
                    reversion.set_comment("Set seed rating.")
                    sp.save()
        season_players = sorted(
            season_players,
            key=lambda sp: sp.get_loneplayerscore().pairing_sort_key(),
            reverse=True,
        )

        # Create byes for unavailable players
        current_byes = {
            bye.player
            for bye in PlayerBye.objects.filter(round=round_)
            .select_related("player")
            .nocache()
        }
        unavailable_players = {
            avail.player
            for avail in PlayerAvailability.objects.filter(
                round=round_, is_available=False
            )
            .select_related("player")
            .nocache()
        }
        active_players = {sp.player for sp in season_players if sp.is_active}
        players_needing_byes = unavailable_players & active_players - current_byes

        for p in players_needing_byes:
            with reversion.create_revision():
                reversion.set_comment("Generated pairings.")
                PlayerBye.objects.create(round=round_, player=p, type="half-point-bye")

        # Don't generate pairings for players that have been withdrawn or have byes
        include_players = {
            sp
            for sp in season_players
            if sp.is_active
            and sp.player not in current_byes
            and sp.player not in unavailable_players
        }

        previous_pairings = (
            LonePlayerPairing.objects.filter(
                round__season=round_.season, round__number__lt=round_.number
            )
            .order_by("round__number")
            .select_related("white", "black", "round")
            .nocache()
        )
        previous_byes = (
            PlayerBye.objects.filter(
                round__season=round_.season, round__number__lt=round_.number
            )
            .order_by("round__number")
            .select_related("player", "round")
            .nocache()
        )

        # Run the pairing algorithm
        if round_.season.league.pairing_type == "swiss-dutch-baku-accel":
            pairing_system = DutchLonePairingSystem(accel="baku")
        else:
            pairing_system = DutchLonePairingSystem()
        lone_pairings, byes = pairing_system.create_lone_pairings(
            round_, season_players, include_players, previous_pairings, previous_byes
        )

        # Save the lone pairings
        rank_dict = lone_player_pairing_rank_dict(round_.season)
        for lone_pairing in lone_pairings:
            lone_pairing.refresh_ranks(rank_dict)
            with reversion.create_revision():
                reversion.set_comment("Generated pairings.")
                lone_pairing.save()

        # Save pairing byes and update player ranks for all byes
        for bye in byes + list(
            PlayerBye.objects.filter(round=round_).select_related("player").nocache()
        ):
            bye.refresh_rank(rank_dict)
            with reversion.create_revision():
                reversion.set_comment("Generated pairings.")
                bye.save()


def delete_pairings(round_):
    if round_.season.league.competitor_type == "team":
        if (
            TeamPlayerPairing.objects.filter(team_pairing__round=round_)
            .exclude(result="")
            .count()
        ):
            raise PairingHasResultException()
        TeamPairing.objects.filter(round=round_).delete()
        TeamBye.objects.filter(round=round_, type="full-point-pairing-bye").delete()
    else:
        if LonePlayerPairing.objects.filter(round=round_).exclude(result="").count():
            raise PairingHasResultException()
        LonePlayerPairing.objects.filter(round=round_).delete()
        PlayerBye.objects.filter(round=round_, type="full-point-pairing-bye").delete()


class PairingsExistException(Exception):
    pass


class PairingHasResultException(Exception):
    pass


class PairingGenerationException(Exception):
    pass


class PlaceholderTeamPairingSystem:
    def create_team_pairings(self, round_, teams, previous_pairings):
        # Pair teams in some arbitrary order for testing purposes
        team_pairings = []
        team_byes = []
        for i in range(int(len(teams) / 2)):
            white_team = teams[i * 2]
            black_team = teams[i * 2 + 1]
            team_pairings.append(
                TeamPairing(
                    white_team=white_team,
                    black_team=black_team,
                    round=round_,
                    pairing_order=i + 1,
                )
            )
        # Handle odd number of teams
        if len(teams) % 2 == 1:
            team_byes.append(
                TeamBye(team=teams[-1], round=round_, type="full-point-pairing-bye")
            )
        return team_pairings, team_byes


class DutchTeamPairingSystem:
    def create_team_pairings(self, round_, teams, previous_pairings):
        # Note: Assumes teams is sorted by seed and previous_pairings is sorted by round

        players = [
            JavafoPlayer(
                team,
                team.teamscore.match_points,
                list(self._process_pairings(team, previous_pairings)),
                include=team.is_active,
            )
            for team in teams
        ]
        javafo = JavafoInstance(round_.season.rounds, players)
        pairs = javafo.run()

        team_pairings = []
        team_byes = []
        for i in range(len(pairs)):
            white_team = pairs[i][0]
            black_team = pairs[i][1]
            if white_team is not None and black_team is not None:
                team_pairings.append(
                    TeamPairing(
                        white_team=white_team,
                        black_team=black_team,
                        round=round_,
                        pairing_order=i + 1,
                    )
                )
            elif white_team is not None and black_team is None:
                # Team gets a bye
                team_byes.append(
                    TeamBye(
                        team=white_team, round=round_, type="full-point-pairing-bye"
                    )
                )
        return team_pairings, team_byes

    def _process_pairings(self, team, pairings):
        # Process all rounds in order
        round_numbers = sorted(
            set(p.round.number for p in pairings) if pairings else []
        )

        for round_num in round_numbers:
            # Check if team had a pairing this round
            round_pairings = [
                p
                for p in pairings
                if p.round.number == round_num
                and (p.white_team == team or p.black_team == team)
            ]

            if round_pairings:
                # Team had a pairing
                p = round_pairings[0]
                if p.white_team == team:
                    yield JavafoPairing(
                        p.black_team,
                        "white",
                        (
                            1.0
                            if p.white_points > p.black_points
                            else 0.5 if p.white_points == p.black_points else 0
                        ),
                    )
                if p.black_team == team:
                    yield JavafoPairing(
                        p.white_team,
                        "black",
                        (
                            1.0
                            if p.black_points > p.white_points
                            else 0.5 if p.white_points == p.black_points else 0
                        ),
                    )
            else:
                # Check if team had a bye this round
                bye = TeamBye.objects.filter(team=team, round__number=round_num).first()
                if bye:
                    yield JavafoPairing(None, None, bye.score(), forfeit=True)


class DutchLonePairingSystem:
    def __init__(self, accel=None):
        self.accel = accel

    def create_lone_pairings(
        self, round_, season_players, include_players, previous_pairings, previous_byes
    ):
        # Note: Assumes season_players is sorted by seed and previous_pairings/previous_byes are sorted by round

        if self.accel == "baku":
            # Ensure each player is in the correct acceleration group
            if round_.number == 1:
                # Calculate all groups from scratch
                for sp in set(season_players) - set(include_players):
                    sp.loneplayerscore.acceleration_group = 0
                    sp.loneplayerscore.save()
                group_1_size = int(2 * math.ceil(len(include_players) / 4.0))
                sorted_players = sorted(
                    include_players, key=lambda sp: sp.seed_rating, reverse=True
                )
                for sp in sorted_players[:group_1_size]:
                    sp.loneplayerscore.acceleration_group = 1
                    sp.loneplayerscore.save()
                for sp in sorted_players[group_1_size:]:
                    sp.loneplayerscore.acceleration_group = 2
                    sp.loneplayerscore.save()
            else:
                # Update groups only for players that don't already have one
                min_rating_for_group_1 = min(
                    (
                        sp.seed_rating
                        for sp in season_players
                        if sp.loneplayerscore.acceleration_group == 1
                    )
                )
                for sp in season_players:
                    if sp.loneplayerscore.acceleration_group == 0:
                        if sp.seed_rating >= min_rating_for_group_1:
                            sp.loneplayerscore.acceleration_group = 1
                        else:
                            sp.loneplayerscore.acceleration_group = 2
                        sp.loneplayerscore.save()

        def acceleration_scores(sp):
            if self.accel == "baku" and sp.loneplayerscore.acceleration_group == 1:
                return [1, 1, 1, 0.5, 0.5]
            return None

        players = [
            JavafoPlayer(
                sp.player,
                sp.get_loneplayerscore().pairing_points(),
                list(
                    self._process_pairings(
                        sp,
                        previous_pairings,
                        previous_byes,
                        round_.number,
                        sp.loneplayerscore.late_join_points,
                    )
                ),
                sp in include_players,
                acceleration_scores=acceleration_scores(sp),
            )
            for sp in season_players
        ]
        javafo = JavafoInstance(round_.season.rounds, players)
        pairs = javafo.run()
        lone_pairings = []
        byes = []
        for i in range(len(pairs)):
            white = pairs[i][0]
            black = pairs[i][1]
            if black is None:
                byes.append(
                    PlayerBye(player=white, round=round_, type="full-point-pairing-bye")
                )
            else:
                lone_pairings.append(
                    LonePlayerPairing(
                        white=white, black=black, round=round_, pairing_order=i + 1
                    )
                )
        return lone_pairings, byes

    def _process_pairings(self, sp, pairings, byes, current_round_number, bonus_score):
        player_pairings = [
            p for p in pairings if p.white == sp.player or p.black == sp.player
        ]
        player_byes = [b for b in byes if b.player == sp.player]
        for n in range(1, current_round_number):
            p = find(player_pairings, round__number=n)
            b = find(player_byes, round__number=n)
            if p is not None:
                if p.white == sp.player:
                    yield JavafoPairing(
                        p.black, "white", p.white_score(), forfeit=not p.game_played()
                    )
                else:
                    yield JavafoPairing(
                        p.white, "black", p.black_score(), forfeit=not p.game_played()
                    )
            elif b is not None:
                yield JavafoPairing(None, None, b.score(), forfeit=True)
            elif bonus_score >= 1:
                yield JavafoPairing(None, None, 1, forfeit=True)
                bonus_score -= 1
            elif bonus_score == 0.5:
                yield JavafoPairing(None, None, 0.5, forfeit=True)
                bonus_score = 0
            else:
                yield JavafoPairing(None, None, None, forfeit=True)


class JavafoPlayer:
    def __init__(self, player, score, pairings, include=True, acceleration_scores=None):
        self.player = player
        self.score = score
        self.pairings = pairings
        self.include = include
        self.acceleration_scores = acceleration_scores


class JavafoPairing:
    def __init__(self, opponent, color, score, forfeit=False):
        self.opponent = opponent
        self.color = color
        self.score = score
        self.forfeit = forfeit


class JavafoPairingResult:
    def __init__(self, white, black):
        self.white = white
        self.black = black


def generate_trf_content(total_round_count, players):
    """Generate TRF file content for JavaFo.

    Arguments:
    total_round_count -- number of rounds in the tournament
    players -- a list of JavafoPlayer objects ordered by seed

    Returns:
    A string containing the TRF file content
    """
    lines = []
    lines.append("XXR %d\n" % total_round_count)

    for n, player in enumerate(players, 1):
        line = "001  {0: >3}  {1:74.1f}     ".format(n, player.score)
        for pairing in player.pairings:
            opponent_num = next(
                (
                    num
                    for num, p in enumerate(players, 1)
                    if p.player == pairing.opponent
                ),
                "0000",
            )
            color = (
                "w"
                if pairing.color == "white"
                else "b" if pairing.color == "black" else "-"
            )
            if pairing.forfeit:
                score = (
                    "+"
                    if pairing.score == 1
                    else (
                        "-"
                        if pairing.score == 0
                        else "=" if pairing.score == 0.5 else " "
                    )
                )
            else:
                score = (
                    "1"
                    if pairing.score == 1
                    else (
                        "0"
                        if pairing.score == 0
                        else "=" if pairing.score == 0.5 else " "
                    )
                )
            if score == " ":
                color = "-"
            line += "{0: >6} {1} {2}".format(opponent_num, color, score)
        if not player.include:
            line += "{0: >6} {1} {2}".format("0000", "-", "-")
        line += "\n"
        lines.append(line)

    # Add acceleration scores if present
    for n, player in enumerate(players, 1):
        if player.acceleration_scores:
            line = "XXA {0: >4} {1}\n".format(
                n,
                " ".join("{0: >4.1f}".format(s) for s in player.acceleration_scores),
            )
            lines.append(line)

    return "".join(lines)


# TODO: Verify for score >= 10
class JavafoInstance:
    """Interfaces with javafo.jar

    Arguments:
    total_round_count -- number of rounds in the tournament
    players -- a list of JavafoPlayer objects ordered by seed

    Each player's list of pairings should be ordered by round number.
    """

    def __init__(self, total_round_count, players):
        self.total_round_count = total_round_count
        self.players = players

    """Runs the Javafo process

    Returns a list of JavafoPairingResult objects in the order they should be displayed.
    """

    def run(self):
        input_file = tempfile.NamedTemporaryFile(suffix=".trfx", mode="w+")
        output_file_name = input_file.name + ".out.txt"
        try:
            # Generate TRF content and write to input file
            trf_content = generate_trf_content(self.total_round_count, self.players)
            input_file.write(trf_content)
            input_file.flush()

            self._call_proc(input_file.name, output_file_name, "-q 10000")

            pairs = self._read_output(output_file_name)
            if len(pairs) == 0 and len(self.players) > 1:
                # Took too long before terminating, use the slower but more deterministic algorithm
                self._call_proc(input_file.name, output_file_name, "-w")
                pairs = self._read_output(output_file_name)

            return pairs
        finally:
            input_file.close()
            try:
                os.remove(output_file_name)
            except OSError:
                pass

    def _call_proc(self, input_file_name, output_file_name, args):
        proc = subprocess.Popen(
            "%s %s -p %s %s"
            % (settings.JAVAFO_COMMAND, input_file_name, output_file_name, args),
            shell=True,
            stdout=subprocess.PIPE,
        )
        stdout = proc.communicate()[0]
        if proc.returncode != 0:
            raise PairingGenerationException(
                "Javafo return code: %s. Output: %s" % (proc.returncode, stdout)
            )

    def _read_output(self, output_file_name):
        with open(output_file_name) as output_file:
            pair_count = int(output_file.readline())
            pairs = []
            for _ in range(pair_count):
                w, b = output_file.readline().split(" ")
                if int(b) == 0:
                    pairs.append([self.players[int(w) - 1].player, None])
                else:
                    pairs.append(
                        [
                            self.players[int(w) - 1].player,
                            self.players[int(b) - 1].player,
                        ]
                    )
            return pairs


def assign_automatic_forfeits(round_):
    """
    Assign forfeit wins for pairings with missing players.

    This function looks for TeamPlayerPairing objects where either white or black
    is None and automatically assigns appropriate forfeit results:
    - 1X-0F: White wins by forfeit (black is missing)
    - 0F-1X: Black wins by forfeit (white is missing)
    - 0F-0F: Double forfeit (both missing)

    Args:
        round_: Round object to process

    Returns:
        int: Number of forfeit results assigned
    """
    forfeit_count = 0

    if round_.season.league.competitor_type == "team":
        # Process team tournament board pairings
        team_pairings = TeamPairing.objects.filter(round=round_).prefetch_related(
            "teamplayerpairing_set"
        )

        for team_pairing in team_pairings:
            board_pairings = team_pairing.teamplayerpairing_set.all()

            for board_pairing in board_pairings:
                # Only assign forfeits if result is empty
                if board_pairing.result:
                    continue

                white_missing = board_pairing.white is None
                black_missing = board_pairing.black is None

                if white_missing and black_missing:
                    # Both players missing - double forfeit
                    board_pairing.result = "0F-0F"
                    board_pairing.save()
                    forfeit_count += 1
                elif white_missing and not black_missing:
                    # White missing - black wins by forfeit
                    board_pairing.result = "0F-1X"
                    board_pairing.save()
                    forfeit_count += 1
                elif not white_missing and black_missing:
                    # Black missing - white wins by forfeit
                    board_pairing.result = "1X-0F"
                    board_pairing.save()
                    forfeit_count += 1

            # Update team pairing points after assigning forfeit results
            if forfeit_count > 0:
                team_pairing.refresh_points()
                team_pairing.save()

    else:
        # Process individual tournament pairings
        lone_pairings = LonePlayerPairing.objects.filter(round=round_)

        for pairing in lone_pairings:
            # Only assign forfeits if result is empty
            if pairing.result:
                continue

            white_missing = pairing.white is None
            black_missing = pairing.black is None

            if white_missing and black_missing:
                # Both players missing - double forfeit
                pairing.result = "0F-0F"
                pairing.save()
                forfeit_count += 1
            elif white_missing and not black_missing:
                # White missing - black wins by forfeit
                pairing.result = "0F-1X"
                pairing.save()
                forfeit_count += 1
            elif not white_missing and black_missing:
                # Black missing - white wins by forfeit
                pairing.result = "1X-0F"
                pairing.save()
                forfeit_count += 1

    return forfeit_count


def _generate_knockout_team_pairings(round_, overwrite=False):
    """Generate pairings for team knockout tournaments."""
    with transaction.atomic():
        existing_pairings = TeamPairing.objects.filter(round=round_)
        if existing_pairings.count() > 0:
            if overwrite:
                delete_pairings(round_)
            else:
                raise PairingsExistException()

        # Get or create knockout bracket
        bracket, created = KnockoutBracket.objects.get_or_create(
            season=round_.season,
            defaults={
                "bracket_size": _calculate_bracket_size(round_.season),
                "seeding_style": round_.season.league.knockout_seeding_style,
                "games_per_match": round_.season.league.knockout_games_per_match,
                "matches_per_stage": (
                    2 if round_.season.league.pairing_type == "knockout-multi" else 1
                ),
            },
        )

        if round_.number == 1:
            # Generate initial bracket for first round
            _generate_initial_knockout_bracket(round_, bracket)
        else:
            # Generate next round based on advancement from previous round
            _generate_next_knockout_round(round_, bracket)


def _generate_knockout_lone_pairings(round_, overwrite=False):
    """Generate pairings for individual knockout tournaments."""
    with transaction.atomic():
        existing_pairings = LonePlayerPairing.objects.filter(round=round_)
        if existing_pairings.count() > 0:
            if overwrite:
                delete_pairings(round_)
            else:
                raise PairingsExistException()

        # Get or create knockout bracket
        bracket, created = KnockoutBracket.objects.get_or_create(
            season=round_.season,
            defaults={
                "bracket_size": _calculate_bracket_size(round_.season),
                "seeding_style": round_.season.league.knockout_seeding_style,
                "games_per_match": round_.season.league.knockout_games_per_match,
                "matches_per_stage": (
                    2 if round_.season.league.pairing_type == "knockout-multi" else 1
                ),
            },
        )

        if round_.number == 1:
            # Generate initial bracket for first round
            _generate_initial_knockout_bracket_lone(round_, bracket)
        else:
            # Generate next round based on advancement from previous round
            _generate_next_knockout_round_lone(round_, bracket)


def _calculate_bracket_size(season):
    """Calculate the appropriate bracket size (power of 2) for the season."""
    if season.league.competitor_type == "team":
        active_teams = Team.objects.filter(season=season, is_active=True).count()
    else:
        active_players = SeasonPlayer.objects.filter(
            season=season, is_active=True
        ).count()
        active_teams = active_players

    # Find next power of 2 that can accommodate all competitors
    bracket_size = 2
    while bracket_size < active_teams:
        bracket_size *= 2

    return bracket_size


def _generate_knockout_seedings_only(bracket):
    """Generate knockout seedings without creating any pairings."""
    season = bracket.season

    if season.league.competitor_type == "team":
        # Get active teams sorted by strength (strongest first)
        teams = Team.objects.filter(season=season, is_active=True).select_related(
            "teamscore"
        )

        # Ensure seed_rating is set for all teams
        for team in teams:
            if team.seed_rating is None:
                team.seed_rating = team.average_rating()
                with reversion.create_revision():
                    reversion.set_comment("Set seed rating for knockout seeding.")
                    team.save()

        # Sort by seed_rating (strongest first)
        teams = sorted(teams, key=lambda t: t.seed_rating, reverse=True)

        # Ensure bracket size is valid
        if not validate_bracket_size(len(teams)):
            raise PairingGenerationException(
                f"Team count {len(teams)} is not a power of 2. Knockout requires power of 2."
            )

        # Create seedings if they don't exist
        if not KnockoutSeeding.objects.filter(bracket=bracket).exists():
            for i, team in enumerate(teams):
                KnockoutSeeding.objects.create(
                    bracket=bracket, team=team, seed_number=i + 1, is_manual_seed=False
                )
    else:
        # Individual tournaments are not fully supported for knockout seedings yet
        # The KnockoutSeeding model only supports teams, not individual players
        # For now, skip seeding creation for individual tournaments
        season_players = SeasonPlayer.objects.filter(
            season=season, is_active=True
        ).order_by("id")

        # Ensure bracket size is valid
        if not validate_bracket_size(len(season_players)):
            raise PairingGenerationException(
                f"Player count {len(season_players)} is not a power of 2. Knockout requires power of 2."
            )

        # TODO: Individual knockout seedings need a separate model or KnockoutSeeding needs a player field
        # For now, individual knockout tournaments will work without seedings


def _generate_initial_knockout_bracket(round_, bracket):
    """Generate initial knockout bracket seedings only - no pairings created."""
    # Generate seedings only, let dashboard create the actual pairings
    _generate_knockout_seedings_only(bracket)
    
    # Set round knockout stage
    teams = Team.objects.filter(season=round_.season, is_active=True)
    stage_name = get_knockout_stage_name(len(teams))
    round_.knockout_stage = stage_name
    round_.save()


def _generate_initial_knockout_bracket_lone(round_, bracket):
    """Generate initial knockout bracket seedings only - no pairings created."""
    # Generate seedings only, let dashboard create the actual pairings
    _generate_knockout_seedings_only(bracket)
    
    # Set round knockout stage  
    season_players = SeasonPlayer.objects.filter(season=round_.season, is_active=True)
    stage_name = get_knockout_stage_name(len(season_players))
    round_.knockout_stage = stage_name
    round_.save()


def _get_multi_match_winners(round_obj, bracket):
    """Get winners from multi-match tournament by aggregating scores for each team pair."""
    from collections import defaultdict
    from heltour.tournament.models import Team

    # Group pairings by team pair
    team_pair_groups = defaultdict(list)
    all_pairings = TeamPairing.objects.filter(round=round_obj).select_related(
        "white_team", "black_team"
    )

    for pairing in all_pairings:
        if pairing.black_team:  # Skip byes (handle separately)
            team_key = tuple(sorted([pairing.white_team.id, pairing.black_team.id]))
            team_pair_groups[team_key].append(pairing)

    # Determine winners for each team pair
    winners = []

    # Process team pairs in order of first pairing_order to maintain bracket structure
    team_pair_first_orders = {}
    for team_key, pairings in team_pair_groups.items():
        min_order = min(p.pairing_order for p in pairings)
        team_pair_first_orders[team_key] = min_order

    # Sort team pairs by their first pairing order
    sorted_team_pairs = sorted(
        team_pair_groups.items(), key=lambda x: team_pair_first_orders[x[0]]
    )

    for team_key, pairings in sorted_team_pairs:
        team1 = Team.objects.get(id=team_key[0])
        team2 = Team.objects.get(id=team_key[1])

        # Aggregate scores for this team pair
        total_team1_points = 0.0
        total_team2_points = 0.0
        has_manual_tiebreak = False
        manual_tiebreak_winner = None

        # Check all matches are complete
        for pairing in pairings:
            if pairing.white_points is None or pairing.black_points is None:
                raise PairingGenerationException(
                    f"Round {round_obj.number} results incomplete for {team1.name} vs {team2.name}"
                )

            # Check for manual tiebreak
            if pairing.manual_tiebreak_value is not None:
                has_manual_tiebreak = True
                if pairing.white_team == team1:
                    manual_tiebreak_winner = (
                        team1 if pairing.manual_tiebreak_value > 0 else team2
                    )
                else:
                    manual_tiebreak_winner = (
                        team2 if pairing.manual_tiebreak_value > 0 else team1
                    )
                break  # Manual tiebreak overrides all other considerations

            # Add to aggregate scores based on team orientation
            if pairing.white_team.id == team1.id:
                total_team1_points += pairing.white_points
                total_team2_points += pairing.black_points
            else:
                total_team1_points += pairing.black_points
                total_team2_points += pairing.white_points

        # Determine winner
        if has_manual_tiebreak:
            winners.append(manual_tiebreak_winner)
        elif total_team1_points > total_team2_points:
            winners.append(team1)
        elif total_team2_points > total_team1_points:
            winners.append(team2)
        else:
            # Aggregate scores are tied - this should be very rare in multi-match
            raise PairingGenerationException(
                f"Tied aggregate score between {team1.name} and {team2.name} "
                f"({total_team1_points}-{total_team2_points}) requires manual tiebreak resolution"
            )

    # Handle byes - teams with byes advance automatically
    bye_pairings = all_pairings.filter(black_team__isnull=True).order_by(
        "pairing_order"
    )
    for pairing in bye_pairings:
        winners.append(pairing.white_team)

    return winners


def _generate_next_knockout_round(round_, bracket):
    """Generate next round pairings based on previous round advancement."""
    previous_round = round_.season.round_set.filter(number=round_.number - 1).first()

    if not previous_round:
        raise PairingGenerationException("No previous round found for advancement")

    # Get winners from previous round
    if bracket.matches_per_stage > 1:
        # Multi-match tournament: aggregate scores by team pair
        winners = _get_multi_match_winners(previous_round, bracket)
    else:
        # Single-match tournament: use individual pairing results
        winners = []
        for pairing in TeamPairing.objects.filter(round=previous_round).order_by(
            "pairing_order"
        ):
            if pairing.white_points is None or pairing.black_points is None:
                raise PairingGenerationException(
                    f"Round {previous_round.number} results incomplete"
                )

            # Determine winner including manual tiebreak
            if pairing.white_points > pairing.black_points:
                winners.append(pairing.white_team)
            elif pairing.black_points > pairing.white_points:
                winners.append(pairing.black_team)
            else:
                # Tied - check manual tiebreak
                if pairing.manual_tiebreak_value is None:
                    raise PairingGenerationException(
                        f"Tied pairing between {pairing.white_team} and {pairing.black_team} "
                        "requires manual tiebreak resolution"
                    )
                elif pairing.manual_tiebreak_value > 0:
                    winners.append(pairing.white_team)
                else:
                    winners.append(pairing.black_team)

    # Create advancement records for all winners
    # Calculate the target stage based on current round's teams remaining
    current_teams_remaining = bracket.bracket_size // (2 ** (round_.number - 1))
    target_stage = get_knockout_stage_name(current_teams_remaining)

    # Determine from_stage - use knockout_stage if set, otherwise calculate it
    from_stage = previous_round.knockout_stage
    if not from_stage:
        # Calculate knockout stage based on round number and bracket size
        teams_remaining = bracket.bracket_size // (2 ** (previous_round.number - 1))
        from_stage = get_knockout_stage_name(teams_remaining)

    if bracket.matches_per_stage > 1:
        # Multi-match tournament: create one advancement record per winner
        # Use the first pairing for each team pair as the source pairing
        from collections import defaultdict

        team_pair_groups = defaultdict(list)
        all_pairings = TeamPairing.objects.filter(round=previous_round).select_related(
            "white_team", "black_team"
        )

        for pairing in all_pairings:
            if pairing.black_team:  # Skip byes
                team_key = tuple(sorted([pairing.white_team.id, pairing.black_team.id]))
                team_pair_groups[team_key].append(pairing)

        # Sort team pairs by first pairing order
        team_pair_first_orders = {}
        for team_key, pairings in team_pair_groups.items():
            min_order = min(p.pairing_order for p in pairings)
            team_pair_first_orders[team_key] = min_order

        sorted_team_pairs = sorted(
            team_pair_groups.items(), key=lambda x: team_pair_first_orders[x[0]]
        )

        for i, (team_key, pairings) in enumerate(sorted_team_pairs):
            winner = winners[i]
            # Use the first pairing (lowest pairing_order) as the source
            source_pairing = min(pairings, key=lambda p: p.pairing_order)
            KnockoutAdvancement.objects.get_or_create(
                bracket=bracket,
                team=winner,
                from_stage=from_stage,
                to_stage=target_stage,
                source_pairing=source_pairing,
            )

        # Handle byes separately
        bye_pairings = all_pairings.filter(black_team__isnull=True).order_by(
            "pairing_order"
        )
        bye_winner_index = len(sorted_team_pairs)
        for pairing in bye_pairings:
            winner = winners[bye_winner_index]
            KnockoutAdvancement.objects.get_or_create(
                bracket=bracket,
                team=winner,
                from_stage=from_stage,
                to_stage=target_stage,
                source_pairing=pairing,
            )
            bye_winner_index += 1
    else:
        # Single-match tournament: one advancement record per pairing
        for i, pairing in enumerate(
            TeamPairing.objects.filter(round=previous_round).order_by("pairing_order")
        ):
            winner = winners[i]
            KnockoutAdvancement.objects.get_or_create(
                bracket=bracket,
                team=winner,
                from_stage=from_stage,
                to_stage=target_stage,
                source_pairing=pairing,
            )

    # Generate next round pairings
    winner_ids = [team.id for team in winners]
    next_pairings = generate_next_round_pairings(winner_ids)

    # Set round knockout stage
    stage_name = get_knockout_stage_name(len(winners))
    round_.knockout_stage = stage_name
    round_.save()

    # Create team pairings for next round. In 'lockstep' mode only the first
    # match of the stage is created; later matches are created once every
    # bracket finishes the current one. In 'upfront' mode every match of the
    # stage is created now, so each bracket can play its matches back-to-back
    # without waiting on the rest of the round. pairing_order is laid out
    # match-by-match (match 1 for every pair, then match 2, ...) to match the
    # modular arithmetic used elsewhere for multi-match knockouts.
    matches_per_stage = bracket.matches_per_stage or 1
    matches_to_create = matches_per_stage if bracket.match_generation == "upfront" else 1
    total_pairs = len(next_pairings)

    for match_number in range(1, matches_to_create + 1):
        for i, (team1_id, team2_id) in enumerate(next_pairings):
            team1 = Team.objects.get(id=team1_id)
            team2 = Team.objects.get(id=team2_id)

            # Odd matches keep the bracket colors; even matches swap them so
            # each bracket plays both colors across the stage.
            if match_number % 2 == 1:
                white_team, black_team = team1, team2
            else:
                white_team, black_team = team2, team1

            pairing_order = (match_number - 1) * total_pairs + i + 1

            with reversion.create_revision():
                reversion.set_comment("Advanced to next knockout round.")
                team_pairing = TeamPairing.objects.create(
                    white_team=white_team,
                    black_team=black_team,
                    round=round_,
                    pairing_order=pairing_order,
                )

            # Create board pairings for team matches
            _create_board_pairings_for_knockout(team_pairing, round_.season.boards)


def _generate_next_knockout_round_lone(round_, bracket):
    """Generate next round pairings for individual tournaments."""
    previous_round = round_.season.round_set.filter(number=round_.number - 1).first()

    if not previous_round:
        raise PairingGenerationException("No previous round found for advancement")

    # Get winners from previous round in bracket order (pairing_order)
    winners = []
    for pairing in LonePlayerPairing.objects.filter(round=previous_round).order_by(
        "pairing_order"
    ):
        if not pairing.result:
            raise PairingGenerationException(
                f"Round {previous_round.number} results incomplete"
            )

        # Determine winner based on result
        white_score = pairing.white_score()
        black_score = pairing.black_score()

        if white_score > black_score:
            winners.append(pairing.white)
        elif black_score > white_score:
            winners.append(pairing.black)
        else:
            # This shouldn't happen in individual knockout without manual tiebreaks
            # but handle gracefully
            raise PairingGenerationException(
                f"Tied pairing between {pairing.white} and {pairing.black} "
                "in individual knockout tournament"
            )

    # Generate next round pairings
    winner_ids = [player.id for player in winners]
    next_pairings = generate_next_round_pairings(winner_ids)

    # Set round knockout stage
    stage_name = get_knockout_stage_name(len(winners))
    round_.knockout_stage = stage_name
    round_.save()

    # Create lone player pairings for next round
    rank_dict = lone_player_pairing_rank_dict(round_.season)
    for i, (player1_id, player2_id) in enumerate(next_pairings):
        from heltour.tournament.models import Player

        player1 = Player.objects.get(id=player1_id)
        player2 = Player.objects.get(id=player2_id)

        with reversion.create_revision():
            reversion.set_comment("Advanced to next knockout round.")
            lone_pairing = LonePlayerPairing.objects.create(
                white=player1,
                black=player2,
                round=round_,
                pairing_order=i + 1,
            )
            lone_pairing.refresh_ranks(rank_dict)
            lone_pairing.save()


def _create_board_pairings_for_knockout(team_pairing, board_count):
    """Create board pairings for a knockout team match."""
    white_player_list = _get_player_list(
        team_pairing.white_team, team_pairing.round, board_count
    )
    black_player_list = _get_player_list(
        team_pairing.black_team, team_pairing.round, board_count
    )

    for board_number in range(1, board_count + 1):
        white_player = white_player_list[board_number - 1]
        black_player = black_player_list[board_number - 1]

        # Alternate colors by board (same as Swiss)
        if board_number % 2 == 0:
            white_player, black_player = black_player, white_player

        with reversion.create_revision():
            reversion.set_comment("Generated knockout board pairing.")
            TeamPlayerPairing.objects.create(
                team_pairing=team_pairing,
                board_number=board_number,
                white=white_player,
                black=black_player,
            )


def generate_knockout_bracket_structure_only(season):
    """
    Generate initial knockout bracket structure and seedings for a season.

    This function creates the KnockoutBracket and KnockoutSeeding records,
    but does NOT generate any match pairings. Use this for initial seeding.

    Args:
        season: Season object to create bracket for

    Returns:
        KnockoutBracket: The created bracket

    Raises:
        PairingGenerationException: If bracket generation fails
    """
    if season.league.pairing_type not in ["knockout-single", "knockout-multi"]:
        raise PairingGenerationException(
            f"Season {season} is not configured for knockout tournaments"
        )

    # Calculate bracket size
    bracket_size = _calculate_bracket_size(season)

    # Create or get existing bracket
    # Set matches_per_stage based on pairing type
    matches_per_stage = 2 if season.league.pairing_type == "knockout-multi" else 1

    bracket, created = KnockoutBracket.objects.get_or_create(
        season=season,
        defaults={
            "bracket_size": bracket_size,
            "seeding_style": season.league.knockout_seeding_style,
            "games_per_match": season.league.knockout_games_per_match,
            "matches_per_stage": matches_per_stage,
        },
    )

    # Only create the seedings, not the pairings
    if created:
        _generate_knockout_seedings_only(bracket)

    return bracket


def generate_knockout_bracket(season):
    """
    Generate initial knockout bracket for a season.

    This function creates the KnockoutBracket and KnockoutSeeding records,
    but does NOT create pairings. Use create_knockout_pairings() for that.

    Args:
        season: Season object to create bracket for

    Returns:
        KnockoutBracket: The created bracket

    Raises:
        PairingGenerationException: If bracket generation fails
    """
    # Only create the bracket structure and seedings
    bracket = generate_knockout_bracket_structure_only(season)

    # Generate seedings only for first round if it exists
    first_round = season.round_set.filter(number=1).first()
    if first_round:
        generate_pairings(first_round, overwrite=True)

    return bracket


def create_knockout_pairings(round_):
    """
    Create actual pairings for a knockout round based on existing seedings.
    
    This simulates the dashboard "create missing matches" functionality.
    
    Args:
        round_: Round object to create pairings for
        
    Returns:
        int: Number of pairings created
        
    Raises:
        PairingGenerationException: If pairing creation fails
    """
    from heltour.tournament.views import LeagueDashboardView
    
    # Create a mock view instance to use the pairing creation logic
    view = LeagueDashboardView()
    
    # Get the bracket
    try:
        bracket = KnockoutBracket.objects.get(season=round_.season)
    except KnockoutBracket.DoesNotExist:
        raise PairingGenerationException(f"No bracket found for season {round_.season}")
    
    if round_.season.league.competitor_type == "team":
        # Check if pairings already exist
        if TeamPairing.objects.filter(round=round_).exists():
            raise PairingGenerationException(f"Pairings already exist for round {round_.number}")
        
        if round_.number == 1:
            # Create initial pairings from seedings
            return view._create_initial_knockout_pairings(round_, bracket)
        else:
            # Create next round pairings based on advancement
            return view._create_missing_knockout_matches(round_, bracket)
    else:
        # Individual tournament logic
        if LonePlayerPairing.objects.filter(round=round_).exists():
            raise PairingGenerationException(f"Pairings already exist for round {round_.number}")
            
        if round_.number == 1:
            # Create initial individual pairings from season players
            return _create_initial_individual_knockout_pairings(round_, bracket)
        else:
            # Individual tournaments advancement not implemented yet
            raise PairingGenerationException("Individual knockout advancement not implemented yet")


def _create_initial_individual_knockout_pairings(round_, bracket):
    """Create initial knockout pairings for individual tournaments."""
    from django.db import transaction
    import reversion
    
    # Get active players
    season_players = (
        SeasonPlayer.objects.filter(season=round_.season, is_active=True)
        .select_related("player")
        .order_by("id")
    )
    
    players = [sp.player for sp in season_players]
    
    if len(players) % 2 != 0:
        raise PairingGenerationException(f"Cannot create pairings with odd number of players: {len(players)}")
    
    # Generate first round pairings using proper bracket ordering
    from heltour.tournament_core.knockout import (
        generate_knockout_seedings_traditional,
        generate_knockout_seedings_adjacent,
    )
    
    if bracket.seeding_style == "traditional":
        pairings = generate_knockout_seedings_traditional([p.id for p in players])
    else:  # adjacent
        pairings = generate_knockout_seedings_adjacent([p.id for p in players])
    
    # Set round knockout stage
    from heltour.tournament_core.knockout import get_knockout_stage_name
    stage_name = get_knockout_stage_name(len(players))
    round_.knockout_stage = stage_name
    round_.save()
    
    # Create lone player pairings
    rank_dict = lone_player_pairing_rank_dict(round_.season)
    created_count = 0
    
    for i, (player1_id, player2_id) in enumerate(pairings):
        player1 = next(p for p in players if p.id == player1_id)
        player2 = next(p for p in players if p.id == player2_id)
        
        with reversion.create_revision():
            reversion.set_comment("Generated knockout bracket.")
            lone_pairing = LonePlayerPairing.objects.create(
                white=player1,
                black=player2,
                round=round_,
                pairing_order=i + 1,
            )
            lone_pairing.refresh_ranks(rank_dict)
            lone_pairing.save()
            created_count += 1
    
    return created_count


def advance_knockout_tournament(round_):
    """
    Calculate advancement for completed knockout round and create next round.

    Args:
        round_: Completed Round object

    Returns:
        Round: The next round created, or None if tournament is complete

    Raises:
        PairingGenerationException: If advancement calculation fails
    """
    if round_.season.league.pairing_type not in ["knockout-single", "knockout-multi"]:
        raise PairingGenerationException(
            f"Season {round_.season} is not a knockout tournament"
        )

    # Check if tournament is complete
    bracket = KnockoutBracket.objects.get(season=round_.season)

    if round_.season.league.competitor_type == "team":
        # For multi-match tournaments, count unique team pairs, not individual pairings
        team_pairings = TeamPairing.objects.filter(round=round_).select_related(
            "white_team", "black_team"
        )
        unique_team_pairs = set()
        for pairing in team_pairings:
            if pairing.black_team:  # Skip byes
                team_key = tuple(sorted([pairing.white_team.id, pairing.black_team.id]))
                unique_team_pairs.add(team_key)

        remaining_teams = len(unique_team_pairs) * 2
        if remaining_teams == 2:
            # Finals completed - tournament is done
            bracket.is_completed = True
            bracket.save()
            return None
    else:
        # For individual tournaments, similar logic would apply if multi-match is supported
        remaining_players = LonePlayerPairing.objects.filter(round=round_).count() * 2
        if remaining_players == 2:
            # Finals completed - tournament is done
            bracket.is_completed = True
            bracket.save()
            return None

    # Create next round (use get_or_create to avoid duplicates)
    next_round, created = round_.season.round_set.get_or_create(
        number=round_.number + 1,
        defaults={
            "start_date": round_.end_date,
            "end_date": round_.end_date + (round_.end_date - round_.start_date),
        },
    )

    # Generate pairings for next round
    generate_pairings(next_round)

    return next_round
