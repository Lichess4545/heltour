import sys

from django.utils.crypto import get_random_string
from django.core.management import BaseCommand
from django.utils import timezone
from django.contrib.auth.models import User
from django.utils import timezone

from heltour.tournament.models import (
    LeagueModerator,
    LoginToken,
    ModRequest,
    Player,
    PrivateUrlAuth,
    Registration,
)


class Command(BaseCommand):
    help = "Anonymizes a user within the 4545 league database."


    def add_arguments(self, parser):
        parser.add_argument('username', nargs=1, type=str)

    def handle(self, *args, **options):
        # TODO: revisions probably need to be updated.
        # TODO: comments might have player names in it?
        username = options['username'][0]
        try:
            player = Player.objects.get(lichess_username__iexact=username.lower())
        except Player.DoesNotExist:
            sys.exit(f"Unable to find player with username: {username}")

        if player.account_status not in ['normal', 'closed']:
            sys.exit(f"Unable to GDPR erase for legitimate interests")

        rando = get_random_string(8)
        anon_username = f"ghost_{rando}"
        anon_email = f"ghost_{rando}@example.com"
        anon_slack = f"ghost_{rando}"
        player.lichess_username = anon_username
        player.rating = 1500
        player.games_played = 0
        player.email = anon_email
        player.is_active = False
        player.slack_user_id = ''
        player.timezone_offset = None
        player.oauth_token = None
        player.profile = ''
        player.gdpr_erased = True
        player.save()

        LeagueModerator.objects \
            .filter(player=player) \
            .delete()

        PrivateUrlAuth.objects \
            .filter(authenticated_user__iexact=username.lower()) \
            .delete()

        ModRequest.objects \
            .filter(requester=player) \
            .delete()

        Registration.objects \
            .filter(lichess_username__iexact=username.lower()) \
            .update(
                lichess_username=anon_username,
                slack_username=anon_slack,
                email=anon_email,

                classical_rating=1500,
                peak_classical_rating=1500,

                has_played_20_games=True,
                already_in_slack_group=False,
                previous_season_alternate='new',

                can_commit=True,
                friends='',
                avoid='',
                agreed_to_rules=True,
                alternate_preference='full_time',
                weeks_unavailable='',
                section_preference=None,
                validation_ok=True,
                validation_warning=False,
            )

        LoginToken.objects \
            .filter(lichess_username__iexact=username.lower()) \
            .delete()


        now = timezone.now()
        User.objects \
            .filter(username__iexact=username.lower()) \
            .update(
                username=anon_username,
                email='',
                first_name='',
                last_name='',
                is_staff=False,
                is_active=False,
                is_superuser=False,
                last_login=now,
                date_joined=now,
            )

        print(f"{username} has been gdpr erased")
