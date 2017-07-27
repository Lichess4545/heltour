from heltour import settings
from heltour.tournament.models import *
from django.db.models.signals import post_save
from django.dispatch.dispatcher import receiver
from heltour.tournament.tasks import pairings_published

@receiver(post_save, sender=ModRequest, dispatch_uid='heltour.tournament.automod')
def mod_request_saved(instance, created, **kwargs):
    if created:
        signals.mod_request_created.send(sender=MOD_REQUEST_SENDER[instance.type], instance=instance)

@receiver(signals.mod_request_created, sender=MOD_REQUEST_SENDER['appeal_late_response'], dispatch_uid='heltour.tournament.automod')
def appeal_late_response_created(instance, **kwargs):
    pass

@receiver(signals.mod_request_created, sender=MOD_REQUEST_SENDER['withdraw'], dispatch_uid='heltour.tournament.automod')
def withdraw_created(instance, **kwargs):
    # Figure out which round to add the withdrawal on
    if not instance.round or instance.round.publish_pairings:
        instance.round = instance.season.round_set.order_by('number').filter(publish_pairings=False).first()
        instance.save()

    # Check that the requester is part of the season
    sp = SeasonPlayer.objects.filter(player=instance.requester, season=instance.season).first()
    if sp is None:
        instance.reject(response='You aren\'t currently a participant in %s.' % instance.season)
        return

    if not instance.round:
        instance.reject(response='You can\'t withdraw from the season at this time.')
        return

    instance.approve()

@receiver(signals.mod_request_approved, sender=MOD_REQUEST_SENDER['withdraw'], dispatch_uid='heltour.tournament.automod')
def withdraw_approved(instance, **kwargs):
    # Add the withdrawal if it doesn't already exist
    PlayerWithdrawal.objects.get_or_create(player=instance.requester, round=instance.round)
