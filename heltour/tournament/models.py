from __future__ import unicode_literals

from django.db import models

#-------------------------------------------------------------------------------
class _BaseModel(models.Model):
    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True

#-------------------------------------------------------------------------------
class League(_BaseModel):
    name = models.CharField(max_length=255, unique=True)

    def __unicode__(self):
        return self.name

#-------------------------------------------------------------------------------
class Season(_BaseModel):
    league = models.ForeignKey(League)
    name = models.CharField(max_length=255)
    start_date = models.DateField(blank=True, null=True)
    rounds = models.PositiveIntegerField()
    boards = models.PositiveIntegerField()
    registration_open = models.BooleanField(default=False)

    is_completed = models.BooleanField(default=False)

    class Meta:
        unique_together = ('league', 'name')

    def __unicode__(self):
        return self.name

#-------------------------------------------------------------------------------
class Round(_BaseModel):
    season = models.ForeignKey(Season)
    start_date = models.DateField()
    number = models.PositiveIntegerField()
    end_date = models.DateField()

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
    lichess_username = models.CharField(max_length=255)
    rating = models.PositiveIntegerField(blank=True, null=True)
    games_played = models.PositiveIntegerField(blank=True, null=True)
    is_moderator = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def __unicode__(self):
        return "%s (%d)" % (self.lichess_username, self.rating)

#-------------------------------------------------------------------------------
class Team(_BaseModel):
    season = models.ForeignKey(Season)
    number = models.PositiveIntegerField()
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = (('season', 'number'), ('season', 'name'))

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
    board_number = models.PositiveIntegerField(blank=True, null=True, choices=BOARD_NUMBER_OPTIONS)
    is_captain = models.BooleanField(default=False)
    is_vice_captain = models.BooleanField(default=False)

    games_missed = models.IntegerField(default=0)

    class Meta:
        unique_together = ('team', 'player')

    def __unicode__(self):
        return "%s" % self.player

#-------------------------------------------------------------------------------
class TeamScore(_BaseModel):
    team = models.ForeignKey(Team)
    match_count = models.PositiveIntegerField()
    match_points = models.PositiveIntegerField()
    game_points = models.PositiveIntegerField()

    class Meta:
        unique_together = (('team',),)

    def __unicode__(self):
        return "%s" % (self.team)
    
    def __cmp__(self, other):
        result = self.match_points - other.match_points
        if result != 0:
            return result
        result = self.game_points - other.game_points
        return result
    
#-------------------------------------------------------------------------------
class TeamPairing(_BaseModel):
    white_team = models.ForeignKey(Team, related_name="pairings_as_white")
    black_team = models.ForeignKey(Team, related_name="pairings_as_black")
    round = models.ForeignKey(Round)

    white_points = models.PositiveIntegerField(default=0)
    black_points = models.PositiveIntegerField(default=0)
    
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
class Pairing(_BaseModel):
    team_pairing = models.ForeignKey(TeamPairing)
    white = models.ForeignKey(Player, related_name="pairings_as_white")
    black = models.ForeignKey(Player, related_name="pairings_as_black")
    board_number = models.PositiveIntegerField(choices=BOARD_NUMBER_OPTIONS)

    result = models.CharField(max_length=16, blank=True, null=True)
    game_link = models.URLField(max_length=1024, blank=True, null=True)
    date_played = models.DateField(blank=True, null=True)
    
    def season_name(self):
        return "%s" % self.team_pairing.round.season.name
    
    def round_number(self):
        return "%d" % self.team_pairing.round.number
    
    def white_team_name(self):
        team = self.team_pairing.white_team if self.board_number % 2 == 1 else self.team_pairing.black_team
        return "%s" % team.name
    
    def black_team_name(self):
        team = self.team_pairing.white_team if self.board_number % 2 == 0 else self.team_pairing.black_team
        return "%s" % team.name

    def __unicode__(self):
        return "%s - %s" % (self.white, self.black)

REGISTRATION_STATUS_OPTIONS = (
    ('pending', 'Pending'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
)

PREVIOUS_SEASON_ALTERNATE_OPTIONS = (
    ('alternate', 'Yes, I was an alternate for at the end of the last season.'),
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
    
    lichess_username = models.CharField(max_length=255)
    slack_username = models.CharField(max_length=255)
    email = models.CharField(max_length=255)
    
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
    
    def __unicode__(self):
        return "%s" % (self.lichess_username)
