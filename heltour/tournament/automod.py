from heltour import settings
from heltour.tournament.models import *
from django.db.models.signals import post_save
from django.dispatch.dispatcher import receiver
from heltour.tournament.tasks import pairings_published
from textwrap import dedent
import reversion
import time

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ModRequest, dispatch_uid='heltour.tournament.automod')
def mod_request_saved(instance, created, **kwargs):
    if created:
        signals.mod_request_created.send(sender=MOD_REQUEST_SENDER[instance.type],
                                         instance=instance)


@receiver(signals.mod_request_created, sender=MOD_REQUEST_SENDER['appeal_late_response'],
          dispatch_uid='heltour.tournament.automod')
def appeal_late_response_created(instance, **kwargs):
    # Figure out which round to use
    if not instance.round or instance.round.publish_pairings:
        instance.round = instance.season.round_set.order_by('number').filter(publish_pairings=True,
                                                                             is_completed=False).first()
        instance.save()


@receiver(signals.mod_request_created, sender=MOD_REQUEST_SENDER['request_continuation'],
          dispatch_uid='heltour.tournament.automod')
def request_continuation_created(instance, **kwargs):
    # Figure out which round to use
    if not instance.round or instance.round.publish_pairings:
        instance.round = instance.season.round_set.order_by('number').filter(
            publish_pairings=False).first()
        instance.save()


@receiver(signals.mod_request_created, sender=MOD_REQUEST_SENDER['withdraw'],
          dispatch_uid='heltour.tournament.automod')
def withdraw_created(instance, **kwargs):
    # Figure out which round to add the withdrawal on
    if not instance.round or instance.round.publish_pairings:
        instance.round = instance.season.round_set.order_by('number').filter(
            publish_pairings=False).first()
        instance.save()

    # Check that the requester is part of the season
    sp = SeasonPlayer.objects.filter(player=instance.requester, season=instance.season).first()
    if sp is None:
        instance.reject(response='You aren\'t currently a participant in %s.' % instance.season)
        return

    if not instance.round:
        instance.reject(response='You can\'t withdraw from the season at this time.')
        return

    instance.approve(response='You\'ve been withdrawn from the season. The withdrawal takes effect at the start of round %d.' % instance.round.number)


@receiver(signals.mod_request_approved, sender=MOD_REQUEST_SENDER['withdraw'],
          dispatch_uid='heltour.tournament.automod')
def withdraw_approved(instance, **kwargs):
    if not instance.round:
        return

    # Add the withdrawal if it doesn't already exist
    with reversion.create_revision():
        reversion.set_comment('Withdraw request approved by %s' % instance.status_changed_by)
        PlayerWithdrawal.objects.get_or_create(player=instance.requester, round=instance.round)


@receiver(signals.automod_unresponsive, dispatch_uid='heltour.tournament.automod')
def automod_unresponsive(round_, **kwargs):
    groups = {'warning': [], 'yellow': [], 'red': []}
    for p in round_.pairings.filter(game_link='', result='', scheduled_time=None).exclude(
        white=None).exclude(black=None):
        # verify that neither player is previously marked unavailable
        # verify that both players on the pairing have been assigned more than 24 hours ago.
        if round_.season.league.competitor_type == 'team':
            white_unavail = PlayerAvailability.objects.filter(round=round_, player=p.white,
                                                              is_available=False).exists()
            black_unavail = PlayerAvailability.objects.filter(round=round_, player=p.black,
                                                              is_available=False).exists()
            if white_unavail or black_unavail or p.pairing_changed_after_round_start():
                continue
        # check who is not present
        white_present = p.get_player_presence(p.white).first_msg_time is not None
        black_present = p.get_player_presence(p.black).first_msg_time is not None
        if not white_present:
            player_unresponsive(round_, p, p.white, groups)
            if black_present:
                signals.notify_opponent_unresponsive.send(sender=automod_unresponsive,
                                                          round_=round_, player=p.black,
                                                          opponent=p.white, pairing=p)
            time.sleep(1)
        if not black_present:
            player_unresponsive(round_, p, p.black, groups)
            if white_present:
                signals.notify_opponent_unresponsive.send(sender=automod_unresponsive,
                                                          round_=round_, player=p.white,
                                                          opponent=p.black, pairing=p)
            time.sleep(1)
    signals.notify_mods_unresponsive.send(sender=automod_unresponsive, round_=round_,
                                          warnings=groups['warning'], yellows=groups['yellow'],
                                          reds=groups['red'])


def player_unresponsive(round_, pairing, player, groups):
    season = round_.season
    league = season.league
    has_warning = PlayerWarning.objects.filter(player=player, round__season=season,
                                               type='unresponsive').exists()
    if not has_warning and league.get_leaguesetting().warning_for_late_response:
        with reversion.create_revision():
            reversion.set_comment('Automatic warning for unresponsiveness')
            PlayerWarning.objects.get_or_create(player=player, round=round_, type='unresponsive')
        punishment = 'You may receive a yellow card.'
        allow_continue = league.competitor_type != 'team'
        groups['warning'].append(player)
    else:
        card_color = give_card(round_, player, 'card_unresponsive')
        if not card_color:
            return
        punishment = 'You have been given a %s card.' % card_color
        allow_continue = card_color != 'red' and league.competitor_type != 'team'
        groups[card_color].append(player)
    if league.competitor_type == 'team':
        avail, _ = PlayerAvailability.objects.get_or_create(round=round_, player=player)
        avail.is_available = False
        avail.save()
    signals.notify_unresponsive.send(sender=automod_unresponsive, round_=round_, player=player,
                                     punishment=punishment, allow_continue=allow_continue,
                                     pairing=pairing)


@receiver(signals.mod_request_approved, sender=MOD_REQUEST_SENDER['appeal_late_response'],
          dispatch_uid='heltour.tournament.automod')
def appeal_late_response_approved(instance, **kwargs):
    if not instance.pairing:
        return

    with reversion.create_revision():
        reversion.set_comment('Late response appeal approved by %s' % instance.status_changed_by)
        warning = PlayerWarning.objects.filter(player=instance.requester, round=instance.round,
                                               type='unresponsive').first()
        if warning:
            warning.delete()
        else:
            revoke_card(instance.round, instance.requester, 'card_unresponsive')


@receiver(signals.automod_noshow, dispatch_uid='heltour.tournament.automod')
def automod_noshow(pairing, **kwargs):
    if pairing.game_link and (not pairing.white_confirmed or not pairing.black_confirmed):
        # Game started, but not by us, so no action necessary
        return
    if not pairing.result:
        # Game ended, no action necessary.
        return
    if pairing.white_confirmed and pairing.black_confirmed:
        # We probably tried to start this game, check if there are moves
        game_meta = lichessapi.get_game_meta(p.game_id(), priority=0, timeout=300)
        if ' ' in game_meta['moves']:
            # space in the move lists indicates that both players played at least one move
            return
    white_online = pairing.get_player_presence(pairing.white).online_for_game
    black_online = pairing.get_player_presence(pairing.black).online_for_game
    if white_online and not black_online:
        player_noshow(pairing, pairing.white, pairing.black)
    if black_online and not white_online:
        player_noshow(pairing, pairing.black, pairing.white)


def player_noshow(pairing, player, opponent):
    round_ = pairing.get_round()
    signals.notify_noshow.send(sender=automod_unresponsive, round_=round_, player=player,
                               opponent=opponent)


@receiver(signals.mod_request_created, sender=MOD_REQUEST_SENDER['claim_win_noshow'],
          dispatch_uid='heltour.tournament.automod')
def claim_win_noshow_created(instance, **kwargs):
    # Figure out which round to add the claim on
    if not instance.round:
        instance.round = instance.season.round_set.order_by('number').filter(is_completed=False,
                                                                             publish_pairings=True).first()
        instance.save()
    if not instance.pairing and instance.round:
        instance.pairing = instance.round.pairing_for(instance.requester)
        instance.save()

    # Check that the requester is part of the season
    sp = SeasonPlayer.objects.filter(player=instance.requester, season=instance.season).first()
    if sp is None:
        instance.reject(response='You aren\'t currently a participant in %s.' % instance.season)
        return

    if not instance.round:
        instance.reject(response='You can\'t claim a win at this time.')
        return

    if not instance.pairing:
        instance.reject(response='You don\'t currently have a pairing you can claim a win for.')
        return

    p = instance.pairing
    opponent = p.white if p.white != instance.requester else p.black

    if p.get_player_presence(instance.requester).online_for_game \
        and not p.get_player_presence(opponent).online_for_game \
        and timezone.now() > p.scheduled_time + timedelta(minutes=21):
        instance.approve(
            response='You\'ve been given a win by forfeit. It is still possible to reschedule and play the game if you want to.')


@receiver(signals.mod_request_approved, sender=MOD_REQUEST_SENDER['claim_win_noshow'],
          dispatch_uid='heltour.tournament.automod')
def claim_win_noshow_approved(instance, **kwargs):
    if not instance.pairing:
        return

    p = instance.pairing
    opponent = p.white if p.white != instance.requester else p.black

    with reversion.create_revision():
        reversion.set_comment('Auto forfeit for no-show')
        if p.white == instance.requester:
            p.result = '1X-0F'
        if p.black == instance.requester:
            p.result = '0F-1X'
        p.save()
    add_system_comment(p, '%s no-show' % opponent.lichess_username)
    sp = SeasonPlayer.objects.filter(player=opponent, season=instance.season).first()
    add_system_comment(sp, 'Round %d no-show' % instance.round.number)

    card_color = give_card(instance.round, opponent, 'card_noshow')
    if not card_color:
        return
    punishment = 'You have been given a %s card.' % card_color
    allow_continue = card_color != 'red' and instance.season.league.competitor_type != 'team'
    signals.notify_noshow_claim.send(sender=claim_win_noshow_approved, round_=instance.round,
                                     player=opponent, punishment=punishment,
                                     allow_continue=allow_continue)


@receiver(signals.mod_request_created, sender=MOD_REQUEST_SENDER['appeal_noshow'],
          dispatch_uid='heltour.tournament.automod')
def appeal_noshow_created(instance, **kwargs):
    # Figure out which round to use
    if not instance.round:
        instance.round = instance.season.round_set.order_by('number').filter(publish_pairings=True,
                                                                             is_completed=False).first()
        instance.save()
    if not instance.pairing and instance.round:
        instance.pairing = instance.round.pairing_for(instance.requester)
        instance.save()


@receiver(signals.mod_request_approved, sender=MOD_REQUEST_SENDER['appeal_noshow'],
          dispatch_uid='heltour.tournament.automod')
def appeal_noshow_approved(instance, **kwargs):
    if not instance.pairing:
        return

    with reversion.create_revision():
        reversion.set_comment('No-show appeal approved by %s' % instance.status_changed_by)
        revoke_card(instance.round, instance.requester, 'card_noshow')
    with reversion.create_revision():
        reversion.set_comment('No-show appeal approved by %s' % instance.status_changed_by)
        instance.pairing.result = ''
        instance.pairing.save()


@receiver(signals.mod_request_created, sender=MOD_REQUEST_SENDER['claim_draw_scheduling'],
          dispatch_uid='heltour.tournament.automod')
def claim_draw_scheduling_created(instance, **kwargs):
    # Figure out which round to add the claim on
    if not instance.round:
        instance.round = instance.season.round_set.order_by('number').filter(is_completed=False,
                                                                             publish_pairings=True).first()
        instance.save()
    if not instance.pairing and instance.round:
        instance.pairing = instance.round.pairing_for(instance.requester)
        instance.save()

    # Check that the requester is part of the season
    sp = SeasonPlayer.objects.filter(player=instance.requester, season=instance.season).first()
    if sp is None:
        instance.reject(response='You aren\'t currently a participant in %s.' % instance.season)
        return

    if not instance.round:
        instance.reject(response='You can\'t claim a scheduling draw at this time.')
        return

    if not instance.pairing:
        instance.reject(
            response='You don\'t currently have a pairing you can claim a scheduling draw for.')
        return

    if instance.pairing.result:
        instance.reject(
            response='You can\'t claim a scheduling draw for a game which already has a set result.')
        return

    add_system_comment(instance.pairing, 'Scheduling draw claim made by %s' % instance.requester)


@receiver(signals.mod_request_approved, sender=MOD_REQUEST_SENDER['claim_draw_scheduling'],
          dispatch_uid='heltour.tournament.automod')
def claim_scheduling_draw_approved(instance, **kwargs):
    if not instance.pairing:
        return

    p = instance.pairing
    opponent = p.white if p.white != instance.requester else p.black
    comment_ = 'Scheduling draw claim approved by %s' % instance.status_changed_by
    with reversion.create_revision():
        reversion.set_comment(comment_)
        p.result = '1/2Z-1/2Z'
        p.save()
    add_system_comment(p, comment_)
    signals.notify_scheduling_draw_claim.send(sender=claim_scheduling_draw_approved,
                                              round_=instance.round, player=opponent)


@receiver(signals.mod_request_created, sender=MOD_REQUEST_SENDER['appeal_draw_scheduling'],
          dispatch_uid='heltour.tournament.automod')
def appeal_scheduling_draw_created(instance, **kwargs):
    # Figure out which round to use    
    if not instance.round:
        instance.round = instance.season.round_set.order_by('number').filter(publish_pairings=True,
                                                                             is_completed=False).first()
        instance.save()
    if not instance.pairing and instance.round:
        instance.pairing = instance.round.pairing_for(instance.requester)
        instance.save()
    add_system_comment(instance.pairing, 'Scheduling draw appeal by %s' % instance.requester)


@receiver(signals.mod_request_approved, sender=MOD_REQUEST_SENDER['appeal_draw_scheduling'],
          dispatch_uid='heltour.tournament.automod')
def appeal_scheduling_draw_approved(instance, **kwargs):
    if not instance.pairing:
        return

    comment_ = 'Scheduling draw appeal approved by %s' % instance.status_changed_by
    with reversion.create_revision():
        reversion.set_comment(comment_)
        instance.pairing.result = ''
        instance.pairing.save()
    add_system_comment(instance.pairing, comment_)


def give_card(round_, player, type_):
    # TODO: Unit tests?
    with transaction.atomic():
        sp = SeasonPlayer.objects.filter(season=round_.season, player=player).first()
        if not sp:
            logger.error('Season player did not exist for %s %s' % (round_.season, player))
            return None
        already_has_card = PlayerWarning.objects.filter(player=player, round=round_,
                                                        type__startswith='card').exists()
        card, _ = PlayerWarning.objects.get_or_create(player=player, round=round_, type=type_)
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
        has_other_card = PlayerWarning.objects.filter(player=player, round=round_,
                                                      type__startswith='card').exists()
        if not has_other_card and sp.games_missed > 0:
            sp.games_missed -= 1
            with reversion.create_revision():
                reversion.set_comment('Card revocation')
                sp.save()
