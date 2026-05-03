export interface BoardSide {
  // Numeric points for the side. Used by `resultBg` to colour the cell
  // win/loss/tie. `null` means the result hasn't been entered yet.
  points: number | null;
  // Rendered text for the score cell. Carries the chess-notation suffix
  // for non-played games — "X" for forfeit win, "F" for forfeit loss,
  // "Z" for half-point bye — so the UI can distinguish a real 1-0 from a
  // 1X-0F walk-over.
  display: string;
}

const EMPTY: BoardSide = { points: null, display: "" };

export function parseBoardSides(result: string): [BoardSide, BoardSide] {
  if (!result) return [EMPTY, EMPTY];
  const r = result.trim();
  if (r === "1-0")
    return [
      { points: 1, display: "1" },
      { points: 0, display: "0" },
    ];
  if (r === "0-1")
    return [
      { points: 0, display: "0" },
      { points: 1, display: "1" },
    ];
  if (r === "1/2-1/2")
    return [
      { points: 0.5, display: "½" },
      { points: 0.5, display: "½" },
    ];
  if (r === "1X-0F" || r === "1X-0")
    return [
      { points: 1, display: "1X" },
      { points: 0, display: "0F" },
    ];
  if (r === "0F-1X" || r === "0-1X")
    return [
      { points: 0, display: "0F" },
      { points: 1, display: "1X" },
    ];
  if (r === "0F-0F")
    return [
      { points: 0, display: "0F" },
      { points: 0, display: "0F" },
    ];
  if (r === "1/2Z-1/2Z")
    return [
      { points: 0.5, display: "½Z" },
      { points: 0.5, display: "½Z" },
    ];
  return [EMPTY, EMPTY];
}

export function formatTeamScore(score: number): string {
  return Number.isInteger(score) ? String(score) : score.toFixed(1).replace(".5", "½");
}

// CSS-variable backed tints (see `app/globals.css`) so light/dark mode are
// theme-aware while staying pixel-identical to the legacy `_common.scss`
// palette in light mode.
export function resultBg(score: number | null, opp: number | null): string {
  if (score == null || opp == null) return "";
  if (score > opp) return "bg-result-win";
  if (score < opp) return "bg-result-loss";
  return "bg-result-tie";
}
