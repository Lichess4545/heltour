import type { components } from "@litour/api-client";

type Match = components["schemas"]["MatchDTO"];

export type MatchFilter = "all" | "started" | "finished" | "unstarted";

export function matchMatchesFilter(m: Match, filter: MatchFilter): boolean {
  if (filter === "all") return true;
  if (filter === "finished") return Boolean(m.result);
  if (filter === "started") return !m.result && Boolean(m.game_link);
  return !m.result && !m.game_link;
}
