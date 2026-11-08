import random
import string
from django.contrib.auth.models import User
from django.core.management import BaseCommand
from django.utils import timezone
from django_comments.models import Comment
from heltour.tournament.models import *

from heltour.tournament.models import Player, Registration

class Command(BaseCommand):
    help = "Removes ALL emails from the database."

    def handle(self, *args, **options):
        letters = ''.join([random.choice(string.ascii_letters) for x in range(4)])
        value = input(f"Are you sure you want to remove all emails? Type: {letters} to confirm: ")
        if letters != value:
            print("You got it wrong, not removing emails")
            return

        print("Removing all emails")
        Player.objects.all().update(email='', normalized_email='')
        Registration.objects.all().update(email='')
        User.objects.all().update(email='')
        Comment.objects.all().update(user_email='')


