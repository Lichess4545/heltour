import type { components } from "@litour/api-client";

import type { BoardSide } from "@/lib/scores";
import { parseBoardSides } from "@/lib/scores";

import { PlayerCell } from "./PlayerCell";
import { ResultCells } from "./ResultCells";

type Match = components["schemas"]["MatchDTO"];
type EventSettings = components["schemas"]["EventSettingsDTO"];
type Viewer = components["schemas"]["ViewerDTO"];
type MatchPresence = components["schemas"]["MatchPresenceDTO"];
type PlayerPresence = components["schemas"]["PlayerPresenceDTO"];

interface Props {
  match: Match;
  // True for team mode (alternating piece colors by board, board# label).
  // False for lone (no flipping, no board label).
  teamMode: boolean;
  eventSettings: EventSettings;
  viewer: Viewer;
  presence: MatchPresence | undefined;
  // When true, the row keeps its slot in the layout but collapses to a
  // thin sliver — content hidden, height reduced. Used by the summary
  // filter so the table stays the same length and rows just contract.
  collapsed?: boolean;
}

// Renders into a 4-col subgrid:
//   [left player | left score | right score | right player]
// Symmetric — board number, when relevant, lives as a small corner label
// outside the grid columns rather than a leading column that breaks symmetry.
export function BoardRow({
  match,
  teamMode,
  eventSettings,
  viewer,
  presence,
  collapsed = false,
}: Props) {
  const oriented = orientForCard(match, teamMode, presence);

  // Team mode: put the board number inside both color markers (so each
  // side of the row visibly carries the board) instead of a separate
  // corner label.
  const boardLabel = teamMode ? match.board_number : null;

  if (collapsed) {
    return <div aria-hidden className="bg-muted/30 col-span-full h-1" />;
  }

  return (
    <div className="col-span-full grid min-h-14 grid-cols-subgrid items-stretch text-sm">
      <PlayerCell
        username={oriented.left.username}
        fideName={oriented.left.fideName}
        rating={oriented.left.rating}
        gender={oriented.left.gender}
        isCaptain={oriented.left.isCaptain}
        pieceColor={oriented.left.pieceColor}
        boardLabel={boardLabel}
        side="left"
        eventSettings={eventSettings}
        presence={viewer.can_view_presence_log ? oriented.left.presence : null}
      />
      <ResultCells
        match={match}
        leftSide={oriented.left.score}
        rightSide={oriented.right.score}
        viewer={viewer}
        presence={presence}
      />
      <PlayerCell
        username={oriented.right.username}
        fideName={oriented.right.fideName}
        rating={oriented.right.rating}
        gender={oriented.right.gender}
        isCaptain={oriented.right.isCaptain}
        pieceColor={oriented.right.pieceColor}
        boardLabel={boardLabel}
        side="right"
        eventSettings={eventSettings}
        presence={viewer.can_view_presence_log ? oriented.right.presence : null}
      />
    </div>
  );
}

interface OrientedSide {
  username: string | null;
  fideName: string | null;
  rating: number | null;
  gender: string | null;
  isCaptain: boolean;
  pieceColor: "white" | "black";
  score: BoardSide;
  presence: PlayerPresence | null;
}

function orientForCard(
  match: Match,
  teamMode: boolean,
  presence: MatchPresence | undefined,
): { left: OrientedSide; right: OrientedSide } {
  const [whitePieceSide, blackPieceSide] = parseBoardSides(match.result);
  const board = match.board_number ?? 1;
  const whitePresence = presence?.white ?? null;
  const blackPresence = presence?.black ?? null;
  // Lone tournaments: no flipping — left = white pieces, right = black pieces.
  // Team tournaments: on even boards the white-team player holds black
  // pieces (and vice versa), so we swap which `MatchDTO` field feeds the
  // left side of the card.
  const leftHasWhitePieces = !teamMode || board % 2 === 1;
  if (leftHasWhitePieces) {
    return {
      left: {
        username: match.white_username,
        fideName: match.white_fide_name,
        rating: match.white_rating,
        gender: match.white_gender,
        isCaptain: match.white_is_captain,
        pieceColor: "white",
        score: whitePieceSide,
        presence: whitePresence,
      },
      right: {
        username: match.black_username,
        fideName: match.black_fide_name,
        rating: match.black_rating,
        gender: match.black_gender,
        isCaptain: match.black_is_captain,
        pieceColor: "black",
        score: blackPieceSide,
        presence: blackPresence,
      },
    };
  }
  return {
    left: {
      username: match.black_username,
      fideName: match.black_fide_name,
      rating: match.black_rating,
      gender: match.black_gender,
      isCaptain: match.black_is_captain,
      pieceColor: "black",
      score: blackPieceSide,
      presence: blackPresence,
    },
    right: {
      username: match.white_username,
      fideName: match.white_fide_name,
      rating: match.white_rating,
      gender: match.white_gender,
      isCaptain: match.white_is_captain,
      pieceColor: "white",
      score: whitePieceSide,
      presence: whitePresence,
    },
  };
}
