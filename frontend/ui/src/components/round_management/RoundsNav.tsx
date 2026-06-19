import type { components } from "@litour/api-client";
import { Check } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";

type EventRound = components["schemas"]["EventRoundDTO"];

interface Props {
  rounds: EventRound[];
  currentRoundNumber: number;
  leagueTag: string;
  eventTag: string;
}

// Horizontal round navigator for round-scoped Event pages.
//   - completed (past): linked, muted Badge, with a check
//   - current: bold border, no link (you're already on it)
//   - unpublished (future): faded, not interactive
// Pills wrap on narrow viewports rather than scrolling, so the whole season
// stays visible at a glance even on phones.
export function RoundsNav({ rounds, currentRoundNumber, leagueTag, eventTag }: Props) {
  return (
    <nav aria-label="Rounds" className="flex flex-wrap items-center gap-1.5">
      <span className="text-muted-foreground mr-1 text-xs uppercase tracking-wide">Rounds</span>
      {rounds.map((r) => (
        <RoundPill
          key={r.round_number}
          round={r}
          isCurrent={r.round_number === currentRoundNumber}
          leagueTag={leagueTag}
          eventTag={eventTag}
        />
      ))}
    </nav>
  );
}

const PILL_CLASS = "h-7 min-w-7 rounded-full font-mono tabular-nums";

function RoundPill({
  round,
  isCurrent,
  leagueTag,
  eventTag,
}: {
  round: EventRound;
  isCurrent: boolean;
  leagueTag: string;
  eventTag: string;
}) {
  const number = round.round_number;
  const completed = round.is_completed;
  const checkIcon = completed ? <Check aria-hidden /> : null;

  if (isCurrent) {
    return (
      <Badge
        aria-current="page"
        variant="outline"
        className={`${PILL_CLASS} border-primary bg-primary/10 text-foreground border-2 font-bold`}
      >
        {number}
        {checkIcon}
      </Badge>
    );
  }

  if (!round.is_published) {
    return (
      <Badge
        aria-disabled
        variant="outline"
        title="Pairings not yet published"
        className={`${PILL_CLASS} text-muted-foreground/50 border-border/40`}
      >
        {number}
      </Badge>
    );
  }

  return (
    <Link
      href={`/${leagueTag}/${eventTag}/round/${number}/matches`}
      aria-label={`Round ${number}${completed ? " (completed)" : ""}`}
    >
      <Badge variant="secondary" className={`${PILL_CLASS} hover:bg-secondary/80 cursor-pointer`}>
        {number}
        {checkIcon}
      </Badge>
    </Link>
  );
}
