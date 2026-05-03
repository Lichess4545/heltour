import type { components } from "@litour/api-client";
import { useMemo } from "react";

import { type MatchFilter, matchMatchesFilter } from "@/lib/match-filter";

import { BoardRow } from "./BoardRow";

type Match = components["schemas"]["MatchDTO"];
type EventSettings = components["schemas"]["EventSettingsDTO"];
type Viewer = components["schemas"]["ViewerDTO"];
type MatchPresence = components["schemas"]["MatchPresenceDTO"];

const GRID =
  "grid-cols-[minmax(0,1fr)_2.5rem_2.5rem_minmax(0,1fr)] sm:grid-cols-[minmax(0,1fr)_3rem_3rem_minmax(0,1fr)]";

interface Props {
  matches: Match[];
  eventSettings: EventSettings;
  filter: MatchFilter;
  viewer: Viewer;
  presenceEvents: Record<string, MatchPresence>;
}

export function LoneMatchesView({ matches, eventSettings, filter, viewer, presenceEvents }: Props) {
  const sorted = useMemo(() => [...matches].sort((a, b) => a.id - b.id), [matches]);
  return (
    <div className="border-border overflow-hidden rounded-md border">
      <div className={`divide-border grid ${GRID} divide-y`}>
        {sorted.map((m) => (
          <BoardRow
            key={m.id}
            match={m}
            teamMode={false}
            eventSettings={eventSettings}
            viewer={viewer}
            presence={presenceEvents[String(m.id)]}
            collapsed={!matchMatchesFilter(m, filter)}
          />
        ))}
      </div>
    </div>
  );
}
