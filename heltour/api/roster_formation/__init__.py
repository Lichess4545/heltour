"""Team / roster / lineup / section formation.

Captains form teams and rosters/lineups, arbiters approve them, then
they're set in stone. Arbiters also move teams or individuals between
sections, or remove participants entirely. The same actions happen
between rounds (withdrawals, byes, late registration) — that is
implemented here too rather than splitting into a separate domain;
between-round transitions are a state, not a separate concept.
"""
