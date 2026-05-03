import type { components } from "@litour/api-client";

import { CaptainBadge, ColorDot, GenderBadge } from "@/components/primitives";

import { PlayerName } from "./PlayerName";
import { PresenceLogTrigger } from "./PresenceLogTrigger";

type EventSettings = components["schemas"]["EventSettingsDTO"];
type PlayerPresence = components["schemas"]["PlayerPresenceDTO"];

interface Props {
  username: string | null;
  fideName: string | null;
  rating: number | null;
  gender: string | null;
  isCaptain: boolean;
  side: "left" | "right";
  pieceColor: "white" | "black";
  // When provided, the dot becomes a labeled marker (team mode shows the
  // board number inside). Omit for lone tournaments — small unlabeled dot.
  boardLabel?: number | null;
  eventSettings: EventSettings;
  presence?: PlayerPresence | null;
}

// Layout responsibility chart:
//
//   sm+ (desktop):
//     left  : [ColorDot] PlayerName ............. [presence]
//     right : [presence] ............. PlayerName [ColorDot]
//   < sm (mobile, stacked column):
//     left  : ColorDot PlayerName
//             ........................ [presence]
//     right : .......... PlayerName ColorDot
//             [presence] ........................
//
// The presence trigger sits at the *inner* edge (next to the score
// column), with the cell's inner padding removed so it hugs the result.
// On mobile it drops below the player so the names/ratings get the
// whole row to themselves. The edit pencil lives in a separate trailing
// gutter column outside this cell so symmetry is preserved.
export function PlayerCell({
  username,
  fideName,
  rating,
  gender,
  isCaptain,
  side,
  pieceColor,
  boardLabel,
  eventSettings,
  presence,
}: Props) {
  const dotLabel = boardLabel != null ? boardLabel : undefined;
  const trailing = (
    <>
      <GenderBadge gender={gender} />
      <CaptainBadge isCaptain={isCaptain} />
      {rating != null ? (
        <span className="text-muted-foreground font-mono text-xs">({rating})</span>
      ) : null}
    </>
  );
  const presenceTrigger =
    presence && username ? (
      <PresenceLogTrigger presence={presence} username={username} side={side} />
    ) : null;

  if (side === "left") {
    return (
      <div className="flex flex-col gap-1 px-2 py-2 sm:flex-row sm:items-center sm:gap-2 sm:px-3 sm:py-2.5 sm:pr-0">
        <div className="flex items-center gap-1.5 sm:gap-2">
          <ColorDot color={pieceColor} label={dotLabel} />
          <PlayerName
            username={username}
            fideName={fideName}
            showFideNames={eventSettings.use_fide_information}
            align="start"
            trailing={trailing}
          />
        </div>
        {presenceTrigger ? (
          <span className="self-end sm:ml-auto sm:self-auto">{presenceTrigger}</span>
        ) : null}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1 px-2 py-2 sm:flex-row sm:items-center sm:justify-end sm:gap-2 sm:px-3 sm:py-2.5 sm:pl-0">
      <div className="flex items-center justify-end gap-1.5 sm:gap-2">
        <PlayerName
          username={username}
          fideName={fideName}
          showFideNames={eventSettings.use_fide_information}
          align="end"
          trailing={trailing}
        />
        <ColorDot color={pieceColor} label={dotLabel} />
      </div>
      {presenceTrigger ? (
        <span className="self-start sm:order-first sm:mr-auto sm:self-auto">{presenceTrigger}</span>
      ) : null}
    </div>
  );
}
