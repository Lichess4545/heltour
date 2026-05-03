import type { BoardSide } from "@/lib/scores";

interface Props {
  side: BoardSide;
}

// Single score cell. Per the design choice to keep the win/loss/tie tints
// only on the Team Match header, this is a plain mono cell — the colour
// signal lives one level up so the table doesn't look like a heat map.
export function ScorePill({ side }: Props) {
  return (
    <span className="flex items-center justify-center font-mono text-sm tabular-nums">
      {side.display}
    </span>
  );
}
