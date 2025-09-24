"""
InviteCode seeder for creating test invite codes.
"""

import random
from datetime import timedelta
from typing import List, Optional
from django.utils import timezone
from heltour.tournament.models import InviteCode, Season, Team, TeamMember, Player
from .base import BaseSeeder


class InviteCodeSeeder(BaseSeeder):
    """Seeder for creating InviteCode objects."""

    def seed(
        self,
        captain_codes: int = 10,
        seasons: Optional[List[Season]] = None,
        **kwargs
    ) -> List[InviteCode]:
        """Create test invite codes for captain team formation.
        
        Args:
            captain_codes: Number of captain codes to create per season
            seasons: Specific seasons to create codes for, defaults to all
            
        Returns:
            List of created InviteCode objects
        """
        codes = []
        
        # Get all seasons if none specified
        if seasons is None:
            seasons = Season.objects.all()
            
        for season in seasons:
            # For invite-only leagues, create more codes
            if season.league.registration_mode == 'invite_only':
                codes_to_create = captain_codes
            else:
                # Still create some codes for testing even in non-invite-only leagues
                if self.weighted_bool(0.3):  # 30% chance
                    codes_to_create = max(2, captain_codes // 3)
                else:
                    continue
                    
            # Create admin-generated captain codes
            codes.extend(self._create_captain_codes(season, codes_to_create))
            
        return codes
    
    def _create_captain_codes(self, season: Season, count: int) -> List[InviteCode]:
        """Create captain invite codes for forming new teams."""
        codes = []
        
        for i in range(count):
            # Generate a readable code using the built-in method
            code_value = InviteCode.generate_code()
            
            # Some codes should be used
            used = self.weighted_bool(0.3)  # 30% usage rate
            
            code_data = {
                'season': season,
                'league': season.league,
                'code': code_value,
                'code_type': 'captain',
                'created_by_captain': None,  # Admin-created
                'team': None,  # Captain codes don't belong to a team
            }
            
            if used:
                # Find a player to use this code
                players = Player.objects.filter(is_active=True)
                if players.exists():
                    used_by = self.random_choice(players)
                    code_data['used_by'] = used_by
                    code_data['used_at'] = timezone.now() - timedelta(
                        days=random.randint(1, 30)
                    )
                    
            code = InviteCode.objects.create(**code_data)
            codes.append(self._track_object(code))
            
        return codes
    
    def seed_team_member_codes(
        self,
        teams: Optional[List[Team]] = None,
        codes_per_team: int = 3,
        **kwargs
    ) -> List[InviteCode]:
        """Create team member codes for existing teams with captains.
        
        This would typically be called after teams are created, to simulate
        captains generating codes for their team members.
        """
        codes = []
        
        # Get teams with captains if none specified
        if teams is None:
            # Find teams that have captains
            team_ids = TeamMember.objects.filter(
                is_captain=True
            ).values_list('team_id', flat=True).distinct()
            teams = Team.objects.filter(id__in=team_ids)
            
        for team in teams:
            # Get the captain
            captain_member = TeamMember.objects.filter(
                team=team,
                is_captain=True
            ).first()
            
            if not captain_member:
                continue
                
            # Skip teams that already have invite codes
            if InviteCode.objects.filter(team=team).exists():
                continue
                
            # Check captain's code limit
            season = team.season
            captain = captain_member.player
            
            # Count existing codes created by this captain
            existing_codes = InviteCode.objects.filter(
                season=season,
                created_by_captain=captain
            ).count()
            
            # Respect the limit if set
            limit = getattr(season, 'codes_per_captain_limit', 10) or 10
            available = max(0, limit - existing_codes)
            codes_to_create = min(codes_per_team, available)
            
            # Create team member codes
            for i in range(codes_to_create):
                code_value = InviteCode.generate_code()
                
                # Some codes should be used
                used = self.weighted_bool(0.2)  # 20% usage rate
                
                code_data = {
                    'season': season,
                    'league': season.league,
                    'code': code_value,
                    'code_type': 'team_member',
                    'created_by_captain': captain,
                    'team': team,
                }
                
                if used:
                    # Find a player not already on a team
                    existing_members = TeamMember.objects.filter(
                        team__season=season
                    ).values_list('player_id', flat=True)
                    
                    available_players = Player.objects.filter(
                        is_active=True
                    ).exclude(id__in=existing_members)
                    
                    if available_players.exists():
                        used_by = self.random_choice(available_players)
                        code_data['used_by'] = used_by
                        code_data['used_at'] = timezone.now() - timedelta(
                            days=random.randint(1, 14)
                        )
                        
                # Ensure unique code
                attempts = 0
                while attempts < 10:
                    try:
                        code = InviteCode.objects.create(**code_data)
                        codes.append(self._track_object(code))
                        break
                    except Exception as e:
                        if 'duplicate key' in str(e):
                            # Generate a new code and try again
                            code_data['code'] = InviteCode.generate_code()
                            attempts += 1
                        else:
                            raise
                            
                if attempts >= 10:
                    # Still failed after 10 attempts, skip this code
                    continue
                
        return codes
    
