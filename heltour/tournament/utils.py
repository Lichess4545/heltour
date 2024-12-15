from django.utils import timezone


def current_round(season):
    if not season.alternates_manager_enabled():
        return None
    # Figure out which round we should be running a search for
    # Depends on the round state, current date and alternates manager settings
    last_published = (
        season.round_set.filter(publish_pairings=True).order_by("-number").first()
    )
    if last_published is None:
        return None
    setting = season.alternates_manager_setting()
    if not setting.contact_before_round_start:
        current = last_published
    elif (
        timezone.now()
        < last_published.end_date - setting.contact_offset_before_round_start
    ):
        current = last_published
    else:
        current = (
            season.round_set.filter(number=last_published.number + 1).first()
            or last_published
        )
    if current.is_completed:
        return None
    return current
