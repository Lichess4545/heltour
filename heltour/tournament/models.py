from __future__ import unicode_literals

from django.db import models
from django.utils.crypto import get_random_string
from ckeditor.fields import RichTextField
from django.core.validators import RegexValidator

tag_validator = RegexValidator(r'^[0-9a-zA-Z-_]*$', 'Only alphanumeric characters, hyphens, and underscores are allowed.')

#-------------------------------------------------------------------------------
class _BaseModel(models.Model):
    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True

#-------------------------------------------------------------------------------
class League(_BaseModel):
    name = models.CharField(max_length=255, unique=True)
    tag = models.CharField(max_length=31, unique=True, validators=[tag_validator], help_text='The league will be accessible at /{league_tag}/')
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    def __unicode__(self):
        return self.name

#-------------------------------------------------------------------------------
class Season(_BaseModel):
    league = models.ForeignKey(League)
    name = models.CharField(max_length=255)
    start_date = models.DateField(blank=True, null=True)
    rounds = models.PositiveIntegerField()
    boards = models.PositiveIntegerField()

    is_active = models.BooleanField(default=True)
    is_completed = models.BooleanField(default=False)
    registration_open = models.BooleanField(default=False)

    class Meta:
        unique_together = ('league', 'name')
        permissions = (
            ('edit_rosters', 'Can edit rosters'),
        )

    def __unicode__(self):
        return self.name

#-------------------------------------------------------------------------------
class Round(_BaseModel):
    season = models.ForeignKey(Season)
    number = models.PositiveIntegerField()
    start_date = models.DateTimeField(blank=True, null=True)
    end_date = models.DateTimeField(blank=True, null=True)
    
    publish_pairings = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)

    class Meta:
        permissions = (
            ('generate_pairings', 'Can generate and review pairings'),
        )

    def __unicode__(self):
        return "%s - Round %d" % (self.season, self.number)

ROUND_CHANGE_OPTIONS = (
    ('register', 'Register'),
    ('withdraw', 'Withdraw'),
    ('bye', 'Bye'),
)

#-------------------------------------------------------------------------------
class RoundChange(_BaseModel):
    round = models.ForeignKey(Round)
    action = models.CharField(max_length=255, choices=ROUND_CHANGE_OPTIONS)

#-------------------------------------------------------------------------------
class Player(_BaseModel):
    # TODO: we should find out the real restrictions on a lichess username and 
    #       duplicate them here.
    # Note: a case-insensitive unique index for lichess_username is added via migration to the DB
    lichess_username = models.CharField(max_length=255)
    rating = models.PositiveIntegerField(blank=True, null=True)
    games_played = models.PositiveIntegerField(blank=True, null=True)
    email = models.CharField(max_length=255, blank=True)
    is_moderator = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    moderator_notes = models.TextField(blank=True, max_length=4095)
   
    def __unicode__(self):
        if self.rating is None:
            return self.lichess_username
        else:
            return "%s (%d)" % (self.lichess_username, self.rating)
    
#-------------------------------------------------------------------------------
class Team(_BaseModel):
    season = models.ForeignKey(Season)
    number = models.PositiveIntegerField()
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = (('season', 'number'), ('season', 'name'))
    
    def boards(self):
        for i in range(self.season.boards):
            board_number = i + 1
            yield board_number, self.teammember_set.filter(board_number=board_number).first()
    
    def average_rating(self):
        n = 0
        total = 0.0
        for board_number, board in self.boards():
            if board is not None and board.player.rating is not None:
                n += 1
                total += board.player.rating
        return total / n if n > 0 else None
    
    def __unicode__(self):
        return "%s - %s" % (self.season, self.name)

BOARD_NUMBER_OPTIONS = (
    (1, '1'),
    (2, '2'),
    (3, '3'),
    (4, '4'),
    (5, '5'),
    (6, '6'),
)

#-------------------------------------------------------------------------------
class TeamMember(_BaseModel):
    team = models.ForeignKey(Team)
    player = models.ForeignKey(Player)
    board_number = models.PositiveIntegerField(choices=BOARD_NUMBER_OPTIONS)
    is_captain = models.BooleanField(default=False)
    is_vice_captain = models.BooleanField(default=False)

    class Meta:
        unique_together = ('team', 'board_number')

    def __unicode__(self):
        return "%s" % self.player

#-------------------------------------------------------------------------------
class TeamScore(_BaseModel):
    team = models.OneToOneField(Team)
    match_count = models.PositiveIntegerField(default=0)
    match_points = models.PositiveIntegerField(default=0)
    game_points = models.PositiveIntegerField(default=0)

    def match_points_display(self):
        return str(self.match_points)
    
    def game_points_display(self):
        return "%g" % (self.game_points / 2.0)
    
    def round_scores(self):
        for i in range(self.team.season.rounds):
            round_number = i + 1
            round_ = Round.objects.filter(season=self.team.season, number=round_number).first()
            if round_ is None or not round_.is_completed:
                yield None
                continue
            points = None
            white_pairing = TeamPairing.objects.filter(round=round_, white_team=self.team).first()
            black_pairing = TeamPairing.objects.filter(round=round_, black_team=self.team).first()
            if white_pairing is not None:
                points = white_pairing.white_points / 2.0
            if black_pairing is not None:
                points = black_pairing.black_points / 2.0
            yield points
    
    def cross_scores(self):
        other_teams = Team.objects.filter(season=self.team.season).order_by('number')
        for other_team in other_teams:
            white_pairing = TeamPairing.objects.filter(white_team=self.team, black_team=other_team).first()
            black_pairing = TeamPairing.objects.filter(white_team=other_team, black_team=self.team).first()
            points = None
            id = None
            if white_pairing is not None and white_pairing.round.is_completed:
                points = white_pairing.white_points / 2.0
                id = white_pairing.pk
            if black_pairing is not None and black_pairing.round.is_completed:
                points = black_pairing.black_points / 2.0
                id = black_pairing.pk
            yield other_team.number, points, id
    
    def __unicode__(self):
        return "%s" % (self.team)
    
    def __cmp__(self, other):
        result = self.match_points - other.match_points
        if result != 0:
            return result
        result = self.game_points - other.game_points
        return result

#-------------------------------------------------------------------------------
class Alternate(_BaseModel):
    season = models.ForeignKey(Season)
    player = models.ForeignKey(Player)
    board_number = models.PositiveIntegerField(choices=BOARD_NUMBER_OPTIONS)

    class Meta:
        unique_together = ('season', 'player')
    
    def __unicode__(self):
        return "%s" % self.player

#-------------------------------------------------------------------------------
class AlternateAssignment(_BaseModel):
    round = models.ForeignKey(Round)
    team = models.ForeignKey(Team)
    board_number = models.PositiveIntegerField(choices=BOARD_NUMBER_OPTIONS)
    player = models.ForeignKey(Player)
    
    class Meta:
        unique_together = ('round', 'team', 'board_number')
    
    def __unicode__(self):
        return "%s - %s - Board %d" % (self.round, self.team.name, self.board_number)

#-------------------------------------------------------------------------------
class AlternateBucket(_BaseModel):
    season = models.ForeignKey(Season)
    board_number = models.PositiveIntegerField(choices=BOARD_NUMBER_OPTIONS)
    min_rating = models.PositiveIntegerField(null=True, blank=True)
    max_rating = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ('season', 'board_number')
    
    def contains(self, rating):
        return (self.min_rating is None or rating >= self.min_rating) and (self.max_rating is None or rating <= self.max_rating)

    def __unicode__(self):
        return "Board %d [%d, %d]" % (self.board_number, self.min_rating, self.max_rating)

#-------------------------------------------------------------------------------
class TeamPairing(_BaseModel):
    white_team = models.ForeignKey(Team, related_name="pairings_as_white")
    black_team = models.ForeignKey(Team, related_name="pairings_as_black")
    round = models.ForeignKey(Round)
    pairing_order = models.PositiveIntegerField()

    white_points = models.PositiveIntegerField(default=0)
    black_points = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('white_team', 'black_team', 'round')
    
    def refresh_points(self):
        self.white_points = 0
        self.black_points = 0
        for team_player_pairing in self.teamplayerpairing_set.all():
            player_pairing = team_player_pairing.player_pairing
            result = player_pairing.result
            if result == '1-0':
                if team_player_pairing.board_number % 2 == 1:
                    self.white_points += 2
                else:
                    self.black_points += 2
            elif result == '0-1':
                if team_player_pairing.board_number % 2 == 1:
                    self.black_points += 2
                else:
                    self.white_points += 2
            elif result == '1/2-1/2':
                self.white_points += 1
                self.black_points += 1
    
    def white_points_display(self):
        return "%g" % (self.white_points / 2.0)
    
    def black_points_display(self):
        return "%g" % (self.black_points / 2.0)
    
    def season_name(self):
        return "%s" % self.round.season.name
    
    def round_number(self):
        return "%d" % self.round.number
    
    def white_team_name(self):
        return "%s" % self.white_team.name
    
    def black_team_name(self):
        return "%s" % self.black_team.name

    def __unicode__(self):
        return "%s - %s - %s" % (self.round, self.white_team.name, self.black_team.name)
    
#-------------------------------------------------------------------------------
class PlayerPairing(_BaseModel):
    white = models.ForeignKey(Player, related_name="pairings_as_white")
    black = models.ForeignKey(Player, related_name="pairings_as_black")

    result = models.CharField(max_length=16, blank=True)
    game_link = models.URLField(max_length=1024, blank=True)
    scheduled_time = models.DateTimeField(blank=True, null=True)
    
    def __init__(self, *args, **kwargs):
        super(PlayerPairing, self).__init__(*args, **kwargs)
        self.initial_result = self.result
        
    def white_score(self):
        if self.result == '1-0':
            return 1
        elif self.result == '0-1':
            return 0
        elif self.result == '1/2-1/2':
            return 0.5
        return None
        
    def black_score(self):
        if self.result == '0-1':
            return 1
        elif self.result == '1-0':
            return 0
        elif self.result == '1/2-1/2':
            return 0.5
        return None
        
    def save(self, *args, **kwargs):
        result_changed = self.pk is None or self.result != self.initial_result
        super(PlayerPairing, self).save(*args, **kwargs)
        if result_changed and hasattr(self, 'team_player_pairing'):
            self.team_player_pairing.team_pairing.refresh_points()
            self.team_player_pairing.team_pairing.save()

    def __unicode__(self):
        return "%s - %s" % (self.white, self.black)

#-------------------------------------------------------------------------------
class TeamPlayerPairing(_BaseModel):
    team_pairing = models.ForeignKey(TeamPairing)
    player_pairing = models.OneToOneField(PlayerPairing)
    board_number = models.PositiveIntegerField(choices=BOARD_NUMBER_OPTIONS)

    class Meta:
        unique_together = ('team_pairing', 'board_number')

    def __unicode__(self):
        return "%s" % (self.player_pairing)
    
    def white_team(self):
        return self.team_pairing.white_team if self.board_number % 2 == 1 else self.team_pairing.black_team
    
    def black_team(self):
        return self.team_pairing.black_team if self.board_number % 2 == 1 else self.team_pairing.white_team
    
    def white_team_player(self):
        return self.player_pairing.white if self.board_number % 2 == 1 else self.player_pairing.black
    
    def black_team_player(self):
        return self.player_pairing.black if self.board_number % 2 == 1 else self.player_pairing.white
    
    def white_team_score(self):
        return self.player_pairing.white_score() if self.board_number % 2 == 1 else self.player_pairing.black_score()
    
    def black_team_score(self):
        return self.player_pairing.black_score() if self.board_number % 2 == 1 else self.player_pairing.white_score()
    
    def white_team_name(self):
        return "%s" % self.white_team().name
    
    def black_team_name(self):
        return "%s" % self.black_team().name
    
    def season_name(self):
        return "%s" % self.team_pairing.round.season.name
    
    def round_number(self):
        return "%d" % self.team_pairing.round.number
        
    def save(self, *args, **kwargs):
        new_object = self.pk is None
        super(TeamPlayerPairing, self).save(*args, **kwargs)
        if new_object:
            self.team_pairing.refresh_points()
            self.team_pairing.save()

#-------------------------------------------------------------------------------
class LonePlayerPairing(_BaseModel):
    round = models.ForeignKey(Round)
    player_pairing = models.OneToOneField(PlayerPairing)
    pairing_order = models.PositiveIntegerField()

    def __unicode__(self):
        return "%s" % (self.player_pairing)

REGISTRATION_STATUS_OPTIONS = (
    ('pending', 'Pending'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
)

PREVIOUS_SEASON_ALTERNATE_OPTIONS = (
    ('alternate', 'Yes, I was an alternate at the end of the last season.'),
    ('alternate_to_full_time', 'Yes, but I was able to find a consistent team (did not simply fill in for a week or two).'),
    ('full_time', 'No, I was not an alternate for the last season. I played the season.'),
    ('new', 'No, I was not an alternate for the last season. I am a new member / I took last season off.'),
)

ALTERNATE_PREFERENCE_OPTIONS = (
    ('alternate', 'Alternate'),
    ('full_time', 'Full Time'),
)

#-------------------------------------------------------------------------------
class Registration(_BaseModel):
    season = models.ForeignKey(Season)
    status = models.CharField(blank=False, max_length=255, choices=REGISTRATION_STATUS_OPTIONS)
    status_changed_by = models.CharField(blank=True, max_length=255)
    status_changed_date = models.DateTimeField(blank=True, null=True)
    
    lichess_username = models.CharField(max_length=255)
    slack_username = models.CharField(max_length=255)
    email = models.EmailField(max_length=255)
    
    classical_rating = models.PositiveIntegerField()
    peak_classical_rating = models.PositiveIntegerField()
    has_played_20_games = models.BooleanField()
    already_in_slack_group = models.BooleanField()
    previous_season_alternate = models.CharField(max_length=255, choices=PREVIOUS_SEASON_ALTERNATE_OPTIONS)
    can_commit = models.BooleanField()
    friends = models.CharField(blank=True, max_length=1023)
    agreed_to_rules = models.BooleanField()
    alternate_preference = models.CharField(max_length=255, choices=ALTERNATE_PREFERENCE_OPTIONS)
    weeks_unavailable = models.CharField(blank=True, max_length=255)
    
    moderator_notes = models.TextField(blank=True, max_length=4095)
    
    def __unicode__(self):
        return "%s" % (self.lichess_username)
    
    def previous_registrations(self):
        return Registration.objects.filter(lichess_username__iexact=self.lichess_username, date_created__lt=self.date_created)
    
    def other_seasons(self):
        return SeasonPlayer.objects.filter(player__lichess_username__iexact=self.lichess_username).exclude(season=self.season)
    
    def player_notes(self):
        try:
            return Player.objects.filter(lichess_username__iexact=self.lichess_username)[0].moderator_notes
        except IndexError:
            return None

#-------------------------------------------------------------------------------
class SeasonPlayer(_BaseModel):
    season = models.ForeignKey(Season)
    player = models.ForeignKey(Player)
    registration = models.ForeignKey(Registration, on_delete=models.SET_NULL, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    games_missed = models.IntegerField(default=0)

    class Meta:
        unique_together = ('season', 'player')

    def __unicode__(self):
        return "%s" % self.player
    
def create_api_token():
    return get_random_string(length=32)

#-------------------------------------------------------------------------------
class ApiKey(_BaseModel):
    name = models.CharField(max_length=255, unique=True)
    secret_token = models.CharField(max_length=255, unique=True, default=create_api_token)
    
    def __unicode__(self):
        return self.name

#-------------------------------------------------------------------------------
class Document(_BaseModel):
    name = models.CharField(max_length=255)
    content = RichTextField()
    
    def __unicode__(self):
        return self.name

LEAGUE_DOCUMENT_TYPES = (
    ('faq', 'FAQ'),
    ('rules', 'Rules'),
    ('intro', 'Intro'),
)

#-------------------------------------------------------------------------------
class LeagueDocument(_BaseModel):
    league = models.ForeignKey(League)
    document = models.ForeignKey(Document)
    tag = models.CharField(max_length=255, validators=[tag_validator], help_text='The document will be accessible at /{league_tag}/document/{document_tag}/')
    type = models.CharField(blank=True, max_length=255, choices=LEAGUE_DOCUMENT_TYPES)

    class Meta:
        unique_together = ('league', 'tag')
    
    def __unicode__(self):
        return self.document.name
