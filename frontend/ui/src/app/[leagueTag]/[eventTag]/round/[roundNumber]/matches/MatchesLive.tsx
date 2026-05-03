"use client";

import { type WSMessage, type components, connectMatchStream } from "@litour/api-client";
import { useEffect, useState } from "react";

import { RoundsNav } from "@/components/event";
import {
  ConnectionBadge,
  type ConnectionState,
  LoneMatchesView,
  MatchesSummary,
  TeamMatchesView,
  ViewerBadge,
} from "@/components/matches";
import { ModeToggle } from "@/components/theme/ModeToggle";
import type { MatchFilter } from "@/lib/match-filter";

type RoundMatches = components["schemas"]["RoundMatchesDTO"];
type Match = components["schemas"]["MatchDTO"];
type TeamMatch = components["schemas"]["TeamMatchDTO"];

interface Props {
  initial: RoundMatches;
  apiBaseUrl: string;
}

export function MatchesLive({ initial, apiBaseUrl }: Props) {
  const [matches, setMatches] = useState<Match[]>(initial.matches);
  const [teamMatches, setTeamMatches] = useState<TeamMatch[]>(initial.team_matches);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [filter, setFilter] = useState<MatchFilter>("all");

  useEffect(() => {
    let didError = false;
    const stream = connectMatchStream(
      apiBaseUrl,
      initial.round_id,
      (msg: WSMessage) => {
        didError = false;
        setConnection("live");
        if (msg.type === "match.update") {
          setMatches((prev) => replaceById(prev, msg.match));
        } else if (msg.type === "team_match.update") {
          setTeamMatches((prev) => replaceById(prev, msg.team_match));
        }
      },
      (err: unknown) => {
        didError = true;
        setConnection("reconnecting");
        console.error("match stream error", err);
      },
    );
    const ready = window.setTimeout(() => {
      if (!didError) setConnection("live");
    }, 1500);
    return () => {
      window.clearTimeout(ready);
      stream.close();
    };
  }, [apiBaseUrl, initial.round_id]);

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <header className="mb-6 space-y-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              {initial.event_name} — Round {initial.round_number}
            </h1>
            <p className="text-muted-foreground text-sm">
              <span className="font-mono">
                {initial.league_tag}/{initial.event_tag}
              </span>
              {initial.is_completed ? " · completed" : " · in progress"}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <ViewerBadge viewer={initial.viewer} />
            <ConnectionBadge state={connection} />
            <ModeToggle />
          </div>
        </div>
        <RoundsNav
          rounds={initial.rounds}
          currentRoundNumber={initial.round_number}
          leagueTag={initial.league_tag}
          eventTag={initial.event_tag}
        />
        <MatchesSummary matches={matches} filter={filter} onFilterChange={setFilter} />
      </header>

      {initial.is_team ? (
        <TeamMatchesView
          teamMatches={teamMatches}
          matches={matches}
          eventSettings={initial.settings}
          filter={filter}
          viewer={initial.viewer}
          presenceEvents={initial.presence_events}
        />
      ) : (
        <LoneMatchesView
          matches={matches}
          eventSettings={initial.settings}
          filter={filter}
          viewer={initial.viewer}
          presenceEvents={initial.presence_events}
        />
      )}
    </main>
  );
}

function replaceById<T extends { id: number }>(prev: T[], next: T): T[] {
  let changed = false;
  const out = prev.map((item) => {
    if (item.id !== next.id) return item;
    changed = true;
    return next;
  });
  return changed ? out : prev;
}
