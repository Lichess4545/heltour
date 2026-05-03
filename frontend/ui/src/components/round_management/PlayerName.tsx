import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";

interface Props {
  username: string | null;
  fideName: string | null;
  // League-level preference: when true and a `fideName` is available, render
  // FIDE name as the primary label and put the lichess handle on a second
  // line as a muted pill. When false (or no FIDE name) just the username.
  showFideNames: boolean;
  // Side determines stack alignment when both names are shown — left places
  // the pill under the FIDE name's start, right under its end. Also drives
  // text-align on the wrapper so the names mirror the card.
  align?: "start" | "end";
  // Inline node rendered next to the primary name on the same line (rating,
  // gender badge, etc.). Layout owner controls what goes here so PlayerName
  // doesn't have to know about all the surrounding metadata.
  trailing?: ReactNode;
}

// Reusable player label with one source of truth for league-aware display.
//
// Layout when FIDE info is shown:
//   <a>FIDE Name</a> <trailing>
//   <a>[pill: lichess_user]</a>
// Otherwise:
//   <a>lichess_user</a> <trailing>
//
// `trailing` is rendered *outside* the lichess anchor so interactive
// children (presence-log button, etc.) keep their own click semantics.
export function PlayerName({
  username,
  fideName,
  showFideNames,
  align = "start",
  trailing,
}: Props) {
  if (!username) {
    return <span className="text-muted-foreground">—</span>;
  }

  const wrapperAlign = align === "end" ? "items-end text-right" : "items-start";
  const inlineJustify = align === "end" ? "justify-end" : "";
  const lichessHref = `https://lichess.org/@/${username}`;

  if (showFideNames && fideName) {
    return (
      <span className={`flex min-w-0 flex-col gap-0.5 ${wrapperAlign}`}>
        <span
          className={`flex flex-wrap items-center gap-x-1.5 gap-y-0 [overflow-wrap:anywhere] ${inlineJustify}`}
        >
          <a
            href={lichessHref}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-primary font-medium hover:underline"
          >
            {fideName}
          </a>
          {trailing}
        </span>
        <a
          href={lichessHref}
          target="_blank"
          rel="noopener noreferrer"
          className="hover:opacity-80"
        >
          <UsernamePill username={username} />
        </a>
      </span>
    );
  }

  return (
    <span className={`flex flex-wrap items-center gap-x-1.5 gap-y-0 ${inlineJustify}`}>
      <a
        href={lichessHref}
        target="_blank"
        rel="noopener noreferrer"
        className="hover:text-primary font-medium hover:underline [overflow-wrap:anywhere]"
      >
        {username}
      </a>
      {trailing}
    </span>
  );
}

function UsernamePill({ username }: { username: string }) {
  return (
    <Badge
      variant="secondary"
      className="px-1.5 font-mono text-[10px] leading-none whitespace-normal [overflow-wrap:anywhere]"
    >
      {username}
    </Badge>
  );
}
