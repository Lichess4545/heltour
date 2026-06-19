"""
Example usage of TRF16 parser and converter.

This script demonstrates how to use the TRF16 parser to:
1. Parse tournament structure and teams
2. Extract pairings for validation
3. Create tournament structures for testing
"""

from heltour.tournament_core.trf16 import TRF16Parser
from heltour.tournament_core.trf16_converter import TRF16Converter
from heltour.tournament_core.assertions import assert_tournament


def parse_teams_only(trf16_content: str):
    """Example: Parse only teams and players without results."""
    parser = TRF16Parser(trf16_content)

    # Parse header to get tournament info
    header = parser.parse_header()
    print(f"Tournament: {header.tournament_name}")
    print(f"Teams: {header.num_teams}")
    print(f"Players: {header.num_players}")

    # Parse teams and players
    players = parser.parse_players()
    teams = parser.parse_teams()
    parser.update_board_numbers()

    # Print team rosters
    for team_name, team in teams.items():
        print(f"\n{team_name}:")
        for player_id in team.player_ids:
            if player_id in players:
                player = players[player_id]
                print(f"  Board {player.board_number}: {player.name} ({player.rating})")


def validate_round_pairings(trf16_content: str, round_number: int):
    """Example: Extract and validate pairings for a specific round."""
    parser = TRF16Parser(trf16_content)
    parser.parse_all()
    parser.update_board_numbers()

    # Get pairings for the round
    pairings = parser.parse_round_pairings(round_number)

    print(f"\nRound {round_number} pairings:")

    # Group by teams (simplified version)
    for pairing in pairings:
        if pairing.white_player_id and pairing.black_player_id:
            white = parser.players[pairing.white_player_id]
            black = parser.players[pairing.black_player_id]

            print(
                f"  Board {pairing.board_number}: {white.name} vs {black.name} = {pairing.result}"
            )


def create_test_tournament(trf16_content: str, rounds_to_import: list = None):
    """Example: Create a test tournament from TRF16 data."""
    converter = TRF16Converter(trf16_content)
    converter.parse()

    # Create tournament with teams
    builder = converter.create_tournament_builder()

    # Add specific rounds (or all if not specified)
    converter.add_rounds_to_builder(builder, rounds_to_import)

    # Build and return tournament
    tournament = builder.build()

    # Calculate and display standings
    results = tournament.calculate_results()
    print("\nStandings:")

    # Sort teams by points
    sorted_teams = sorted(
        [
            (team_name, team_info["id"])
            for team_name, team_info in builder.metadata.teams.items()
        ],
        key=lambda x: -results[x[1]].match_points,
    )

    for team_name, team_id in sorted_teams:
        score = results[team_id]
        print(
            f"  {team_name}: {score.match_points} match pts, {score.game_points} game pts"
        )

    return tournament


def main():
    """Example usage with sample data."""
    # Sample TRF16 data
    sample_trf16 = """012 Sample Team Tournament
022 Test City
032 USA
042 2024/01/01
052 2024/01/02
062 8 (8)
072 8
082 2
092 Team Swiss System
102 Chief Arbiter
112 Deputy Arbiter
122 90+30
142 2

001    1 m    Alice Johnson                     2200 USA    12345678 1990/01/01  2.0   1     5 w 1     7 b 1
001    2 m    Bob Smith                         2150 USA    12345679 1991/01/01  1.0   4     6 b =     8 w =
001    3 m    Carol White                       2100 USA    12345680 1992/01/01  1.5   2     7 w =     5 b 1
001    4 m    David Brown                       2050 USA    12345681 1993/01/01  0.5   6     8 b =     6 w 0
001    5 m    Eve Davis                         2180 USA    12345682 1988/01/01  0.0   7     1 b 0     3 w 0
001    6 m    Frank Miller                      2130 USA    12345683 1989/01/01  1.5   3     2 w =     4 b 1
001    7 m    Grace Wilson                      2080 USA    12345684 1994/01/01  0.5   5     3 b =     1 w 0
001    8 m    Henry Moore                       2030 USA    12345685 1995/01/01  0.5   8     4 w =     2 b =

013 Team Alpha                          1    2
013 Team Beta                           3    4
013 Team Gamma                          5    6
013 Team Delta                          7    8"""

    print("=== TRF16 Parser Examples ===\n")

    # Example 1: Parse teams only
    print("1. Parsing teams and players:")
    parse_teams_only(sample_trf16)

    # Example 2: Validate round pairings
    print("\n2. Validating round pairings:")
    validate_round_pairings(sample_trf16, 1)
    validate_round_pairings(sample_trf16, 2)

    # Example 3: Create test tournament
    print("\n3. Creating test tournament:")
    tournament = create_test_tournament(sample_trf16)

    # Example 4: Use assertions to verify
    print("\n4. Verifying with assertions:")
    try:
        assert_tournament(tournament).team("Team Alpha").assert_().match_points(
            4
        ).position(1)
        print("  ✓ Team Alpha has 4 match points and is in 1st place")
    except AssertionError as e:
        print(f"  ✗ Assertion failed: {e}")


if __name__ == "__main__":
    main()

