// Compatibility shim. Components have moved into per-domain folders:
//   - cross-domain primitives -> @/components/primitives
//   - round-specific logic    -> @/components/round_management
// New code should import from those locations directly.
export {
  CaptainBadge,
  ColorDot,
  ConnectionBadge,
  GenderBadge,
  ScorePill,
} from "@/components/primitives";
export type { ConnectionState } from "@/components/primitives";
export {
  BoardRow,
  LoneMatchesView,
  MatchesSummary,
  PlayerCell,
  PlayerName,
  PresenceLogTrigger,
  ResultCells,
  ResultPopover,
  TeamMatchCard,
  TeamMatchesView,
  ViewerBadge,
} from "@/components/round_management";
