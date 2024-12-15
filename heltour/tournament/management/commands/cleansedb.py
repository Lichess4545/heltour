from django.contrib.auth.models import Group, User
from django.contrib.sessions.models import Session
from django.core.management import BaseCommand
from django.utils import timezone
from django_comments.models import Comment
from impersonate.models import ImpersonationLog
from reversion.models import Revision

from heltour.tournament.models import (
    ApiKey,
    Document,
    FcmSub,
    GameNomination,
    LeagueChannel,
    LeagueDocument,
    LeagueModerator,
    LoginToken,
    ModRequest,
    OauthToken,
    Player,
    PlayerNotificationSetting,
    PlayerPresence,
    PlayerWarning,
    PrivateUrlAuth,
    Registration,
    ScheduledNotification,
    SeasonDocument,
    Team,
)


class Command(BaseCommand):
    help = "Cleanse your local database of sensitive things"

    def handle(self, *args, **options):
        Session.objects.all().delete()
        for u in User.objects.all():
            u.set_password("09876default1234")
            u.email = "email-{}@example.com".format(u.id)
            u.is_staff = False
            u.last_login = None
            u.date_joined = timezone.now()
            u.save()
            u.user_permissions.all().delete()
        Group.objects.all().delete()
        for p in Player.objects.all():
            p.email = "email-{}@example.com".format(p.id)
            p.slack_user_id = ""
            p.timezone_offset = None
            p.save()
        for t in Team.objects.all():
            t.slack_channel = ""
            t.save()
        Registration.objects.filter(status="rejected").delete()
        Registration.objects.filter(status="pending").delete()
        for r in Registration.objects.all():
            r.email = "email-{}@example.com".format(r.id)
            r.status = "approved"
            r.validation_ok = True
            r.validation_warning = False
            r.friends = ""
            r.avoid = ""
            r.slack_username = ""
            r.save()
        LeagueModerator.objects.all().delete()
        Comment.objects.all().delete()
        FcmSub.objects.all().delete()
        GameNomination.objects.all().delete()
        ApiKey.objects.all().delete()
        PrivateUrlAuth.objects.all().delete()
        LoginToken.objects.all().delete()
        OauthToken.objects.all().delete()
        # TODO: could probably selectively delete these, but meh.
        SeasonDocument.objects.all().delete()
        LeagueDocument.objects.all().delete()
        Document.objects.all().delete()
        PlayerNotificationSetting.objects.all().delete()
        ModRequest.objects.all().delete()
        LeagueChannel.objects.all().delete()
        Revision.objects.all().delete()
        ImpersonationLog.objects.all().delete()
        ScheduledNotification.objects.all().delete()
        PlayerPresence.objects.all().delete()
        PlayerWarning.objects.all().delete()
