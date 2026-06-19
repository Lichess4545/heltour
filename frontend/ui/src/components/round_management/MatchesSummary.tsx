import type { components } from "@litour/api-client";

import { Button } from "@/components/ui/button";
import type { MatchFilter } from "@/lib/match-filter";

type Match = components["schemas"]["MatchDTO"];

interface Props {
  matches: Match[];
  filter: MatchFilter;
  onFilterChange: (filter: MatchFilter) => void;
}

// Mirrors `_summarize_pairings` in heltour/tournament/views.py: a single
// finished/started/remaining tally derived purely from the matches array,
// so it stays in sync with WS updates without a separate endpoint. Each
// segment toggles a filter — clicking the active one resets to "all".
export function MatchesSummary({ matches, filter, onFilterChange }: Props) {
  let finished = 0;
  let started = 0;
  let remaining = 0;
  for (const m of matches) {
    if (m.result) finished += 1;
    else if (m.game_link) started += 1;
    else remaining += 1;
  }
  const total = matches.length;

  const toggle = (next: MatchFilter) => {
    onFilterChange(filter === next ? "all" : next);
  };

  return (
    <div className="text-muted-foreground flex flex-wrap items-center gap-x-1 text-sm">
      <Stat
        value={total}
        label="games"
        active={filter === "all"}
        onClick={() => onFilterChange("all")}
      />
      <Sep />
      <Stat
        value={started}
        label="in progress"
        active={filter === "started"}
        onClick={() => toggle("started")}
      />
      <Sep />
      <Stat
        value={finished}
        label="finished"
        active={filter === "finished"}
        onClick={() => toggle("finished")}
      />
      <Sep />
      <Stat
        value={remaining}
        label="unstarted"
        active={filter === "unstarted"}
        onClick={() => toggle("unstarted")}
      />
    </div>
  );
}

interface StatProps {
  value: number;
  label: string;
  active: boolean;
  onClick: () => void;
}

function Stat({ value, label, active, onClick }: StatProps) {
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={onClick}
      aria-pressed={active}
      className={`h-7 px-2 font-normal ${active ? "text-foreground bg-accent" : ""}`}
    >
      <span className="text-foreground font-semibold tabular-nums">{value}</span>
      <span className="ml-1">{label}</span>
    </Button>
  );
}

function Sep() {
  return (
    <span aria-hidden className="text-muted-foreground/50">
      ·
    </span>
  );
}
