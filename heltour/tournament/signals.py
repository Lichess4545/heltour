from django.dispatch.dispatcher import Signal

# Signals that run tasks
do_generate_pairings = Signal()
do_round_transition = Signal()
do_schedule_publish = Signal()
do_pairings_published = Signal()
do_validate_registration = Signal()
do_create_team_channel = Signal()

# Signals that send notifications
pairing_forfeit_changed = Signal()
player_account_status_changed = Signal()
notify_mods_unscheduled = Signal()
notify_mods_no_result = Signal()
notify_mods_pending_regs = Signal()
notify_mods_pairings_published = Signal()
notify_mods_round_start_done = Signal()
pairings_generated = Signal()
no_round_transition = Signal()
starting_round_transition = Signal()
alternate_search_started = Signal()
alternate_search_reminder = Signal()
alternate_search_all_contacted = Signal()
alternate_search_failed = Signal()
alternate_assigned = Signal()
alternate_needed = Signal()
alternate_spots_filled = Signal()
notify_players_round_start = Signal()
notify_players_late_pairing = Signal()
notify_players_unscheduled = Signal()
notify_players_game_time = Signal()
notify_players_game_started = Signal()
before_game_time = Signal()
game_warning = Signal()
league_comment = Signal()
notify_unresponsive = Signal()
notify_opponent_unresponsive = Signal()
notify_mods_unresponsive = Signal()
notify_noshow = Signal()
notify_noshow_claim = Signal()
notify_scheduling_draw_claim = Signal()
slack_account_linked = Signal()
publish_scheduled = Signal()
# Automod signals
automod_unresponsive = Signal()
automod_noshow = Signal()
mod_request_created = Signal()
mod_request_approved = Signal()
mod_request_rejected = Signal()
