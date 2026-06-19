// Round-management domain logic components — the third UI layer
// (shadcn -> primitive -> domain logic -> page). Everything here knows
// about chess: matches, team matches, presence, pairings, results.
// Reusable visual building blocks live one level up in `primitives/`.
export { BoardRow } from "./BoardRow";
export { LoneMatchesView } from "./LoneMatchesView";
export { MatchesSummary } from "./MatchesSummary";
export { PlayerCell } from "./PlayerCell";
export { PlayerName } from "./PlayerName";
export { PresenceLogTrigger } from "./PresenceLogTrigger";
export { ResultCells } from "./ResultCells";
export { ResultPopover } from "./ResultPopover";
export { RoundsNav } from "./RoundsNav";
export { TeamMatchCard } from "./TeamMatchCard";
export { TeamMatchesView } from "./TeamMatchesView";
export { ViewerBadge } from "./ViewerBadge";
