# Chess Competition Glossary

## Hierarchy

- **League** _(optional)_ — the persistent identity for a recurring competition. Has many Seasons over time. Holds cross-Season concerns: standings history, rule continuity, captain pools, promotion/relegation between tiers. One-off competitions skip this level.
- **Event** — the named, bounded competition. Called a _Season_ when it belongs to a League. Has a start date, end date, prize fund, and a winner.
- **Stage** — a sequential phase within an Event with a specific purpose. Stages run in order; Stage N must finish before Stage N+1 begins. Typical purposes: Qualifier, Playoff, Final.
- **Section** — a parallel division within a Stage. Players in different Sections of the same Stage do not face each other. Each Section runs one format (Swiss, Round-Robin, Knockout). Sections may be categorical (Open, Women's, U1800), regional (Americas, Europe), or capacity-driven (Pool A, Pool B) — all are just Sections, distinguished by naming.
- **Round** — a unit of progression within a Section.
- **Match** — a head-to-head encounter in a Round between two participants. A _Player Match_ is between two players; a _Team Match_ is between two teams.
- **Player Match** _(only inside a Team Match)_ — the board-vs-board encounter that is one component of a Team Match. Resolves to a 1 / ½ / 0 score that contributes to the Team Match result.
- **Game** — one game of chess. Atomic.

## Match composition

- **Regular Games** — the scheduled Games of the Match.
- **Tiebreak Games** — additional Games appended to a Match when Regular Games leave it tied. Typically faster time controls, often in a defined sequence (e.g., two rapid, then two blitz).
- **Armageddon Game** — a single Game with asymmetric draw odds, used as a final tiebreaker when Tiebreak Games remain inconclusive. It is a Game, not a Match.

## Stage transitions

- **Standings** — the ordered result of a Section at the end of its Stage. The published, ranked list with scores and tiebreaks applied. Every Section produces Standings.
- **Tiebreak Rule** — the rule used to order tied participants in Standings (Buchholz, Sonneborn-Berger, head-to-head, etc.). Distinct from Tiebreak Games, which resolve a tied Match.
- **Cut** — the rule that determines which participants in the Standings advance to the next Stage. Examples: "top 8 per Section," "score ≥ 5/9," "all undefeated."
- **Advancement** — the set of participants who passed the Cut and proceed to the next Stage.
- **Seeding** — the rule that places advancing participants into positions in the next Stage (bracket positions, starting pairings, group assignments).
- **Carryover** _(optional)_ — points or results brought forward from the previous Stage into the next. Distinct from Seeding.

## Terms to avoid or use carefully

- **Tournament** — too overloaded; prefer Event, Stage, or Section depending on meaning.
- **Qualifier** — use as an adjective on Stage or Section, not as a standalone noun.
- **Qualification** — collides with "Qualifier Stage"; prefer Cut for the rule, Advancement for the result.
- **Promotion** — reserve for cross-Season tier movement at the League level; use Advancement for within-Event Stage transitions.
- **Group** — absorbed into Section; not a separate level.
- **Tiebreak** — always qualify: _Tiebreak Game_ (Match-level) vs _Tiebreak Rule_ (Standings-level).
- **Match** with one Game — still a Match. Don't collapse the term.
- **Armageddon Match** — incorrect; it is an Armageddon Game within a Match.
