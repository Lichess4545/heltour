"""Cross-domain plumbing: auth, permissions, pubsub, path validators, health.

Anything in here is consumed by multiple chess-domain packages and isn't
itself a chess concept. Resist adding domain logic here — if it's specific
to event setup, registration, roster formation, round management or
standings, it belongs in that domain package.
"""
