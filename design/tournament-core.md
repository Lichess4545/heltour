# Tournament Core Module and Testing

## Architecture

`heltour/tournament_core/` is a clean, database-independent
representation of tournaments. No Django imports — just dataclasses and
calculation logic.

- `structure.py` — `Game`, `Match`, `Round`, `Tournament` (frozen
  dataclasses), helpers for creating matches (single game / team /
  bye), tournament calculation methods.
- `tiebreaks.py` — `MatchResult`, `CompetitorScore`, plus tiebreak
  functions: Sonneborn-Berger, Buchholz, Head-to-Head, Games Won. Work
  for both team and individual tournaments.
- `scoring.py` — `ScoringSystem` (standard 2-1-0, alternative 3-1-0,
  etc.). Handles game points, match points, bye scoring.
- `builder.py` — fluent `TournamentBuilder` for tests.
- `assertions.py` — fluent assertion interface for tournament
  standings.

`heltour/tournament/db_to_structure.py` converts Django ORM models to
`tournament_core` structures:

- `season_to_tournament_structure()` — main entry point.
- `team_tournament_to_structure()` — handles team tournaments with
  board pairings.
- `lone_tournament_to_structure()` — handles individual tournaments.
- Properly handles color alternation in team matches.

## Use the builder for tests

```python
# Team tournament example
builder = TournamentBuilder()
builder.league("Test League", "TL", "team")
builder.season("TL", "Spring 2024", rounds=3, boards=2)
builder.team("Dragons", ("Alice", 2000), ("Bob", 1900))
builder.team("Knights", ("Charlie", 1950), ("David", 1850))
builder.round(1)
builder.match("Dragons", "Knights", "1-0", "1/2-1/2")  # Dragons 1.5-0.5
builder.complete()
tournament = builder.build()

# Individual tournament example
builder = TournamentBuilder()
builder.league("Chess Club", "CC", "lone")
builder.season("CC", "Winter 2024", rounds=3)
builder.player("Alice", 2100)
builder.player("Bob", 2000)
builder.round(1)
builder.game("Alice", "Bob", "1-0")
builder.complete()
tournament = builder.build()
```

## Fluent assertion interface

```python
from heltour.tournament_core.assertions import assert_tournament

# Team tournament standings
assert_tournament(tournament).team("Dragons").assert_()
    .wins(2).losses(0).draws(1)
    .match_points(5).game_points(4.5)
    .games_won(3)               # team tournaments only
    .position(1)

# Individual tournament standings
assert_tournament(tournament).player("Alice").assert_()
    .wins(2).losses(1).draws(0)
    .match_points(4).game_points(2.0)
    .byes(1)
    .position(2)

# Tiebreaks
assert_tournament(tournament).player("Alice").assert_()
    .tiebreak("sonneborn_berger", 3.5)
    .tiebreak("buchholz", 6.0)
```

### Team-tournament assertion notes

- Match results are from the *first* team's perspective.
- `"1-0"` means the first team's player wins that board.
- On alternating (odd-numbered) boards, colors are swapped
  automatically.
- Example: `.match("Dragons", "Knights", "1-0", "1-0")` means Dragons
  win both boards.

## Database test requirements

- **Team tournaments must have board pairings.** The system raises if a
  `TeamPairing` lacks `TeamPlayerPairing` children — there is no
  legacy/aggregate-only mode.
- **Avoid circular dependencies.** Create rounds as
  `is_completed=False`, add all pairings and board results, then mark
  the round complete.
- **No synthetic data.** Aggregate scores must come from real game
  results, not stuffed values.

## Testing workflow

1. Pure logic tests → use `tournament_core` structures directly.
2. Integration tests → create complete database structures with board
   pairings.
3. Use `season_to_tournament_structure()` to convert ORM models to
   `tournament_core`.
4. All calculations flow through `tournament_core` for consistency.

## Design decisions

1. **No legacy support** — all team matches must have board results.
2. **Clean errors** — raise on incomplete data instead of guessing.
3. **Immutable structures** — frozen dataclasses, thread-safe.
4. **Separation of concerns** — DB models persist; `tournament_core`
   calculates.
5. **Name mappings** — the builder attaches `name_to_id` to tournaments
   so assertions read by name.

## Future improvements

- More convenience methods on `TournamentBuilder`.
- Fixture generators for common tournament scenarios.
- Property-based testing for tiebreaks.
- Edge-case coverage: byes, forfeits, odd player counts.
