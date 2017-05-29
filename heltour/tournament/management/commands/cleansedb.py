from django.core.management import BaseCommand

class Command(BaseCommand):
    help = "Cleanse your local database of sensitive things"

    def handle(self, *args, **options):
        from heltour.tournament.models import Player, Registration
        from django_comments.models import Comment
        from django.contrib.auth.models import User
        for u in User.objects.all():
            u.set_password("09876default1234")
            u.email = "email-{}@example.com".format(u.id)
            u.save()
        for p in Player.objects.all():
            p.email = "email-{}@example.com".format(p.id)
            p.save()
        for r in Registration.objects.all():
            r.email = "email-{}@example.com".format(r.id)
            r.save()
        Comment.objects.all().delete()
