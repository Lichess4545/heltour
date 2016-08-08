from __future__ import unicode_literals

from django.db import models
from django.utils.crypto import get_random_string
from ckeditor.fields import RichTextField
from django.core.validators import RegexValidator
from datetime import timedelta
from django.utils import timezone

# Helper function to find an item in a list by its properties
def find(lst, **prop_values):
    it = iter(lst)
    for k, v in prop_values.items():
        it = (obj for obj in it if getattr(obj, k) == v) 
    return next(it, None)

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
    start_date = models.DateTimeField(blank=True, null=True)
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
    
    def __init__(self, *args, **kwargs):
        super(Season, self).__init__(*args, **kwargs)
        self.initial_rounds = self.rounds
        self.initial_start_date = self.start_date
        
    def save(self, *args, **kwargs):
        # TODO: Add validation to prevent changes after a certain point
        rounds_changed = self.pk is None or self.rounds != self.initial_rounds
        start_date_changed = self.pk is None or self.start_date != self.initial_start_date
        super(Season, self).save(*args, **kwargs)
        
        if rounds_changed or start_date_changed:
            date = self.start_date
            for round_num in range(1, self.rounds + 1):
                # TODO: Allow round duration to be customized
                next_date = date + timedelta(days=7) if date is not None else None
                Round.objects.update_or_create(season=self, number=round_num, defaults={'start_date': date, 'end_date': next_date})
                date = next_date
    
    def calculate_scores(self):
        # Note: The scores are calculated in a particular way to allow easy adding of new tiebreaks
        score_dict = {}
        
        last_round = None
        for round_ in self.round_set.filter(is_completed=True).order_by('number'):
            round_pairings = round_.teampairing_set.all()
            for team in Team.objects.filter(season=self):
                white_pairing = find(round_pairings, white_team_id=team.id)
                black_pairing = find(round_pairings, black_team_id=team.id)
                if white_pairing is not None:
                    self._increment_score(score_dict, round_, last_round, team, white_pairing.black_team, white_pairing.white_points, white_pairing.black_points)
                elif black_pairing is not None:
                    self._increment_score(score_dict, round_, last_round, team, black_pairing.white_team, black_pairing.black_points, black_pairing.white_points)
                else:
                    score_dict[(team, round_)] = score_dict[(team, last_round)][:3] + (0,) if last_round is not None else (0, 0, 0, 0)
            last_round = round_
        
        team_scores = TeamScore.objects.filter(team__season=self)
        for score in team_scores:
            if last_round is None:
                score.match_count = 0
                score.match_points = 0
                score.game_points = 0
            else:
                score.match_count, score.match_points, score.game_points, _ = score_dict[(score.team, last_round)]
            score.save()
    
    def _increment_score(self, score_dict, round_, last_round, team, opponent, points, opponent_points):
        match_count, match_points, game_points, _ = score_dict[(team, last_round)] if last_round is not None else (0, 0, 0, 0)
        match_count += 1
        game_points += points
        if points > opponent_points:
            match_points += 2
        elif points == opponent_points:
            match_points += 1
        score_dict[(team, round_)] = (match_count, match_points, game_points, points)
    
    def is_started(self):
        return self.start_date is not None and self.start_date < timezone.now()
    
    def end_date(self):
        last_round = self.round_set.filter(number=self.rounds).first()
        if last_round is not None:
            return last_round.end_date
        return None
    
    def board_number_list(self):
        return [n for n in range(1, self.boards + 1)]
    
    def __unicode__(self):
        return self.name

#-------------------------------------------------------------------------------
class Round(_BaseModel):
    season = models.ForeignKey(Season)
    number = models.PositiveIntegerField(verbose_name='round number')
    start_date = models.DateTimeField(blank=True, null=True)
    end_date = models.DateTimeField(blank=True, null=True)
    
    publish_pairings = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)

    class Meta:
        permissions = (
            ('generate_pairings', 'Can generate and review pairings'),
        )
    
    def __init__(self, *args, **kwargs):
        super(Round, self).__init__(*args, **kwargs)
        self.initial_is_completed = self.is_completed
        
    def save(self, *args, **kwargs):
        is_completed_changed = self.pk is None and self.is_completed or self.is_completed != self.initial_is_completed
        super(Round, self).save(*args, **kwargs)
        if is_completed_changed:
            self.season.calculate_scores()
    
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
    number = models.PositiveIntegerField(verbose_name='team number')
    name = models.CharField(max_length=255, verbose_name='team name')
    is_active = models.BooleanField(default=True)
    
    seed_rating = models.PositiveIntegerField(blank=True, null=True)

    class Meta:
        unique_together = (('season', 'number'), ('season', 'name'))
    
    def boards(self):
        team_members = self.teammember_set.all()
        return [(n, find(team_members, board_number=n)) for n in Season.objects.get(pk=self.season_id).board_number_list()]
    
    def average_rating(self):
        n = 0
        total = 0.0
        for _, board in self.boards():
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
        white_pairings = self.team.pairings_as_white.all()
        black_pairings = self.team.pairings_as_black.all()
        for round_ in Round.objects.filter(season_id=self.team.season_id).order_by('number'):
            if round_ is None or not round_.is_completed:
                yield None
                continue
            points = None
            white_pairing = find(white_pairings, round_id=round_.id)
            black_pairing = find(black_pairings, round_id=round_.id)
            if white_pairing is not None:
                points = white_pairing.white_points / 2.0
            if black_pairing is not None:
                points = black_pairing.black_points / 2.0
            yield points
    
    def cross_scores(self):
        other_teams = Team.objects.filter(season_id=self.team.season_id).order_by('number')
        white_pairings = self.team.pairings_as_white.all()
        black_pairings = self.team.pairings_as_black.all()
        for other_team in other_teams:
            white_pairing = find(white_pairings, black_team_id=other_team.pk)
            black_pairing = find(black_pairings, white_team_id=other_team.pk)
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
class TeamPairing(_BaseModel):
    white_team = models.ForeignKey(Team, related_name="pairings_as_white")
    black_team = models.ForeignKey(Team, related_name="pairings_as_black")
    round = models.ForeignKey(Round)
    pairing_order = models.PositiveIntegerField()

    white_points = models.PositiveIntegerField(default=0)
    black_points = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('white_team', 'black_team', 'round')
    
    def __init__(self, *args, **kwargs):
        super(TeamPairing, self).__init__(*args, **kwargs)
        self.initial_white_points = self.white_points
        self.initial_black_points = self.black_points
        
    def save(self, *args, **kwargs):
        points_changed = self.pk is None or self.white_points != self.initial_white_points or self.black_points != self.initial_black_points
        super(TeamPairing, self).save(*args, **kwargs)
        if points_changed and self.round.is_completed:
            self.round.season.calculate_scores()
    
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
    white = models.ForeignKey(Player, blank=True, null=True, related_name="pairings_as_white")
    black = models.ForeignKey(Player, blank=True, null=True, related_name="pairings_as_black")

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
        if result_changed and hasattr(self, 'teamplayerpairing'):
            self.teamplayerpairing.team_pairing.refresh_points()
            self.teamplayerpairing.team_pairing.save()

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
    status = models.CharField(max_length=255, choices=REGISTRATION_STATUS_OPTIONS)
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
    unresponsive = models.BooleanField(default=False)    

    class Meta:
        unique_together = ('season', 'player')

    def __unicode__(self):
        return "%s" % self.player

#-------------------------------------------------------------------------------
class PlayerAvailability(_BaseModel):
    round = models.ForeignKey(Round)
    player = models.ForeignKey(Player)
    is_available = models.BooleanField(default=True)
    
    class Meta:
        verbose_name_plural = 'player availabilities'
    
    def __unicode__(self):
        return "%s" % self.player

#-------------------------------------------------------------------------------
class Alternate(_BaseModel):
    season_player = models.OneToOneField(SeasonPlayer)
    board_number = models.PositiveIntegerField(choices=BOARD_NUMBER_OPTIONS)
    
    def update_board_number(self):
        buckets = AlternateBucket.objects.filter(season=self.season)
        if len(buckets) == self.season.boards:
            for b in buckets:
                if (b.max_rating is None or b.max_rating >= self.player.rating) and (b.min_rating is None or self.player.rating > b.min_rating):
                    self.board_number = b.board_number
                    self.save()
    
    def priority_date(self):
        most_recent_assign = AlternateAssignment.objects.filter(player=self.season_player.player).order_by('-round__start_date').first()
        
        if most_recent_assign is not None:
            round_date = most_recent_assign.round.start_date
            if round_date is not None:
                return round_date
        
        if self.season_player.registration is not None:
            return self.season_player.registration.date_created
        
        return self.date_created
    
    def __unicode__(self):
        return "%s" % self.season_player

#-------------------------------------------------------------------------------
class AlternateAssignment(_BaseModel):
    round = models.ForeignKey(Round)
    team = models.ForeignKey(Team)
    board_number = models.PositiveIntegerField(choices=BOARD_NUMBER_OPTIONS)
    player = models.ForeignKey(Player)
    
    class Meta:
        unique_together = ('round', 'team', 'board_number')
        
    def save(self, *args, **kwargs):
        super(AlternateAssignment, self).save(*args, **kwargs)
        
        # Find and update any current pairings
        white_pairing = self.team.pairings_as_white.filter(round=self.round).first()
        if white_pairing is not None:
            tpp = white_pairing.teamplayerpairing_set.filter(board_number=self.board_number).first()
            if tpp is not None:
                if self.board_number % 2 == 1:
                    tpp.player_pairing.white = self.player
                else:
                    tpp.player_pairing.black = self.player
                tpp.player_pairing.save()
        black_pairing = self.team.pairings_as_black.filter(round=self.round).first()
        if black_pairing is not None:
            tpp = black_pairing.teamplayerpairing_set.filter(board_number=self.board_number).first()
            if tpp is not None:
                if self.board_number % 2 == 1:
                    tpp.player_pairing.black = self.player
                else:
                    tpp.player_pairing.white = self.player
                tpp.player_pairing.save()
    
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
        return "Board %d [%s, %s]" % (self.board_number, self.min_rating, self.max_rating)
    
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
    ('slack-welcome', 'Slack Welcome'),
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
