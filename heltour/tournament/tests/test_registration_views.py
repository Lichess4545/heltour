"""Integration tests for registration views with invite codes and team assignment."""

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

from heltour.tournament.models import (
    League, Season, Player, Registration, InviteCode, Team, TeamMember, SeasonPlayer
)
from heltour.tournament.templatetags.tournament_extras import leagueurl
from heltour.tournament.tests.testutils import get_valid_registration_form_data


class RegistrationViewIntegrationTestCase(TestCase):
    """Test registration views with team assignment functionality."""
    
    def setUp(self):
        """Set up test data and client."""
        self.client = Client()
        
        # Create invite-only league
        self.league = League.objects.create(
            name='View Test League',
            tag='view-test',
            description='Test registration views',
            theme='blue',
            time_control='45+45',
            rating_type='classical',
            competitor_type='team',
            registration_mode='invite_only',
            email_required=False,
            show_provisional_warning=False,
            ask_availability=False
        )
        
        self.season = Season.objects.create(
            league=self.league,
            name='View Test Season',
            tag='view-test-season',
            rounds=8,
            boards=4,
            start_date=timezone.now() + timedelta(days=7),
            registration_open=True
        )
        
        # Create user and player
        self.user = User.objects.create_user(
            username='testviewplayer',
            password='testpass123'
        )
        self.player = Player.objects.create(
            lichess_username='testviewplayer',
            rating=1700,
            email='viewtest@example.com'
        )
    
    def test_registration_with_captain_code_full_flow(self):
        """Test full registration flow with captain code including success page."""
        # Create captain invite code
        captain_code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code='VIEW-CAPTAIN-001',
            code_type='captain'
        )
        
        # Login
        self.client.login(username='testviewplayer', password='testpass123')
        
        # Get registration URL
        reg_url = leagueurl('register', self.league.tag, self.season.tag)
        
        # Submit registration form
        form_data = get_valid_registration_form_data()
        form_data['invite_code'] = 'VIEW-CAPTAIN-001'
        form_data['first_name'] = 'View'
        form_data['last_name'] = 'Captain'
        form_data['corporate_email'] = 'viewcaptain@company.com'
        form_data['date_of_birth'] = '1985-03-15'
        
        response = self.client.post(reg_url, form_data)
        
        # Should redirect to success page
        success_url = leagueurl('registration_success', self.league.tag, self.season.tag)
        self.assertRedirects(response, success_url)
        
        # Follow redirect to success page
        response = self.client.get(success_url)
        self.assertEqual(response.status_code, 200)
        
        # In new flow, captain doesn't get team assignment - they need to create it
        self.assertIn('is_captain', response.context)
        self.assertIn('needs_team_setup', response.context)
        self.assertTrue(response.context['is_captain'])
        self.assertTrue(response.context['needs_team_setup'])
        
        # Check HTML content
        self.assertContains(response, 'Your registration has been approved!')
        self.assertContains(response, 'captain')  # Should mention they're a captain
        self.assertContains(response, 'Create')  # Should have create team option
        
        # Verify database state
        registration = Registration.objects.get(player=self.player, season=self.season)
        self.assertEqual(registration.status, 'approved')
        
        # No team member should exist yet
        self.assertFalse(TeamMember.objects.filter(player=self.player).exists())
        
        sp = SeasonPlayer.objects.get(player=self.player, season=self.season)
        self.assertTrue(sp.is_active)
    
    def test_registration_with_team_member_code_full_flow(self):
        """Test full registration flow with team member code."""
        # Create existing team
        existing_team = Team.objects.create(
            season=self.season,
            number=1,
            name='Existing View Team',
            is_active=True
        )
        
        # Add captain
        captain = Player.objects.create(
            lichess_username='viewcaptain',
            rating=2000
        )
        TeamMember.objects.create(
            team=existing_team,
            player=captain,
            board_number=1,
            is_captain=True
        )
        
        # Create team member code
        member_code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code='VIEW-MEMBER-001',
            code_type='team_member',
            team=existing_team,
            created_by_captain=captain
        )
        
        # Login and register
        self.client.login(username='testviewplayer', password='testpass123')
        
        reg_url = leagueurl('register', self.league.tag, self.season.tag)
        form_data = get_valid_registration_form_data()
        form_data['invite_code'] = 'VIEW-MEMBER-001'
        form_data['first_name'] = 'View'
        form_data['last_name'] = 'Member'
        form_data['gender'] = 'female'
        form_data['date_of_birth'] = '1992-08-20'
        form_data['nationality'] = 'CA'
        form_data['corporate_email'] = 'viewmember@company.com'
        
        response = self.client.post(reg_url, form_data)
        
        # Should redirect to success page
        success_url = leagueurl('registration_success', self.league.tag, self.season.tag)
        self.assertRedirects(response, success_url)
        
        # Check success page
        response = self.client.get(success_url)
        self.assertEqual(response.status_code, 200)
        
        # Verify team assignment
        self.assertIn('assigned_team', response.context)
        assigned_team = response.context['assigned_team']
        self.assertEqual(assigned_team, existing_team)
        
        # Check HTML
        self.assertContains(response, 'Your registration has been approved!')
        self.assertContains(response, existing_team.name)
        self.assertContains(response, 'View Your Team')
        
        # Verify member was added to team
        team_member = TeamMember.objects.get(player=self.player)
        self.assertEqual(team_member.team, existing_team)
        self.assertEqual(team_member.board_number, 2)
        self.assertFalse(team_member.is_captain)
    
    def test_registration_without_invite_code_shows_pending(self):
        """Test that regular registration shows pending status."""
        # Create regular league
        regular_league = League.objects.create(
            name='Regular View League',
            tag='regular-view',
            description='Regular registration',
            theme='green',
            time_control='45+45',
            rating_type='classical',
            competitor_type='team',
            registration_mode='open',
            email_required=True,
            show_provisional_warning=True,
            ask_availability=True
        )
        
        regular_season = Season.objects.create(
            league=regular_league,
            name='Regular View Season',
            tag='regular-view-season',
            rounds=8,
            boards=4,
            start_date=timezone.now() + timedelta(days=7),
            registration_open=True
        )
        
        # Login and register
        self.client.login(username='testviewplayer', password='testpass123')
        
        reg_url = leagueurl('register', regular_league.tag, regular_season.tag)
        form_data = get_valid_registration_form_data()
        form_data['email'] = 'test@example.com'
        form_data['first_name'] = 'Regular'
        form_data['last_name'] = 'Player'
        form_data['gender'] = 'non-binary'
        form_data['date_of_birth'] = '1994-12-25'
        form_data['nationality'] = 'DE'
        form_data['corporate_email'] = 'regular@company.com'
        form_data['friends'] = 'friend1'
        form_data['avoid'] = 'enemy1'
        form_data['weeks_unavailable'] = []  # Available for all weeks
        response = self.client.post(reg_url, form_data)
        
        # Should redirect to success page
        success_url = leagueurl('registration_success', regular_league.tag, regular_season.tag)
        self.assertRedirects(response, success_url)
        
        # Check success page
        response = self.client.get(success_url)
        self.assertEqual(response.status_code, 200)
        
        # Should NOT show team assignment
        self.assertNotIn('assigned_team', response.context)
        
        # Should show pending message
        self.assertContains(response, 'A confirmation email will be sent')
        self.assertNotContains(response, 'Your registration has been approved!')
        
        # Verify registration is pending
        registration = Registration.objects.get(player=self.player, season=regular_season)
        self.assertEqual(registration.status, 'pending')
        
        # No team should be created
        team_member = TeamMember.objects.filter(player=self.player).first()
        self.assertIsNone(team_member)
    
    def test_team_details_link_works(self):
        """Test that the team details link in success page works correctly."""
        # Login first
        self.client.login(username='testviewplayer', password='testpass123')
        
        # Create captain invite code
        captain_code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code='LINK-CAPTAIN-001',
            code_type='captain'
        )
        
        # Register using the form to properly trigger workflows
        reg_url = leagueurl('register', self.league.tag, self.season.tag)
        form_data = get_valid_registration_form_data()
        form_data['invite_code'] = 'LINK-CAPTAIN-001'
        form_data['first_name'] = 'Link'
        form_data['last_name'] = 'Captain'
        form_data['gender'] = 'male'
        form_data['date_of_birth'] = '1986-06-10'
        form_data['nationality'] = 'FR'
        form_data['corporate_email'] = 'linkcaptain@company.com'
        response = self.client.post(reg_url, form_data)
        
        # Should redirect to success page
        success_url = leagueurl('registration_success', self.league.tag, self.season.tag)
        self.assertRedirects(response, success_url)
        
        # Get the registration
        registration = Registration.objects.get(player=self.player, season=self.season)
        self.assertEqual(registration.status, 'approved')
        
        # Create team using TeamCreateForm
        from heltour.tournament.forms import TeamCreateForm
        team_form = TeamCreateForm(
            data={
                'team_name': 'Link Test Team',
                'company_name': 'Test Company',
                'company_address': '123 Test St',
                'team_contact_email': 'team@example.com',
                'team_contact_number_0': 'US',
                'team_contact_number_1': '2345678900',
            },
            season=self.season,
            player=self.player
        )
        self.assertTrue(team_form.is_valid())
        team = team_form.save()
        
        # Now we need to check the team member's view of the success page
        # Create a team member and check their success page shows the team link
        member = Player.objects.create(
            lichess_username='testmember',
            rating=1600
        )
        
        # Add member to team
        TeamMember.objects.create(
            team=team,
            player=member,
            board_number=2,
            is_captain=False
        )
        
        # Create member registration
        member_reg = Registration.objects.create(
            season=self.season,
            player=member,
            status='approved',
            can_commit=True,
            agreed_to_rules=True,
            agreed_to_tos=True
        )
        
        # Set session for member
        session = self.client.session
        session['reg_id'] = member_reg.id
        session.save()
        
        # Get success page as team member
        response = self.client.get(success_url)
        
        # Check team details link
        team_url = leagueurl('team_profile', self.league.tag, self.season.tag, team.number)
        self.assertContains(response, team_url)
        self.assertContains(response, 'View Your Team')
        
        # Test that the team details page loads
        response = self.client.get(team_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, team.name)


class RegistrationErrorHandlingTestCase(TestCase):
    """Test error handling in registration with invite codes."""
    
    def setUp(self):
        """Set up test data."""
        self.client = Client()
        
        self.league = League.objects.create(
            name='Error Test League',
            tag='error-test',
            description='Test error handling',
            theme='red',
            time_control='30+30',
            rating_type='rapid',
            competitor_type='team',
            registration_mode='invite_only',
            email_required=False,
            show_provisional_warning=False,
            ask_availability=False
        )
        
        self.season = Season.objects.create(
            league=self.league,
            name='Error Test Season',
            tag='error-test-season',
            rounds=6,
            boards=4,
            start_date=timezone.now() + timedelta(days=7),
            registration_open=True
        )
        
        self.user = User.objects.create_user(
            username='errortest',
            password='testpass'
        )
        self.player = Player.objects.create(
            lichess_username='errortest',
            rating=1600
        )
    
    def test_registration_with_invalid_code_shows_error(self):
        """Test that invalid invite code shows proper error."""
        self.client.login(username='errortest', password='testpass')
        
        reg_url = leagueurl('register', self.league.tag, self.season.tag)
        form_data = get_valid_registration_form_data()
        form_data['invite_code'] = 'INVALID-CODE-999'
        response = self.client.post(reg_url, form_data)
        
        # Should not redirect (form has errors)
        self.assertEqual(response.status_code, 200)
        
        # Check for error message
        self.assertFormError(response, 'form', 'invite_code', 'Invalid invite code')
    
    def test_registration_with_used_code_shows_error(self):
        """Test that already used invite code shows proper error."""
        # Create and use an invite code
        used_player = Player.objects.create(
            lichess_username='usedplayer',
            rating=1700
        )
        
        code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code='USED-CODE-001',
            code_type='captain'
        )
        code.mark_used(used_player)
        
        # Try to use it again
        self.client.login(username='errortest', password='testpass')
        
        reg_url = leagueurl('register', self.league.tag, self.season.tag)
        form_data = get_valid_registration_form_data()
        form_data['invite_code'] = 'USED-CODE-001'
        response = self.client.post(reg_url, form_data)
        
        # Should not redirect
        self.assertEqual(response.status_code, 200)
        
        # Check for error
        self.assertFormError(response, 'form', 'invite_code', 
                           'This invite code has already been used')