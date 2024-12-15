import random
import string

from django.core.management import BaseCommand

from heltour.tournament.models import Player, Registration


class Command(BaseCommand):
    help = "Removes ALL emails from the database."

    def handle(self, *args, **options):
        letters = "".join([random.choice(string.ascii_letters) for x in range(4)])
        value = input(
            f"Are you sure you want to remove all emails? Type: {letters} to confirm: "
        )
        if letters != value:
            print("You got it wrong, not removing emails")
            return

        print("Removing all emails")
        Player.objects.all().update(email="")
        Registration.objects.all().update(email="")
