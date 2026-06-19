"""
Tests for knockout tournament functionality using the simulation framework.

This module tests knockout tournaments using the TournamentBuilder simulation
framework, avoiding manual database manipulation and properly exercising
all knockout tournament features.
"""

from django.test import TestCase, TransactionTestCase
from heltour.tournament.builder import TournamentBuilder
from heltour.tournament.db_to_structure import season_to_tournament_structure
from heltour.tournament_core.structure import TournamentFormat
from heltour.tournament.models import (
    KnockoutBracket,
    KnockoutSeeding,
    KnockoutAdvancement,
    Round,
    TeamPairing,
    LonePlayerPairing,
)


class KnockoutSimulationTestCase(TransactionTestCase):
    """Test knockout tournament simulation and integration."""

    def test_simple_team_knockout(self):
        """Test basic 4-team knockout tournament simulation."""
        tournament = (
            TournamentBuilder()
            .league("Knockout Champions", "KC", "team")
            .knockout_format(seeding_style="traditional", games_per_match=1)
            .season("KC", "Spring Finals", rounds=2, boards=2)
            # Four teams for quarterfinals
            .team("Dragons", ("Dragon1", 2100), ("Dragon2", 2000))
            .team("Knights", ("Knight1", 1950), ("Knight2", 1900))
            .team("Wizards", ("Wizard1", 1850), ("Wizard2", 1800))
            .team("Phoenix", ("Phoenix1", 1750), ("Phoenix2", 1700))
            .build()
        )

        season = tournament.current_season
        
        # Generate knockout bracket
        from heltour.tournament.pairinggen import generate_knockout_bracket, create_knockout_pairings
        bracket = generate_knockout_bracket(season)
        
        # Verify bracket creation
        self.assertEqual(bracket.bracket_size, 4)
        self.assertEqual(bracket.seeding_style, "traditional")
        
        # Verify seedings were created
        seedings = KnockoutSeeding.objects.filter(bracket=bracket).order_by('seed_number')
        self.assertEqual(seedings.count(), 4)
        self.assertEqual(seedings[0].seed_number, 1)
        self.assertEqual(seedings[3].seed_number, 4)
        
        # Verify first round (semifinals)
        round1 = Round.objects.get(season=season, number=1)
        self.assertEqual(round1.knockout_stage, "semifinals")
        
        # Create pairings using dashboard functionality
        create_knockout_pairings(round1)
        
        # Check pairings were created
        pairings = TeamPairing.objects.filter(round=round1)
        self.assertEqual(pairings.count(), 2)  # 4 teams -> 2 semifinal matches

    def test_individual_knockout(self):
        """Test 4-player individual knockout tournament."""
        tournament = (
            TournamentBuilder()
            .league("Individual Knockout", "IK", "lone")
            .knockout_format(seeding_style="traditional", games_per_match=1)
            .season("IK", "Championship", rounds=2)
            .player("Magnus", 2850)
            .player("Hikaru", 2800)
            .player("Ding", 2750)
            .player("Nepo", 2700)
            .build()
        )

        season = tournament.current_season
        
        # Generate knockout bracket
        from heltour.tournament.pairinggen import generate_knockout_bracket, create_knockout_pairings
        bracket = generate_knockout_bracket(season)
        
        # Verify bracket
        self.assertEqual(bracket.bracket_size, 4)
        
        # Verify first round
        round1 = Round.objects.get(season=season, number=1)
        self.assertEqual(round1.knockout_stage, "semifinals")
        
        # Create pairings using dashboard functionality
        create_knockout_pairings(round1)
        
        # Check individual pairings
        pairings = LonePlayerPairing.objects.filter(round=round1)
        self.assertEqual(pairings.count(), 2)  # 4 players -> 2 matches

    def test_knockout_advancement_simulation(self):
        """Test knockout tournament advancement through multiple rounds."""
        tournament = (
            TournamentBuilder()
            .league("Advancement Test", "AT", "team")
            .knockout_format(seeding_style="traditional", games_per_match=1)
            .season("AT", "Test Tournament", rounds=3, boards=2)
            # 8 teams for proper bracket
            .team("Team1", "Player1A", "Player1B")
            .team("Team2", "Player2A", "Player2B")
            .team("Team3", "Player3A", "Player3B")
            .team("Team4", "Player4A", "Player4B")
            .team("Team5", "Player5A", "Player5B")
            .team("Team6", "Player6A", "Player6B")
            .team("Team7", "Player7A", "Player7B")
            .team("Team8", "Player8A", "Player8B")
            .build()
        )

        season = tournament.current_season
        
        # Generate bracket
        from heltour.tournament.pairinggen import generate_knockout_bracket, create_knockout_pairings
        bracket = generate_knockout_bracket(season)
        
        # Verify 8-team bracket
        self.assertEqual(bracket.bracket_size, 8)
        
        # First round should be quarterfinals
        round1 = Round.objects.get(season=season, number=1)
        self.assertEqual(round1.knockout_stage, "quarterfinals")
        
        # Create pairings using dashboard functionality
        create_knockout_pairings(round1)
        
        # Should have 4 matches
        round1_pairings = TeamPairing.objects.filter(round=round1)
        self.assertEqual(round1_pairings.count(), 4)
        
        # Simulate results for first round
        self._set_team_match_results(round1_pairings)
        round1.is_completed = True
        round1.save()
        
        # Advance to semifinals
        from heltour.tournament.pairinggen import advance_knockout_tournament
        round2 = advance_knockout_tournament(round1)
        
        # Verify advancement
        self.assertIsNotNone(round2)
        self.assertEqual(round2.number, 2)
        self.assertEqual(round2.knockout_stage, "semifinals")
        
        # Should have 2 matches
        round2_pairings = TeamPairing.objects.filter(round=round2)
        self.assertEqual(round2_pairings.count(), 2)
        
        # Verify advancement records were created
        advancements = KnockoutAdvancement.objects.filter(bracket=bracket)
        self.assertEqual(advancements.count(), 4)  # 4 winners from quarterfinals

    def test_knockout_manual_tiebreak(self):
        """Test manual tiebreak resolution in knockout matches."""
        tournament = (
            TournamentBuilder()
            .league("Tiebreak Test", "TT", "team")
            .knockout_format(seeding_style="traditional", games_per_match=1)
            .season("TT", "Manual Tiebreak", rounds=2, boards=2)
            .team("TeamA", "PlayerA1", "PlayerA2")
            .team("TeamB", "PlayerB1", "PlayerB2")
            .team("TeamC", "PlayerC1", "PlayerC2")
            .team("TeamD", "PlayerD1", "PlayerD2")
            .build()
        )

        season = tournament.current_season
        
        # Generate bracket
        from heltour.tournament.pairinggen import generate_knockout_bracket, create_knockout_pairings
        bracket = generate_knockout_bracket(season)
        
        round1 = Round.objects.get(season=season, number=1)
        
        # Create pairings using dashboard functionality
        create_knockout_pairings(round1)
        
        pairings = TeamPairing.objects.filter(round=round1)
        
        # Create tied match requiring manual tiebreak
        tied_pairing = pairings.first()
        tied_pairing.white_points = 1.0
        tied_pairing.black_points = 1.0  # Tied!
        tied_pairing.manual_tiebreak_value = 1.0  # White team wins tiebreak
        tied_pairing.save()
        
        # Set clear result for other match
        other_pairing = pairings.exclude(id=tied_pairing.id).first()
        other_pairing.white_points = 2.0
        other_pairing.black_points = 0.0
        other_pairing.save()
        
        # Complete round
        round1.is_completed = True
        round1.save()
        
        # Advance tournament
        from heltour.tournament.pairinggen import advance_knockout_tournament
        round2 = advance_knockout_tournament(round1)
        
        # Verify advancement with tiebreak resolution
        self.assertIsNotNone(round2)
        
        # Check that tiebreak winner advanced
        finals_pairing = TeamPairing.objects.filter(round=round2).first()
        finalists = {finals_pairing.white_team, finals_pairing.black_team}
        
        # White team should have advanced (tiebreak winner)
        self.assertIn(tied_pairing.white_team, finalists)
        self.assertNotIn(tied_pairing.black_team, finalists)

    def test_knockout_db_to_structure_conversion(self):
        """Test that knockout tournament converts properly to tournament_core."""
        tournament = (
            TournamentBuilder()
            .league("Structure Test", "ST", "team")
            .knockout_format(seeding_style="traditional", games_per_match=1)
            .season("ST", "Conversion Test", rounds=2, boards=2) 
            .team("Alpha", ("AlphaP1", 2000), ("AlphaP2", 1900))
            .team("Beta", ("BetaP1", 1950), ("BetaP2", 1850))
            .team("Gamma", ("GammaP1", 1800), ("GammaP2", 1750))
            .team("Delta", ("DeltaP1", 1700), ("DeltaP2", 1650))
            .build()
        )

        season = tournament.current_season
        
        # Generate knockout bracket  
        from heltour.tournament.pairinggen import generate_knockout_bracket, create_knockout_pairings
        bracket = generate_knockout_bracket(season)
        
        round1 = Round.objects.get(season=season, number=1)
        
        # Create pairings using dashboard functionality
        create_knockout_pairings(round1)
        
        pairings = TeamPairing.objects.filter(round=round1)
        
        # Add board results for all pairings
        from heltour.tournament.models import TeamPlayerPairing
        for i, pairing in enumerate(pairings):
            # Set manual tiebreak for first pairing only
            if i == 0:
                pairing.manual_tiebreak_value = 0.5
                pairing.save()
            
            # Add board results for all pairings
            board_pairings = TeamPlayerPairing.objects.filter(team_pairing=pairing)
            for bp in board_pairings:
                bp.result = "1-0"
                bp.save()
        
        round1.is_completed = True
        round1.save()
        
        # Convert to tournament_core structure
        tournament_structure = season_to_tournament_structure(season)
        
        # Verify knockout format
        self.assertEqual(tournament_structure.format, TournamentFormat.KNOCKOUT)
        
        # Verify round structure
        self.assertEqual(len(tournament_structure.rounds), 1)
        round_struct = tournament_structure.rounds[0]
        self.assertEqual(round_struct.knockout_stage, "semifinals")
        
        # Verify match structure with manual tiebreak
        self.assertEqual(len(round_struct.matches), 2)
        
        # Find the pairing with tiebreak
        tiebreak_pairing = next(
            p for p in pairings 
            if p.manual_tiebreak_value is not None
        )
        
        match_with_tiebreak = next(
            m for m in round_struct.matches 
            if m.competitor1_id == tiebreak_pairing.white_team_id
        )
        self.assertEqual(match_with_tiebreak.manual_tiebreak_value, 0.5)

    def test_multi_game_knockout(self):
        """Test multi-game knockout matches (games_per_match > 1)."""
        tournament = (
            TournamentBuilder()
            .league("Multi-Game Knockout", "MGK", "team")
            .knockout_format(seeding_style="traditional", games_per_match=2)
            .season("MGK", "Double Games", rounds=2, boards=2)
            .team("TeamX", "PlayerX1", "PlayerX2")
            .team("TeamY", "PlayerY1", "PlayerY2") 
            .team("TeamZ", "PlayerZ1", "PlayerZ2")
            .team("TeamW", "PlayerW1", "PlayerW2")
            .build()
        )
        
        season = tournament.current_season
        
        # Generate bracket
        from heltour.tournament.pairinggen import generate_knockout_bracket
        bracket = generate_knockout_bracket(season)
        
        # Verify multi-game setting
        self.assertEqual(bracket.games_per_match, 2)
        
        # Verify structure conversion preserves multi-game setting
        tournament_structure = season_to_tournament_structure(season)
        if tournament_structure.rounds:
            match = tournament_structure.rounds[0].matches[0]
            self.assertEqual(match.games_per_match, 2)

    def _set_team_match_results(self, pairings):
        """Helper to set realistic results for team pairings."""
        from heltour.tournament.models import TeamPlayerPairing
        
        for i, pairing in enumerate(pairings):
            # Alternate winners to create interesting bracket progression
            if i % 2 == 0:
                # White team wins
                pairing.white_points = 1.5
                pairing.black_points = 0.5
            else:
                # Black team wins  
                pairing.white_points = 0.5
                pairing.black_points = 1.5
            pairing.save()
            
            # Set board results consistently
            board_pairings = TeamPlayerPairing.objects.filter(team_pairing=pairing)
            for j, bp in enumerate(board_pairings):
                if i % 2 == 0:  # White team winning
                    bp.result = "1-0" if j == 0 else "1/2-1/2"
                else:  # Black team winning
                    bp.result = "0-1" if j == 0 else "1/2-1/2"
                bp.save()


class KnockoutAdminSimulationTestCase(TestCase):
    """Test knockout admin actions using simulation."""

    def test_bracket_generation_admin_action(self):
        """Test admin bracket generation action."""
        tournament = (
            TournamentBuilder()
            .league("Admin Test", "AD", "team")
            .knockout_format(seeding_style="traditional", games_per_match=1)
            .season("AD", "Admin Season", rounds=2, boards=2)
            .team("AdminTeam1", "AP1A", "AP1B")
            .team("AdminTeam2", "AP2A", "AP2B")
            .team("AdminTeam3", "AP3A", "AP3B")
            .team("AdminTeam4", "AP4A", "AP4B")
            .build()
        )

        season = tournament.current_season
        
        # Create bracket without generating it (check if one already exists)
        bracket, created = KnockoutBracket.objects.get_or_create(
            season=season,
            defaults={
                "bracket_size": 4,
                "seeding_style": "traditional",
                "games_per_match": 1
            }
        )
        
        # Test admin action
        from django.contrib.admin.sites import AdminSite
        from django.contrib.auth.models import User
        from django.http import HttpRequest
        from django.contrib.messages.storage.fallback import FallbackStorage
        from heltour.tournament.admin import KnockoutBracketAdmin
        
        # Create admin user and request
        user = User.objects.create_superuser('admin', 'admin@test.com', 'pass')
        request = HttpRequest()
        request.user = user
        request.method = 'POST'
        request.session = {}
        request._messages = FallbackStorage(request)
        
        # Execute admin action
        admin = KnockoutBracketAdmin(KnockoutBracket, AdminSite())
        queryset = KnockoutBracket.objects.filter(id=bracket.id)
        admin.generate_knockout_bracket_action(request, queryset)
        
        # Verify bracket was generated
        self.assertTrue(Round.objects.filter(season=season, number=1).exists())
        self.assertTrue(KnockoutSeeding.objects.filter(bracket=bracket).exists())

    def test_manual_tiebreak_admin_actions(self):
        """Test admin actions for setting manual tiebreaks."""
        tournament = (
            TournamentBuilder()
            .league("Tiebreak Admin", "TA", "team")
            .knockout_format(seeding_style="traditional", games_per_match=1)
            .season("TA", "Tiebreak Test", rounds=1, boards=2)
            .team("TieTeamA", "TTAP1", "TTAP2")
            .team("TieTeamB", "TTBP1", "TTBP2")
            .build()
        )

        season = tournament.current_season
        
        # Generate bracket and get pairing
        from heltour.tournament.pairinggen import generate_knockout_bracket, create_knockout_pairings
        generate_knockout_bracket(season)
        
        round1 = Round.objects.get(season=season, number=1)
        
        # Create pairings using dashboard functionality
        create_knockout_pairings(round1)
        
        pairing = TeamPairing.objects.filter(round=round1).first()
        
        # Test admin actions
        from django.contrib.admin.sites import AdminSite
        from django.contrib.auth.models import User
        from django.http import HttpRequest
        from django.contrib.messages.storage.fallback import FallbackStorage
        from heltour.tournament.admin import TeamPairingAdmin
        
        user = User.objects.create_superuser('admin', 'admin@test.com', 'pass')
        request = HttpRequest()
        request.user = user
        request.method = 'POST'
        request.session = {}
        request._messages = FallbackStorage(request)
        
        admin = TeamPairingAdmin(TeamPairing, AdminSite())
        queryset = TeamPairing.objects.filter(id=pairing.id)
        
        # Test white wins tiebreak
        admin.set_white_wins_tiebreak(request, queryset)
        pairing.refresh_from_db()
        self.assertEqual(pairing.manual_tiebreak_value, 1.0)
        
        # Test black wins tiebreak
        admin.set_black_wins_tiebreak(request, queryset)
        pairing.refresh_from_db()
        self.assertEqual(pairing.manual_tiebreak_value, -1.0)
        
        # Test clear tiebreak
        admin.clear_manual_tiebreak(request, queryset)
        pairing.refresh_from_db()
        self.assertIsNone(pairing.manual_tiebreak_value)


class KnockoutErrorHandlingTestCase(TransactionTestCase):
    """Test error handling in knockout tournaments."""

    def test_missing_manual_tiebreak_error(self):
        """Test that tied matches without manual tiebreak raise errors."""
        tournament = (
            TournamentBuilder()
            .league("Error Test", "ET", "team")
            .knockout_format(seeding_style="traditional", games_per_match=1)
            .season("ET", "Tiebreak Error", rounds=2, boards=2)
            .team("ErrorA", "EPA1", "EPA2")
            .team("ErrorB", "EPB1", "EPB2")
            .team("ErrorC", "EPC1", "EPC2")
            .team("ErrorD", "EPD1", "EPD2")
            .build()
        )

        season = tournament.current_season
        
        # Generate bracket
        from heltour.tournament.pairinggen import generate_knockout_bracket, create_knockout_pairings
        generate_knockout_bracket(season)
        
        round1 = Round.objects.get(season=season, number=1)
        
        # Create pairings using dashboard functionality
        create_knockout_pairings(round1)
        
        pairings = TeamPairing.objects.filter(round=round1)
        
        # Create tied match without manual tiebreak
        tied_pairing = pairings.first()
        tied_pairing.white_points = 1.0
        tied_pairing.black_points = 1.0  # Tied!
        tied_pairing.manual_tiebreak_value = None  # No tiebreak!
        tied_pairing.save()
        
        # Set result for other match
        other_pairing = pairings.exclude(id=tied_pairing.id).first()
        other_pairing.white_points = 2.0
        other_pairing.black_points = 0.0
        other_pairing.save()
        
        # Complete round
        round1.is_completed = True
        round1.save()
        
        # Advance tournament should fail
        from heltour.tournament.pairinggen import advance_knockout_tournament, PairingGenerationException
        
        with self.assertRaises(PairingGenerationException) as context:
            advance_knockout_tournament(round1)
        
        self.assertIn("requires manual tiebreak", str(context.exception))

    def test_invalid_bracket_size_error(self):
        """Test that invalid bracket sizes are handled."""
        tournament = (
            TournamentBuilder()
            .league("Invalid Size", "IS", "team")
            .knockout_format(seeding_style="traditional", games_per_match=1)
            .season("IS", "Bad Bracket", rounds=2, boards=2)
            # Only 3 teams - not a power of 2
            .team("BadTeam1", "BP1A", "BP1B")
            .team("BadTeam2", "BP2A", "BP2B")
            .team("BadTeam3", "BP3A", "BP3B")
            .build()
        )

        season = tournament.current_season
        
        # Try to generate bracket with invalid size
        from heltour.tournament.pairinggen import generate_knockout_bracket, PairingGenerationException
        
        with self.assertRaises(PairingGenerationException) as context:
            generate_knockout_bracket(season)
        
        self.assertIn("power of 2", str(context.exception))