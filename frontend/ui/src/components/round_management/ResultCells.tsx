import type { components } from "@litour/api-client";
import { Swords } from "lucide-react";

import { ScorePill } from "@/components/primitives";
import type { BoardSide } from "@/lib/scores";

import { ResultPopover } from "./ResultPopover";

type Match = components["schemas"]["MatchDTO"];
type Viewer = components["schemas"]["ViewerDTO"];
type MatchPresence = components["schemas"]["MatchPresenceDTO"];

interface Props {
  match: Match;
  // Already oriented for the row — the side for the player on the left/
  // right of *this card*, not necessarily the chess white/black.
  leftSide: BoardSide;
  rightSide: BoardSide;
  viewer: Viewer;
  presence: MatchPresence | undefined;
}

// Two centre cells of a `BoardRow`, wrapped in a `ResultPopover` that
// shows the lichess game embed (and, for staff, an inline result form)
// on hover/click. The score cells themselves stay plain — the panel
// owns the interaction the legacy `<a href={game_link}>` provided, plus
// the staff edit affordance the legacy admin pencil link provided.
export function ResultCells({ match, leftSide, rightSide, viewer, presence }: Props) {
  const finished = leftSide.points != null && rightSide.points != null;
  const inProgress = !finished && Boolean(match.game_link);

  let inner: React.ReactNode;
  if (finished) {
    inner = (
      <>
        <ScorePill side={leftSide} />
        <ScorePill side={rightSide} />
      </>
    );
  } else if (inProgress) {
    inner = (
      <span className="text-muted-foreground col-span-2 flex items-center justify-center">
        <Swords className="size-4" />
      </span>
    );
  } else {
    inner = (
      <span className="text-muted-foreground col-span-2 flex items-center justify-center text-sm">
        —
      </span>
    );
  }

  return (
    <ResultPopover match={match} viewer={viewer} presence={presence}>
      {inner}
    </ResultPopover>
  );
}
