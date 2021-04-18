import random
import string
from django.core.management import BaseCommand
from django.utils import timezone
from heltour.tournament.models import *

from django_comments.models import Comment
from django.contrib.contenttypes.models import ContentType

class Command(BaseCommand):
    help = "Removes ALL emails from the database."

    def handle(self, *args, **options):
        letters = ''.join([random.choice(string.ascii_letters) for x in range(4)])
        value = input(f"Are you sure you want to clean up all comments? Type: {letters} to confirm: ")
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
        ct_pks = [
            ct.pk for ct in ContentType.objects.filter(model__in=models)
        ]
        assert(len(ct_pks) == len(models))
        for badword in ['mark', 'cheat', 'alt', 'tos violation']:
            Comment.objects.filter(
                content_type_id__in=ct_pks,
                comment__icontains=badword,
            ).delete()





