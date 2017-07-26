from heltour import settings
from heltour.tournament.models import *
from django.db.models.signals import post_save
from django.dispatch.dispatcher import receiver

@receiver(signals.mod_request_created, sender='appeal_late_response', dispatch_uid='heltour.tournament.automod')
def appeal_late_response_created(instance, **kwargs):
    pass