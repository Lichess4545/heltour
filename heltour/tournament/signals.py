from django.dispatch.dispatcher import Signal

generate_pairings = Signal(providing_args=['round_id', 'overwrite'])
pairing_forfeit_changed = Signal(providing_args=['instance'])
