"""
Convert tournament_core structures to database objects.

This module provides functions to convert pure tournament structures created by
the TournamentBuilder into Django database models for persistence.
"""

from heltour.tournament_core.builder import TournamentBuilder


def structure_to_db(builder: TournamentBuilder, existing_league=None):
    """Convert a TournamentBuilder's structure to database objects.

    This function creates all necessary database objects including:
    - League and Season
    - Teams/Players and registrations
    - Rounds and pairings with board results
    - Byes for teams/players without pairings

    Args:
        builder: A TournamentBuilder instance with tournament structure and metadata
        existing_league: Optional existing League instance to use instead of creating new

    Returns:
        dict: A dictionary containing the created database objects:
            - 'league': The League instance
            - 'season': The Season instance
            - 'teams': Dict mapping team names to Team instances
            - 'players': Dict mapping player names to Player instances
            - 'rounds': List of Round instances
    """
    from heltour.tournament.models import (
        League,
        Season,
        Round,
        Team,
        Player,
        SeasonPlayer,
        TeamMember,
        TeamScore,
        LonePlayerScore,
        TeamPairing,
        TeamPlayerPairing,
        LonePlayerPairing,
        Registration,
        TeamBye,
        PlayerBye,
    )
    from django.utils.text import slugify

    tournament = builder.tournament
    metadata = builder.metadata

    # Use existing league or create a new one
    if existing_league:
        league = existing_league
    else:
        # Generate a web-safe slug if tag contains non-ASCII characters
        import re

        tag = metadata.league_tag or "TL"
        # If tag contains non-ASCII characters, slugify it
        if not tag.isascii():
            tag = slugify(tag)
            # If slugify results in empty string, use a default
            if not tag:
                tag = "trf16-import"

        league_data = {
            "name": metadata.league_name or "Test League",
            "tag": tag,
            "competitor_type": metadata.competitor_type,
            "rating_type": metadata.league_settings.get("rating_type", "standard"),
            "pairing_type": metadata.league_settings.get("pairing_type", "swiss-dutch"),
            "theme": metadata.league_settings.get("theme", "blue"),
            # Knockout-specific settings
            "knockout_games_per_match": metadata.league_settings.get(
                "knockout_games_per_match", 1
            ),
            "knockout_seeding_style": metadata.league_settings.get(
                "knockout_seeding_style", "traditional"
            ),
        }

        # Configure tiebreaks for team tournaments
        if metadata.competitor_type == "team":
            # Default tiebreak order: Game Points, Sonneborn-Berger, Buchholz, Games Won
            league_data["team_tiebreak_1"] = metadata.league_settings.get(
                "team_tiebreak_1", "game_points"
            )
            league_data["team_tiebreak_2"] = metadata.league_settings.get(
                "team_tiebreak_2", "sonneborn_berger"
            )
            league_data["team_tiebreak_3"] = metadata.league_settings.get(
                "team_tiebreak_3", "buchholz"
            )
            league_data["team_tiebreak_4"] = metadata.league_settings.get(
                "team_tiebreak_4", "games_won"
            )
        # Add any additional league settings
        for key, value in metadata.league_settings.items():
            if key not in league_data:
                league_data[key] = value

        league, created = League.objects.get_or_create(
            tag=league_data["tag"], defaults=league_data
        )

    # Import timezone at the top if not already
    from django.utils import timezone

    # Generate a unique season tag from the season name
    import re

    season_name = metadata.season_name or "Test Season"
    base_tag = re.sub(r"[^a-zA-Z0-9]", "", season_name.lower())[
        :20
    ]  # Clean and truncate
    if not base_tag:  # If no valid characters, use a default
        base_tag = "season"

    # Ensure tag is unique within the league
    tag = base_tag
    counter = 2
    while Season.objects.filter(league=league, tag=tag).exists():
        tag = f"{base_tag}{counter}"
        counter += 1

    # Create Season
    # Generate unique tag based on season name
    season_name = metadata.season_name or "Test Season"
    base_tag = (
        season_name.lower().replace(" ", "_").replace("-", "_")[:20]
    )  # Limit length
    tag = base_tag
    counter = 1
    while Season.objects.filter(league=league, tag=tag).exists():
        tag = f"{base_tag}_{counter}"
        counter += 1

    season_data = {
        "league": league,
        "name": season_name,
        "rounds": metadata.season_settings.get("rounds", len(tournament.rounds)) or 1,
        "boards": metadata.boards if metadata.competitor_type == "team" else None,
        "is_active": True,  # Make the season visible
        "tag": tag,  # Use generated unique tag
        "start_date": timezone.now(),  # Set start date
    }
    # Add any additional season settings
    for key, value in metadata.season_settings.items():
        if key not in season_data and key != "player_kwargs":
            season_data[key] = value

    # Check if a season with this name already exists for this league
    existing_seasons = Season.objects.filter(league=league, name=season_data["name"])
    if existing_seasons.exists():
        # Append a number to make it unique
        base_name = season_data["name"]
        counter = 2
        while Season.objects.filter(
            league=league, name=f"{base_name} ({counter})"
        ).exists():
            counter += 1
        season_data["name"] = f"{base_name} ({counter})"

    season = Season.objects.create(**season_data)

    # Track created objects
    db_players = {}  # player_name -> Player instance (use name as key instead of ID)
    db_teams = {}  # team_name -> Team instance
    db_rounds = []  # List of Round instances

    if metadata.competitor_type == "team":
        # Create teams and players
        for team_name, team_info in metadata.teams.items():
            # Calculate seed rating as average of player ratings if not provided
            if "seed_rating" not in team_info and team_info["players"]:
                total_rating = sum(p.get("rating", 1500) for p in team_info["players"])
                seed_rating = total_rating / len(team_info["players"])
            else:
                seed_rating = team_info.get("seed_rating", 1500)

            # Create team
            team = Team.objects.create(
                season=season,
                name=team_name,
                number=team_info["id"],
                is_active=True,
                seed_rating=seed_rating,
            )
            TeamScore.objects.create(team=team)
            db_teams[team_name] = team

            # Create players and team members
            for i, player_info in enumerate(team_info["players"], 1):
                player_name = player_info["name"]
                player_id = player_info["id"]
                rating = player_info.get("rating", 1500)

                # Create or get player (using name as key to avoid ID conflicts)
                if player_name not in db_players:
                    # Check if the player name is already a valid username (alphanumeric, hyphen, underscore)
                    import re

                    if re.match(r"^[-\w]+$", player_name):
                        # Already looks like a valid username, use as-is
                        username = player_name
                    else:
                        # Need to slugify for web-safe URLs
                        username = slugify(player_name)
                        if not username:
                            # If slugify results in empty string, create a fallback
                            username = f"player-{player_id}"

                    # Try to find existing player first
                    player, created = Player.objects.get_or_create(
                        lichess_username=username,
                        defaults={
                            "rating": rating,
                            "profile": {
                                "perfs": {
                                    "standard": {
                                        "rating": rating,
                                        "games": 100,
                                        "prov": False,
                                    },
                                    "classical": {
                                        "rating": rating,
                                        "games": 100,
                                        "prov": False,
                                    },
                                }
                            },
                        },
                    )
                    if not created:
                        # Update rating if player already exists
                        player.rating = rating
                        player.save()
                    db_players[player_name] = player
                else:
                    player = db_players[player_name]

                # Create season player (use get_or_create to avoid duplicates)
                SeasonPlayer.objects.get_or_create(
                    season=season,
                    player=player,
                    defaults={"seed_rating": rating, "is_active": True},
                )

                # Create team member
                TeamMember.objects.create(team=team, player=player, board_number=i)
    else:
        # Create individual players
        player_kwargs = metadata.season_settings.get("player_kwargs", {})
        for player_name, player_id in metadata.players.items():
            kwargs = player_kwargs.get(player_id, {})
            rating = kwargs.get("rating", 1500)

            # Create player (check by name to avoid duplicates)
            if player_name not in db_players:
                # Check if the player name is already a valid username (alphanumeric, hyphen, underscore)
                import re

                if re.match(r"^[-\w]+$", player_name):
                    # Already looks like a valid username, use as-is
                    username = player_name
                else:
                    # Need to slugify for web-safe URLs
                    username = slugify(player_name)
                    if not username:
                        # If slugify results in empty string, create a fallback
                        username = f"player-{player_id}"

                player = Player.objects.create(
                    lichess_username=username,
                    rating=rating,
                    profile={
                        "perfs": {
                            "standard": {"rating": rating, "games": 100, "prov": False},
                            "classical": {
                                "rating": rating,
                                "games": 100,
                                "prov": False,
                            },
                        }
                    },
                )
                db_players[player_name] = player
            else:
                player = db_players[player_name]

            # Create registration
            Registration.objects.create(
                season=season,
                player=player,
                status="approved",
                has_played_20_games=True,
                can_commit=True,
                agreed_to_rules=True,
                agreed_to_tos=True,
            )

            # Create season player
            sp = SeasonPlayer.objects.create(
                season=season, player=player, seed_rating=rating, is_active=True
            )
            LonePlayerScore.objects.create(season_player=sp)

    # Create a mapping from builder player IDs to database player instances
    player_id_to_db = {}
    for player_name, player_id in metadata.players.items():
        if player_name in db_players:
            player_id_to_db[player_id] = db_players[player_name]

    # Create rounds and pairings
    from datetime import timedelta
    from django.utils import timezone

    for round_struct in tournament.rounds:
        # Create round with proper dates
        round_start = timezone.now() + timedelta(weeks=(round_struct.number - 1))
        round_end = round_start + timedelta(days=7)

        # Include knockout stage if present
        round_defaults = {
            "start_date": round_start,
            "end_date": round_end,
            "is_completed": False,
            "publish_pairings": True,
        }

        # Add knockout stage if tournament is knockout format
        if hasattr(round_struct, "knockout_stage") and round_struct.knockout_stage:
            round_defaults["knockout_stage"] = round_struct.knockout_stage

        round_obj, created = Round.objects.get_or_create(
            season=season,
            number=round_struct.number,
            defaults=round_defaults,
        )
        # Ensure publish_pairings is True even for existing rounds
        if not created and not round_obj.publish_pairings:
            round_obj.publish_pairings = True
            round_obj.save()
        db_rounds.append(round_obj)

        # Track who played in this round and who has byes
        competitors_played = set()
        competitors_with_byes = set()

        # Create pairings
        pairing_order = 0
        for match in round_struct.matches:
            pairing_order += 1

            if match.is_bye:
                # Handle bye
                competitors_with_byes.add(match.competitor1_id)
                if metadata.competitor_type == "team":
                    # Find team by ID
                    team = next(
                        (
                            t
                            for t in db_teams.values()
                            if t.number == match.competitor1_id
                        ),
                        None,
                    )
                    if team:
                        # Use get_or_create to avoid duplicates
                        TeamBye.objects.get_or_create(
                            round=round_obj,
                            team=team,
                            defaults={"type": "full-point-pairing-bye"},
                        )
                else:
                    # Find player by ID
                    player = player_id_to_db.get(match.competitor1_id)
                    if player:
                        bye_type = _match_to_bye_type(match)
                        # Use get_or_create to avoid duplicates
                        PlayerBye.objects.get_or_create(
                            round=round_obj,
                            player=player,
                            defaults={"type": bye_type},
                        )
            else:
                competitors_played.add(match.competitor1_id)
                competitors_played.add(match.competitor2_id)

                if metadata.competitor_type == "team":
                    # Create team pairing
                    team1 = next(
                        (
                            t
                            for t in db_teams.values()
                            if t.number == match.competitor1_id
                        ),
                        None,
                    )
                    team2 = next(
                        (
                            t
                            for t in db_teams.values()
                            if t.number == match.competitor2_id
                        ),
                        None,
                    )

                    if team1 and team2:
                        # Include manual tiebreak value if present
                        pairing_data = {
                            "round": round_obj,
                            "white_team": team1,
                            "black_team": team2,
                            "pairing_order": pairing_order,
                        }

                        # Add manual tiebreak if present
                        if (
                            hasattr(match, "manual_tiebreak_value")
                            and match.manual_tiebreak_value is not None
                        ):
                            pairing_data["manual_tiebreak_value"] = (
                                match.manual_tiebreak_value
                            )

                        team_pairing = TeamPairing.objects.create(**pairing_data)

                        # Create board pairings
                        for board_num, game in enumerate(match.games, 1):
                            # Get players (None for forfeit opponent with ID -1)
                            white_player = (
                                player_id_to_db.get(game.player1.player_id)
                                if game.player1.player_id != -1
                                else None
                            )
                            black_player = (
                                player_id_to_db.get(game.player2.player_id)
                                if game.player2.player_id != -1
                                else None
                            )

                            # Create pairing even if one player is missing (forfeit)
                            if white_player or black_player:
                                # Convert result
                                result_str = _game_result_to_string(game.result)

                                TeamPlayerPairing.objects.create(
                                    team_pairing=team_pairing,
                                    board_number=board_num,
                                    white=white_player,
                                    black=black_player,
                                    result=result_str,
                                )

                        # Update pairing points
                        team_pairing.refresh_points()
                        team_pairing.save()
                else:
                    # Create individual pairing
                    player1 = player_id_to_db.get(match.competitor1_id)
                    player2 = player_id_to_db.get(match.competitor2_id)

                    if player1 and player2 and match.games:
                        game = match.games[0]
                        result_str = _game_result_to_string(game.result)

                        LonePlayerPairing.objects.create(
                            round=round_obj,
                            white=player1,
                            black=player2,
                            result=result_str,
                            pairing_order=pairing_order,
                        )

        # Create byes for competitors who didn't play and don't already have byes
        if metadata.competitor_type == "team":
            all_team_ids = set(t.number for t in db_teams.values())
            teams_without_pairing = (
                all_team_ids - competitors_played - competitors_with_byes
            )

            for team_id in teams_without_pairing:
                team = next((t for t in db_teams.values() if t.number == team_id), None)
                if team:
                    # Use get_or_create to avoid duplicates
                    TeamBye.objects.get_or_create(
                        round=round_obj,
                        team=team,
                        defaults={"type": "full-point-pairing-bye"},
                    )

        # Mark round as completed
        round_obj.is_completed = True
        round_obj.save()

    # Calculate scores
    season.calculate_scores()

    return {
        "league": league,
        "season": season,
        "teams": db_teams,
        "players": db_players,  # Already keyed by name
        "rounds": db_rounds,
    }


def _game_result_to_string(result) -> str:
    """Convert GameResult enum to database string format."""
    from heltour.tournament_core.structure import GameResult

    result_map = {
        GameResult.P1_WIN: "1-0",
        GameResult.DRAW: "1/2-1/2",
        GameResult.P2_WIN: "0-1",
        GameResult.P1_FORFEIT_WIN: "1X-0F",
        GameResult.P2_FORFEIT_WIN: "0F-1X",
        GameResult.DOUBLE_FORFEIT: "0F-0F",
    }

    return result_map.get(result, "")


def _match_to_bye_type(match) -> str:
    """Derive the PlayerBye type from a bye Match's effective game points."""
    if match.bye_game_points is not None:
        gp = match.bye_game_points
    else:
        gp, _ = match.game_points()

    if gp >= 1.0:
        return "full-point-pairing-bye"
    elif gp > 0:
        return "half-point-bye"
    else:
        return "zero-point-bye"
