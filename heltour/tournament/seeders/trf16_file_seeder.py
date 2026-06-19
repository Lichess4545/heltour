"""
TRF16 file-based tournament seeder.

This module provides functions to seed tournaments from TRF16 files.
"""

import os
from heltour.tournament_core.trf16_converter import TRF16Converter
from heltour.tournament.structure_to_db import structure_to_db
from django.db import transaction


@transaction.atomic
def seed_complete_tournament(trf16_path, league_tag, existing_league=None):
    """
    Create a complete tournament from a TRF16 file.
    
    Args:
        trf16_path: Path to the TRF16 file
        league_tag: Tag for the league (e.g., "friendship-cup", "championship")
        existing_league: Optional existing League to use instead of creating new
    """
    print(f"=== Seeding complete tournament from {trf16_path} (league: {league_tag}) ===")
    
    # Read TRF16 file
    with open(trf16_path, 'r', encoding='utf-8') as f:
        trf16_data = f.read()
    
    # Create converter and parse TRF16
    converter = TRF16Converter(trf16_data)
    converter.parse()
    
    # Create tournament builder with custom league tag
    builder = converter.create_tournament_builder(league_tag=league_tag)
    
    # Add all rounds
    converter.add_rounds_to_builder(builder)
    
    # Build the tournament structure
    tournament = builder.build()
    
    print(f"Built tournament with {len(tournament.competitors)} competitors and {len(tournament.rounds)} rounds")
    
    # Convert structure to database
    result = structure_to_db(builder, existing_league)
    
    # Print final standings
    print("\n=== Final Standings ===")
    results = tournament.calculate_results()
    
    # Sort by match points
    sorted_teams = sorted(
        results.items(), 
        key=lambda x: (x[1].match_points, x[1].game_points),
        reverse=True
    )
    
    for i, (team_id, score) in enumerate(sorted_teams, 1):
        # Find team name
        team_name = None
        for name, info in builder.metadata.teams.items():
            if info["id"] == team_id:
                team_name = name
                break
        if team_name:
            print(f"{i:2d}. {team_name:30s} - MP: {score.match_points:.1f}, GP: {score.game_points:.1f}")
    
    return result["season"]


@transaction.atomic
def seed_partial_tournament(trf16_path, league_tag, num_rounds=1, include_results=True, existing_league=None):
    """
    Create a partial tournament with specified number of rounds.
    
    Args:
        trf16_path: Path to the TRF16 file
        league_tag: Tag for the league
        num_rounds: Number of rounds to create
        include_results: Whether to include game results
        existing_league: Optional existing League to use
    """
    print(f"=== Seeding {num_rounds} round(s) {'with results' if include_results else 'without results'} ===")
    
    # Read TRF16 file
    with open(trf16_path, 'r', encoding='utf-8') as f:
        trf16_data = f.read()
    
    # Create converter and parse TRF16
    converter = TRF16Converter(trf16_data)
    converter.parse()
    
    # Create tournament builder
    builder = converter.create_tournament_builder(league_tag=league_tag)
    
    # Add specified rounds
    converter.add_rounds_to_builder(builder, max_rounds=num_rounds, include_results=include_results)
    
    # Build the tournament structure
    tournament = builder.build()
    
    # Convert structure to database
    result = structure_to_db(builder, existing_league)
    
    print(f"Created {num_rounds} round(s) for {result['season'].name}")
    return result["season"]


@transaction.atomic
def seed_teams_only(trf16_path, league_tag, existing_league=None):
    """
    Create only teams without any rounds or pairings.
    
    Args:
        trf16_path: Path to the TRF16 file
        league_tag: Tag for the league
        existing_league: Optional existing League to use
    """
    print("=== Seeding teams only (no rounds) ===")
    
    # Read TRF16 file
    with open(trf16_path, 'r', encoding='utf-8') as f:
        trf16_data = f.read()
    
    # Create converter and parse TRF16
    converter = TRF16Converter(trf16_data)
    converter.parse()
    
    # Create tournament builder
    builder = converter.create_tournament_builder(league_tag=league_tag)
    
    # Don't add any rounds - just build with teams
    tournament = builder.build()
    
    # Convert structure to database
    result = structure_to_db(builder, existing_league)
    
    print(f"Created {len(result['teams'])} teams for {result['season'].name}")
    return result["season"]


def get_predefined_tournaments():
    """Get list of predefined TRF16 tournaments."""
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'trf16')
    tournaments = {}
    
    if os.path.exists(data_dir):
        for filename in os.listdir(data_dir):
            if filename.endswith('.trf'):
                name = filename[:-4]  # Remove .trf extension
                tournaments[name] = os.path.join(data_dir, filename)
    
    return tournaments