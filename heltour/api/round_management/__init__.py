"""Running a round.

This domain owns everything that happens once a round exists in the DB:
publishing pairings, broadcasting games, starting clocks, recording
results, presence tracking, and the live websocket fan-out that keeps
the UI in sync. It does not own creation of the *event* itself
(see ``event_setup``) nor team / lineup formation (see
``roster_formation``); those are upstream packages.
"""
