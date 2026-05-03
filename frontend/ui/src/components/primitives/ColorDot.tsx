interface Props {
  color: "white" | "black";
  // Optional label rendered inside the dot. Used in team mode to put the
  // board number on both color markers — neat, symmetric, and removes the
  // need for a separate corner label.
  label?: string | number | undefined;
}

// Piece-color marker. Uses fixed light/dark colors rather than theme tokens
// so the white/black distinction stays correct in both light and dark mode
// (chess convention is "white pieces are always cream-light, black always
// dark", regardless of the surrounding theme).
export function ColorDot({ color, label }: Props) {
  const swatch =
    color === "white"
      ? "bg-white text-neutral-900 border-neutral-400"
      : "bg-neutral-900 text-white border-neutral-700";

  if (label != null && label !== "") {
    return (
      <span
        aria-label={`Board ${label}`}
        className={`inline-flex size-5 shrink-0 items-center justify-center rounded-full border font-mono text-[10px] leading-none font-semibold ${swatch}`}
      >
        {label}
      </span>
    );
  }

  return (
    <span aria-hidden className={`inline-block size-2.5 shrink-0 rounded-full border ${swatch}`} />
  );
}
