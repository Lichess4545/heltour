from django.dispatch.dispatcher import Signal

# Signals that run tasks
generate_pairings = Signal(providing_args=['round_id', 'overwrite'])

# Signals that send notifications
pairing_forfeit_changed = Signal(providing_args=['instance'])
notify_mods_unscheduled = Signal(providing_args=['round_'])
notify_mods_no_result = Signal(providing_args=['round_'])
pairings_generated = Signal(providing_args=['round_'])
no_round_transition = Signal(providing_args=['season', 'warnings'])
starting_round_transition = Signal(providing_args=['season', 'msg_list'])
alternate_search_started = Signal(providing_args=['season', 'team', 'board_number', 'round_'])
alternate_search_all_contacted = Signal(providing_args=['season', 'team', 'board_number', 'round_', 'number_contacted'])
alternate_assigned = Signal(providing_args=['season', 'alt_assignment'])
alternate_needed = Signal(providing_args=['alternate', 'accept_url', 'decline_url'])
