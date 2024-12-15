import random
import string
from datetime import datetime

from django.contrib.contenttypes.models import ContentType
from django.core.management import BaseCommand
from django.utils import timezone
from django_comments.models import Comment


class Command(BaseCommand):
    help = "Removes ALL emails from the database."

    def handle(self, *args, **options):
        letters = "".join([random.choice(string.ascii_letters) for x in range(4)])
        value = input(
            f"Are you sure you want to clean up all comments? Type: {letters} to confirm: "
        )
        if letters != value:
            print("You got it wrong, exiting")
            return

        print("Cleaning up all comments")

        models = [
            "player",
            "registration",
            "seasonplayer",
            "playerpairing",
            "loneplayerpairing",
            "alternate",
            "alternateassignment",
            "playeravailability",
            "playerlateregistration",
            "playerbye",
            "playerwithdrawal",
            "playerwarning",
        ]
        ct_pks = [ct.pk for ct in ContentType.objects.filter(model__in=models)]
        assert len(ct_pks) == len(models)
        jan_01_2021 = timezone.make_aware(datetime(2021, 1, 1))
        Comment.objects.filter(
            content_type_id__in=ct_pks, submit_date__lte=jan_01_2021
        ).exclude(user_name="System").delete()
