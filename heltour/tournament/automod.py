from heltour import settings
from heltour.tournament.models import *
from django.db.models.signals import post_save
from django.dispatch.dispatcher import receiver
from heltour.tournament.tasks import pairings_published
import reversion
import time

logger = logging.getLogger(__name__)

@receiver(post_save, sender=ModRequest, dispatch_uid='heltour.tournament.automod')
def mod_request_saved(instance, created, **kwargs):
    if created:
        signals.mod_request_created.send(sender=MOD_REQUEST_SENDER[instance.type], instance=instance)

@receiver(signals.mod_request_created, sender=MOD_REQUEST_SENDER['appeal_late_response'], dispatch_uid='heltour.tournament.automod')
def appeal_late_response_created(instance, **kwargs):
    # Figure out which round to use
    if not instance.round or instance.round.publish_pairings:
        instance.round = instance.season.round_set.order_by('number').filter(publish_pairings=True, is_completed=False).first()
        instance.save()

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

    instance.approve(response='You\'ve been withdrawn for round %d.' % instance.round.number)

@receiver(signals.mod_request_approved, sender=MOD_REQUEST_SENDER['withdraw'], dispatch_uid='heltour.tournament.automod')
def withdraw_approved(instance, **kwargs):
    # Add the withdrawal if it doesn't already exist
    with reversion.create_revision():
        reversion.set_comment('Withdraw request approved by %s' % instance.status_changed_by)
        PlayerWithdrawal.objects.get_or_create(player=instance.requester, round=instance.round)

@receiver(signals.automod_unresponsive, dispatch_uid='heltour.tournament.automod')
def automod_unresponsive(round_, **kwargs):
    groups = { 'warning': [], 'yellow': [], 'red': [] }
    for p in round_.pairings.filter(game_link='', result='', scheduled_time=None).exclude(white=None).exclude(black=None):
        white_present = p.get_player_presence(p.white).first_msg_time is not None
        black_present = p.get_player_presence(p.black).first_msg_time is not None
        if not white_present:
            player_unresponsive(round_, p, p.white, groups)
            if black_present:
                signals.notify_opponent_unresponsive.send(sender=automod_unresponsive, round_=round_, player=p.black, opponent=p.white)
            time.sleep(1)
        if not black_present:
            player_unresponsive(round_, p, p.black, groups)
            if white_present:
                signals.notify_opponent_unresponsive.send(sender=automod_unresponsive, round_=round_, player=p.white, opponent=p.black)
            time.sleep(1)
    signals.notify_mods_unresponsive.send(sender=automod_unresponsive, round_=round_, warnings=groups['warning'], yellows=groups['yellow'], reds=groups['red'])

def player_unresponsive(round_, pairing, player, groups):
    has_warning = PlayerWarning.objects.filter(player=player, round__season=round_.season, type='unresponsive').exists()
    if not has_warning:
        with reversion.create_revision():
            reversion.set_comment('Automatic warning for unresponsiveness')
            PlayerWarning.objects.create(player=player, round=round_, type='unresponsive')
        punishment = 'You may receive a yellow card.'
        allow_continue = True
        groups['warning'].append(player)
    else:
        card_color = give_card(round_, player, 'card_unresponsive')
        if not card_color:
            return
        punishment = 'You have been given a %s card.' % card_color
        allow_continue = card_color != 'red'
        groups[card_color].append(player)
    signals.notify_unresponsive.send(sender=automod_unresponsive, round_=round_, player=player, punishment=punishment, allow_continue=allow_continue)

@receiver(signals.mod_request_approved, sender=MOD_REQUEST_SENDER['appeal_late_response'], dispatch_uid='heltour.tournament.automod')
def appeal_late_response_approved(instance, **kwargs):
    with reversion.create_revision():
        reversion.set_comment('Late response appeal approved by %s' % instance.status_changed_by)
        warning = PlayerWarning.objects.filter(player=instance.requester, round=instance.round, type='unresponsive').first()
        if warning:
            warning.delete()
        else:
            revoke_card(instance.round, instance.requester, 'card_unresponsive')

def give_card(round_, player, type_):
    # TODO: Unit tests?
    with transaction.atomic():
        sp = SeasonPlayer.objects.filter(season=round_.season, player=player).first()
        if not sp:
            logger.error('Season player did not exist for %s %s' % (round_.season, player))
            return None
        already_has_card = PlayerWarning.objects.filter(player=player, round=round_, type__startswith='card').exists()
        card = PlayerWarning.objects.create(player=player, round=round_, type=type_)
        if not already_has_card:
            sp.games_missed += 1
            with reversion.create_revision():
                reversion.set_comment('Automatic %s %s' % (sp.card_color, card.get_type_display()))
                sp.save()
        return sp.card_color

def revoke_card(round_, player, type_):
    with transaction.atomic():
        sp = SeasonPlayer.objects.filter(season=round_.season, player=player).first()
        if not sp:
            logger.error('Season player did not exist for %s %s' % (round_.season, player))
            return
        card = PlayerWarning.objects.filter(player=player, round=round_, type=type_).first()
        if not card:
            return
        card.delete()
        has_other_card = PlayerWarning.objects.filter(player=player, round=round_, type__startswith='card').exists()
        if not has_other_card and sp.games_missed > 0:
            sp.games_missed -= 1
            with reversion.create_revision():
                reversion.set_comment('Card revocation')
                sp.save()
