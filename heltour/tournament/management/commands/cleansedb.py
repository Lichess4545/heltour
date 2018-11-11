from django.core.management import BaseCommand
from heltour.tournament.models import *

from django_comments.models import Comment
from django.contrib.auth.models import User, Group
from django.contrib.sessions.models import Session
from django.contrib.sessions.models import Session
from reversion.models import Revision

class Command(BaseCommand):
    help = "Cleanse your local database of sensitive things"

    def handle(self, *args, **options):
        Session.objects.all().delete()
        for u in User.objects.all():
            u.set_password("09876default1234")
            u.email = "email-{}@example.com".format(u.id)
            u.save()
            u.user_permissions.all().delete()
        Group.objects.all().delete()
        for p in Player.objects.all():
            p.profile = None
            p.email = "email-{}@example.com".format(p.id)
            p.slack_user_id = ''
            p.save()
        for t in Team.objects.all():
            t.slack_channel = ''
            t.save()
        Registration.objects.filter(status='Rejected').delete()
        Registration.objects.filter(status='Pending').delete()
        for r in Registration.objects.all():
            r.email = "email-{}@example.com".format(r.id)
            r.status = 'Approved'
            r.validation_ok = True
            r.validation_warning = False
            r.friends = ''
            r.avoid = ''
            r.slack_username = ''
            r.save()
        Comment.objects.all().delete()
        FcmSub.objects.all().delete()
        GameNomination.objects.all().delete()
        SeasonPrizeWinner.objects.all().delete()
        SeasonPrize.objects.all().delete()
        GameSelection.objects.all().delete()
        ApiKey.objects.all().delete()
        PrivateUrlAuth.objects.all().delete()
        LoginToken.objects.all().delete()
        # TODO: could probably selectively delete these, but meh.
        SeasonDocument.objects.all().delete()
        LeagueDocument.objects.all().delete()
        Document.objects.all().delete()
        PlayerNotificationSetting.objects.all().delete()
        ModRequest.objects.all().delete()
        LeagueChannel.objects.all().delete()
        Revision.objects.all().delete()
