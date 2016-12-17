import reversion
from django.contrib import messages
from heltour.tournament.models import *
from heltour.tournament import pairinggen, signals

class RoundTransitionWorkflow():

    def __init__(self, season):
        self.season = season

    @property
    def round_to_close(self):
        return self.season.round_set.filter(publish_pairings=True, is_completed=False).order_by('number').first()

    @property
    def round_to_open(self):
        return self.season.round_set.filter(publish_pairings=False, is_completed=False).order_by('number').first()

    @property
    def season_to_close(self):
        round_to_close = self.round_to_close
        round_to_open = self.round_to_open
        return self.season if not self.season.is_completed and round_to_open is None and (round_to_close is None or round_to_close.number == self.season.rounds) else None

    def run(self, complete_round=False, complete_season=False, update_board_order=False, generate_pairings=False, background=False, user=None):
        msg_list = []
        round_to_close = self.round_to_close
        round_to_open = self.round_to_open
        season_to_close = self.season_to_close

        with transaction.atomic():
            if complete_round and round_to_close is not None:
                with reversion.create_revision():
                    reversion.set_user(user)
                    reversion.set_comment('Closed round.')
                    round_to_close.is_completed = True
                    round_to_close.save()
                msg_list.append(('Round %d set as completed.' % round_to_close.number, messages.INFO))
            if complete_season and season_to_close is not None and (round_to_close is None or round_to_close.is_completed):
                with reversion.create_revision():
                    reversion.set_user(user)
                    reversion.set_comment('Closed season.')
                    season_to_close.is_completed = True
                    season_to_close.save()
                msg_list.append(('%s set as completed.' % season_to_close.name, messages.INFO))
            if update_board_order and round_to_open is not None and self.season.league.competitor_type == 'team':
                try:
                    self.do_update_board_order(self.season)
                    msg_list.append(('Board order updated.', messages.INFO))
                except IndexError:
                    msg_list.append(('Error updating board order.', messages.ERROR))
                    return msg_list
            if generate_pairings and round_to_open is not None:
                if background:
                    signals.do_generate_pairings.send(sender=self.__class__, round_id=round_to_open.pk)
                    msg_list.append(('Generating pairings in background.', messages.INFO))
                else:
                    try:
                        pairinggen.generate_pairings(round_to_open, overwrite=False)
                        with reversion.create_revision():
                            reversion.set_user(user)
                            reversion.set_comment('Generated pairings.')
                            round_to_open.publish_pairings = False
                            round_to_open.save()
                        msg_list.append(('Pairings generated.', messages.INFO))
                    except pairinggen.PairingsExistException:
                        msg_list.append(('Unpublished pairings already exist.', messages.WARNING))
                    except pairinggen.PairingHasResultException:
                        msg_list.append(('Pairings with results can\'t be overwritten.', messages.ERROR))
        return msg_list

    @property
    def warnings(self):
        msg_list = []
        round_to_close = self.round_to_close
        round_to_open = self.round_to_open

        if round_to_close is not None and round_to_close.end_date is not None and round_to_close.end_date > timezone.now() + timedelta(hours=1):
            time_from_now = self._time_from_now(round_to_close.end_date - timezone.now())
            msg_list.append(('The round %d end date is %s from now.' % (round_to_close.number, time_from_now), messages.WARNING))
        elif round_to_open is not None and round_to_open.start_date is not None and round_to_open.start_date > timezone.now() + timedelta(hours=1):
            time_from_now = self._time_from_now(round_to_open.start_date - timezone.now())
            msg_list.append(('The round %d start date is %s from now.' % (round_to_open.number, time_from_now), messages.WARNING))

        if round_to_close is not None:
            incomplete_pairings = PlayerPairing.objects.filter(result='', teamplayerpairing__team_pairing__round=round_to_close).nocache() | \
                                  PlayerPairing.objects.filter(result='', loneplayerpairing__round=round_to_close).nocache()
            if len(incomplete_pairings) > 0:
                msg_list.append(('Round %d has %d pairing(s) without a result.' % (round_to_close.number, len(incomplete_pairings)), messages.WARNING))

        return msg_list

    def _time_from_now(self, delta):
        if delta.days > 0:
            if delta.days == 1:
                return '1 day'
            else:
                return '%d days' % delta.days
        else:
            hours = delta.seconds / 3600
            if hours == 1:
                return '1 hour'
            else:
                return '%d hours' % hours
