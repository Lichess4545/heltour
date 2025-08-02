"""
Pairing seeder for creating test pairings.
"""

import random
from typing import List, Optional
from django.utils import timezone
from heltour.tournament.models import (
    Round,
    Team,
    TeamPairing,
    TeamPlayerPairing,
    LonePlayerPairing,
    SeasonPlayer,
    PlayerBye,
)
from .base import BaseSeeder


class PairingSeeder(BaseSeeder):
    """Seeder for creating Pairing objects."""

    # Game link patterns for different results
    GAME_LINKS = {
        "win": "https://lichess.org/abcdef123",
        "loss": "https://lichess.org/ghijkl456",
        "draw": "https://lichess.org/mnopqr789",
        "forfeit": "",
    }

    def seed(self, round_obj: Round, **kwargs) -> List:
        """Create pairings for a round."""
        if round_obj.season.league.is_team_league():
            return self.seed_team_pairings(round_obj, **kwargs)
        else:
            return self.seed_lone_pairings(round_obj, **kwargs)

    def seed_team_pairings(self, round_obj: Round, **kwargs) -> List[TeamPairing]:
        """Create team pairings for a round."""
        pairings = []

        # Get active teams
        teams = list(
            Team.objects.filter(season=round_obj.season, is_active=True).order_by(
                "number"
            )
        )

        if len(teams) < 2:
            return pairings

        # Simple Swiss-style pairing simulation
        # In real Swiss, teams are paired based on score, but for seeding
        # we'll simulate by having teams play different opponents each round
        round_num = round_obj.number

        # Get previous pairings to avoid repeat matchups
        from heltour.tournament.models import TeamPairing

        previous_pairings = TeamPairing.objects.filter(
            round__season=round_obj.season, round__number__lt=round_num
        )

        # Build a set of who has played whom
        played_pairs = set()
        for pairing in previous_pairings:
            played_pairs.add((pairing.white_team_id, pairing.black_team_id))
            played_pairs.add((pairing.black_team_id, pairing.white_team_id))

        # Simple Swiss pairing - try to avoid repeat matchups
        teams_to_pair = list(teams)
        random.shuffle(teams_to_pair)  # Shuffle for variety
        pairings_for_round = []

        # Keep track of which teams we've paired this round
        paired_teams = set()

        # First pass: try to pair teams that haven't played each other
        for team1 in teams_to_pair:
            if team1.id in paired_teams:
                continue

            for team2 in teams_to_pair:
                if team2.id in paired_teams or team1.id == team2.id:
                    continue

                if (team1.id, team2.id) not in played_pairs:
                    # Found a valid pairing
                    pairings_for_round.append((team1, team2))
                    paired_teams.add(team1.id)
                    paired_teams.add(team2.id)
                    break

        # Second pass: pair any remaining unpaired teams
        unpaired = [t for t in teams_to_pair if t.id not in paired_teams]
        while len(unpaired) >= 2:
            team1 = unpaired.pop(0)
            team2 = unpaired.pop(0)
            pairings_for_round.append((team1, team2))
            paired_teams.add(team1.id)
            paired_teams.add(team2.id)

        # Sanity check - all teams should be paired
        if len(paired_teams) != len(teams):
            print(
                f"WARNING: Round {round_num} - Only {len(paired_teams)} of {len(teams)} teams paired!"
            )

        print(
            f"Round {round_num}: Creating {len(pairings_for_round)} pairings for {len(teams)} teams"
        )

        # Create the pairings
        for pairing_idx, (white_team, black_team) in enumerate(pairings_for_round):

            pairing_data = {
                "round": round_obj,
                "white_team": white_team,
                "black_team": black_team,
                "pairing_order": pairing_idx + 1,
            }
            pairing_data.update(kwargs)

            team_pairing = TeamPairing.objects.create(**pairing_data)
            pairings.append(self._track_object(team_pairing))

            # Create player pairings for each board
            self._create_board_pairings(team_pairing, round_obj)

            # Refresh team pairing points after creating all board pairings
            team_pairing.refresh_points()
            team_pairing.save()  # Save to trigger score calculation

        # Handle odd team (gets a bye)
        if len(teams) % 2 == 1:
            # In round-robin with odd teams, one team sits out each round
            # The unpaired team is the one that would have been paired with the "ghost" team
            pass

        return pairings

    def _create_board_pairings(self, team_pairing: TeamPairing, round_obj: Round):
        """Create individual board pairings for a team pairing."""
        boards = round_obj.season.boards or 4

        white_members = team_pairing.white_team.teammember_set.all()
        black_members = team_pairing.black_team.teammember_set.all()

        for board_num in range(1, boards + 1):
            # Get players for this board
            white_member = white_members.filter(board_number=board_num).first()
            black_member = black_members.filter(board_number=board_num).first()

            if not white_member or not black_member:
                # Skip if either team is missing a player for this board
                # This shouldn't happen with our team creation logic
                continue

            # Determine game result
            result = self._generate_game_result(
                round_obj, white_member.player, black_member.player
            )

            # For completed rounds, ensure we always have a result
            if round_obj.is_completed and not result["result"]:
                # Default to a draw if no result was generated
                result = {
                    "result": "1/2-1/2",
                    "game_link": f"https://lichess.org/{self.fake.lexify('????????')}",
                }

            player_pairing = TeamPlayerPairing.objects.create(
                team_pairing=team_pairing,
                board_number=board_num,
                white=white_member.player,
                black=black_member.player,
                result=result["result"],
                game_link=result["game_link"],
                scheduled_time=self._get_scheduled_time(round_obj),
            )

    def seed_lone_pairings(self, round_obj: Round, **kwargs) -> List[LonePlayerPairing]:
        """Create lone player pairings for a round."""
        pairings = []

        # Get active season players
        season_players = list(
            SeasonPlayer.objects.filter(
                season=round_obj.season, is_active=True
            ).select_related("player")
        )

        if len(season_players) < 2:
            return pairings

        # Sort by rating for Swiss pairing simulation
        season_players.sort(
            key=lambda sp: sp.player.rating_for(round_obj.season.league), reverse=True
        )

        # Simple pairing by rating groups
        paired_players = []
        pairing_order = 1

        for i in range(0, len(season_players) - 1, 2):
            white_sp = season_players[i]
            black_sp = season_players[i + 1]

            result = self._generate_game_result(
                round_obj, white_sp.player, black_sp.player
            )

            lone_pairing = LonePlayerPairing.objects.create(
                round=round_obj,
                white=white_sp.player,
                black=black_sp.player,
                pairing_order=pairing_order,
                result=result["result"],
                game_link=result["game_link"],
                scheduled_time=self._get_scheduled_time(round_obj),
                **kwargs,
            )
            pairings.append(self._track_object(lone_pairing))

            paired_players.extend([white_sp, black_sp])
            pairing_order += 1

        # Handle odd player (gets a bye)
        if len(season_players) % 2 == 1:
            bye_player = season_players[-1].player
            PlayerBye.objects.create(
                round=round_obj,
                player=bye_player,
                type="full-point",
            )

        return pairings

    def _generate_game_result(
        self, round_obj: Round, white: "Player", black: "Player"
    ) -> dict:
        """Generate a realistic game result."""
        # Only generate results for completed rounds
        if not round_obj.is_completed:
            return {"result": "", "game_link": ""}

        # Always generate a result for completed rounds
        # (Remove the random chance of no result)

        # Calculate expected score based on rating difference
        white_rating = white.rating_for(round_obj.season.league)
        black_rating = black.rating_for(round_obj.season.league)
        rating_diff = white_rating - black_rating

        # Expected score for white (Elo formula)
        expected_white = 1 / (1 + 10 ** (-rating_diff / 400))

        # Generate result with some randomness
        rand = random.random()

        # Small chance of forfeit
        if rand < 0.05:
            if random.random() < 0.5:
                return {"result": "1X", "game_link": ""}  # White wins by forfeit
            else:
                return {"result": "0F", "game_link": ""}  # Black wins by forfeit

        # Normal game results
        if rand < expected_white - 0.1:  # Slightly favor expected result
            result = "1-0"
            game_type = "win"
        elif rand > expected_white + 0.1:
            result = "0-1"
            game_type = "loss"
        else:
            result = "1/2-1/2"
            game_type = "draw"

        # Generate game link
        game_id = self.fake.lexify("????????")
        game_link = f"https://lichess.org/{game_id}"

        return {"result": result, "game_link": game_link}

    def _get_scheduled_time(self, round_obj: Round) -> Optional[timezone.datetime]:
        """Get scheduled time for a round."""
        if not round_obj.season.start_date:
            return None

        # Calculate round start date
        round_start = (
            round_obj.season.start_date
            + (round_obj.number - 1) * round_obj.season.round_duration
        )

        # Add some random hours for game time (evening/weekend)
        hour = random.choice([18, 19, 20, 21])  # Evening times
        minute = random.choice([0, 30])

        return round_start.replace(hour=hour, minute=minute)
