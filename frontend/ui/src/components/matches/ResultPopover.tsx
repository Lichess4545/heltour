"use client";

import { type components, createClient } from "@litour/api-client";
import { Activity, ExternalLink } from "lucide-react";
import { type ReactNode, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { publicApiBaseUrl } from "@/lib/api-public";
import { lichessEmbedUrl } from "@/lib/lichess";

type Match = components["schemas"]["MatchDTO"];
type Viewer = components["schemas"]["ViewerDTO"];
type MatchPresence = components["schemas"]["MatchPresenceDTO"];
type PlayerPresence = components["schemas"]["PlayerPresenceDTO"];

interface Props {
  match: Match;
  viewer: Viewer;
  presence: MatchPresence | undefined;
  children: ReactNode;
}

// Wide panel sizes the board + moves side-by-side; mobile clamps to
// viewport so the same iframe folds the move list beneath the board.
const PANEL_DESKTOP_WIDTH = 720;
const IFRAME_HEIGHT = 460;
const CLOSE_DELAY_MS = 150;
// Initial estimate for placement before the panel has rendered and we
// can read its real height. Tuned to roughly cover header + iframe +
// presence row + form. Refined post-mount via `panelRef.offsetHeight`.
const PANEL_HEIGHT_ESTIMATE = 700;

// Wraps the score cells with a hover/click trigger. The panel is portaled
// into the body so card `overflow-hidden` doesn't clip it; it carries the
// lichess game embed, both players' presence summaries, and (for staff)
// an inline result form. Without a game link AND without edit perms
// there's nothing useful to show, so we render the children as a plain
// element instead of a trigger — the row stays inert.
export function ResultPopover({ match, viewer, presence, children }: Props) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeTimer = useRef<number | null>(null);
  const [open, setOpen] = useState(false);

  const hasContent = Boolean(match.game_link) || viewer.can_edit_pairings;

  function show() {
    if (closeTimer.current != null) {
      window.clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
    setOpen(true);
  }
  function scheduleClose() {
    if (closeTimer.current != null) window.clearTimeout(closeTimer.current);
    closeTimer.current = window.setTimeout(() => setOpen(false), CLOSE_DELAY_MS);
  }

  if (!hasContent) {
    return <span className="col-span-2 grid grid-cols-subgrid items-stretch">{children}</span>;
  }

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="hover:bg-accent/40 col-span-2 grid grid-cols-subgrid items-stretch outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
        aria-haspopup="dialog"
        aria-expanded={open}
        onMouseEnter={show}
        onMouseLeave={scheduleClose}
        onFocus={show}
        onBlur={scheduleClose}
        onClick={show}
      >
        {children}
      </button>
      {open ? (
        <ResultPanel
          triggerRef={triggerRef}
          match={match}
          viewer={viewer}
          presence={presence}
          onPanelEnter={show}
          onPanelLeave={scheduleClose}
          onClose={() => setOpen(false)}
        />
      ) : null}
    </>
  );
}

interface PanelProps {
  triggerRef: React.RefObject<HTMLButtonElement | null>;
  match: Match;
  viewer: Viewer;
  presence: MatchPresence | undefined;
  onClose: () => void;
  onPanelEnter: () => void;
  onPanelLeave: () => void;
}

function ResultPanel({
  triggerRef,
  match,
  viewer,
  presence,
  onClose,
  onPanelEnter,
  onPanelLeave,
}: PanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [layout, setLayout] = useState<{
    top: number;
    left: number;
    width: number;
  } | null>(null);

  useEffect(() => {
    function compute() {
      const trigger = triggerRef.current;
      if (!trigger) return;
      const vw = document.documentElement.clientWidth;
      const vh = document.documentElement.clientHeight;
      const width = Math.min(PANEL_DESKTOP_WIDTH, vw - 16);
      const rect = trigger.getBoundingClientRect();
      // Prefer the measured panel height once it's mounted; before that,
      // use the estimate so the first frame doesn't flash in the wrong
      // place when the trigger is near the bottom of the viewport.
      const panelHeight = panelRef.current?.offsetHeight ?? PANEL_HEIGHT_ESTIMATE;
      const spaceBelow = vh - rect.bottom;
      const spaceAbove = rect.top;
      const placeAbove = spaceBelow < panelHeight + 12 && spaceAbove > spaceBelow;

      const top = placeAbove
        ? Math.max(window.scrollY + 8, rect.top + window.scrollY - panelHeight - 4)
        : rect.bottom + window.scrollY + 4;
      const center = rect.left + rect.width / 2 + window.scrollX;
      const rawLeft = center - width / 2;
      const maxLeft = window.scrollX + vw - width - 8;
      const minLeft = window.scrollX + 8;
      const left = Math.max(minLeft, Math.min(maxLeft, rawLeft));
      setLayout({ top, left, width });
    }
    compute();
    window.addEventListener("scroll", compute, true);
    window.addEventListener("resize", compute);
    return () => {
      window.removeEventListener("scroll", compute, true);
      window.removeEventListener("resize", compute);
    };
  }, [triggerRef]);

  // Re-run positioning once the panel has actually rendered so we can
  // read its true height — needed when the iframe height makes the
  // estimate wrong, or when above/below should swap based on the real
  // panel size.
  useLayoutEffect(() => {
    const panel = panelRef.current;
    const trigger = triggerRef.current;
    if (!panel || !trigger || !layout) return;
    const vh = document.documentElement.clientHeight;
    const rect = trigger.getBoundingClientRect();
    const panelHeight = panel.offsetHeight;
    const spaceBelow = vh - rect.bottom;
    const spaceAbove = rect.top;
    const placeAbove = spaceBelow < panelHeight + 12 && spaceAbove > spaceBelow;
    const desiredTop = placeAbove
      ? Math.max(window.scrollY + 8, rect.top + window.scrollY - panelHeight - 4)
      : rect.bottom + window.scrollY + 4;
    if (Math.abs(desiredTop - layout.top) > 1) {
      setLayout({ ...layout, top: desiredTop });
    }
  }, [layout, triggerRef]);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      const target = e.target as Node;
      if (panelRef.current?.contains(target)) return;
      if (triggerRef.current?.contains(target)) return;
      onClose();
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose, triggerRef]);

  if (layout == null) return null;
  if (typeof document === "undefined") return null;

  const embedUrl = lichessEmbedUrl(match.game_link);
  const showPresence =
    viewer.can_view_presence_log &&
    presence != null &&
    (presence.white != null || presence.black != null);

  return createPortal(
    <div
      ref={panelRef}
      role="dialog"
      aria-label="Game"
      style={{
        position: "absolute",
        top: layout.top,
        left: layout.left,
        width: layout.width,
      }}
      className="bg-popover text-popover-foreground z-50 overflow-hidden rounded-md border shadow-md"
      onMouseEnter={onPanelEnter}
      onMouseLeave={onPanelLeave}
    >
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2 text-xs">
        <span className="text-muted-foreground">
          {match.white_username ?? "—"} vs {match.black_username ?? "—"}
        </span>
        {match.game_link ? (
          <a
            href={match.game_link}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-foreground text-muted-foreground inline-flex items-center gap-1"
            title="Open on lichess.org"
          >
            lichess <ExternalLink className="size-3" />
          </a>
        ) : null}
      </div>
      {embedUrl ? (
        <iframe
          src={embedUrl}
          title="Lichess game"
          width={layout.width}
          height={IFRAME_HEIGHT}
          className="block w-full"
          allow="fullscreen"
        />
      ) : (
        <p className="text-muted-foreground px-3 py-6 text-center text-xs italic">
          No game scheduled.
        </p>
      )}
      {showPresence ? (
        <PresenceSection
          whiteUsername={match.white_username}
          blackUsername={match.black_username}
          white={presence.white}
          black={presence.black}
        />
      ) : null}
      {viewer.can_edit_pairings ? (
        <ResultEditor
          matchId={match.id}
          initialResult={match.result}
          whiteUsername={match.white_username}
          blackUsername={match.black_username}
          presence={presence}
        />
      ) : null}
    </div>,
    document.body,
  );
}

interface PresenceSectionProps {
  whiteUsername: string | null;
  blackUsername: string | null;
  white: PlayerPresence | null;
  black: PlayerPresence | null;
}

// Two-column presence summary inside the result panel. Keeps the
// dedicated per-player activity icons in the row functional (quick peek
// at one side) while consolidating both sides plus the event lists in
// the same panel as the game.
function PresenceSection({ whiteUsername, blackUsername, white, black }: PresenceSectionProps) {
  return (
    <div className="grid grid-cols-1 gap-px border-t bg-border sm:grid-cols-2">
      <PresenceColumn username={whiteUsername} side="White" presence={white} />
      <PresenceColumn username={blackUsername} side="Black" presence={black} />
    </div>
  );
}

interface PresenceColumnProps {
  username: string | null;
  side: "White" | "Black";
  presence: PlayerPresence | null;
}

function PresenceColumn({ username, side, presence }: PresenceColumnProps) {
  if (presence == null || username == null) {
    return (
      <div className="bg-popover text-muted-foreground px-3 py-2 text-xs italic">
        {side}: no player
      </div>
    );
  }
  const tone = presence.was_online
    ? "text-emerald-600 dark:text-emerald-400"
    : "text-muted-foreground/60";
  return (
    <div className="bg-popover px-3 py-2 text-xs">
      <div className="mb-1.5 flex items-center gap-1.5">
        <Activity className={`size-3.5 ${tone}`} />
        <span className="text-muted-foreground">{side}:</span>
        <strong>{username}</strong>
        <span className="text-muted-foreground ml-auto">{presence.plies_played} plies</span>
      </div>
      {presence.events.length === 0 ? (
        <p className="text-muted-foreground italic">No events recorded.</p>
      ) : (
        <ul className="max-h-40 space-y-0.5 overflow-y-auto font-mono">
          {presence.events.map((ev, i) => (
            <li key={`${ev.timestamp}-${i}`}>
              <time dateTime={ev.timestamp} className="text-muted-foreground">
                {formatTimestamp(ev.timestamp)}
              </time>{" "}
              · {ev.event_type_display}
              {ev.game_id ? <span className="text-muted-foreground"> ({ev.game_id})</span> : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function formatTimestamp(iso: string): string {
  const t = iso.replace("T", " ");
  const dot = t.indexOf(".");
  const trimmed = dot === -1 ? t : t.slice(0, dot);
  return trimmed.replace(/[+-]\d{2}:?\d{2}$/, "").trim();
}

// FastAPI `HTTPException(detail=...)` serialises as `{ "detail": "..." }`;
// runtime-narrow rather than casting so we don't blindly trust the wire shape.
const apiErrorShape = z.object({ detail: z.string() });

const RESULT_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "", label: "— unset —" },
  { value: "1-0", label: "1-0  (white wins)" },
  { value: "0-1", label: "0-1  (black wins)" },
  { value: "1/2-1/2", label: "½-½  (draw)" },
  { value: "1X-0F", label: "1X-0F  (white wins by forfeit)" },
  { value: "0F-1X", label: "0F-1X  (black wins by forfeit)" },
  { value: "0F-0F", label: "0F-0F  (double forfeit)" },
  { value: "1/2Z-1/2Z", label: "½Z-½Z  (half-point bye both)" },
];

interface EditorProps {
  matchId: number;
  initialResult: string;
  whiteUsername: string | null;
  blackUsername: string | null;
  presence: MatchPresence | undefined;
}

interface ForfeitSuggestion {
  result: string;
  winner: string;
  loser: string;
}

// "Activity" here is the broad presence signal — anything that says the
// player engaged with the game: showed up online, played any plies, or
// even a chat-message event. If exactly one side has that and the other
// has nothing, the no-show side is the natural forfeit candidate.
function detectForfeit(
  whiteUsername: string | null,
  blackUsername: string | null,
  presence: MatchPresence | undefined,
): ForfeitSuggestion | null {
  const white = presence?.white;
  const black = presence?.black;
  if (!white || !black || !whiteUsername || !blackUsername) return null;
  const whiteActive = white.was_online || white.plies_played > 0 || white.events.length > 0;
  const blackActive = black.was_online || black.plies_played > 0 || black.events.length > 0;
  if (whiteActive && !blackActive) {
    return { result: "1X-0F", winner: whiteUsername, loser: blackUsername };
  }
  if (blackActive && !whiteActive) {
    return { result: "0F-1X", winner: blackUsername, loser: whiteUsername };
  }
  return null;
}

function ResultEditor({
  matchId,
  initialResult,
  whiteUsername,
  blackUsername,
  presence,
}: EditorProps) {
  const [value, setValue] = useState(initialResult);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  // Re-sync the dropdown when the row updates from a WS event (e.g. a
  // sibling tab sets the result). The popover stays open in the meantime
  // so the user can correct without losing context.
  useEffect(() => {
    setValue(initialResult);
  }, [initialResult]);

  async function saveResult(target: string) {
    setSaving(true);
    setError(null);
    try {
      const client = createClient(publicApiBaseUrl());
      const { error: apiError } = await client.PUT("/v1/matches/{match_id}/result", {
        params: { path: { match_id: matchId } },
        body: { result: target },
      });
      if (apiError) {
        const parsed = apiErrorShape.safeParse(apiError);
        setError(parsed.success ? parsed.data.detail : "save failed");
        return;
      }
      setValue(target);
      setSavedAt(Date.now());
    } catch (err) {
      setError(err instanceof Error ? err.message : "save failed");
    } finally {
      setSaving(false);
    }
  }

  const dirty = value !== initialResult;
  const showSaved = savedAt != null && Date.now() - savedAt < 3000;
  const forfeit = detectForfeit(whiteUsername, blackUsername, presence);
  const forfeitAlreadySet = forfeit != null && initialResult === forfeit.result;

  return (
    <div className="border-t bg-muted/40">
      {forfeit && !forfeitAlreadySet ? (
        <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2 text-xs">
          <span className="text-muted-foreground">
            Only <strong>{forfeit.winner}</strong> showed up.
          </span>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={saving}
            onClick={() => void saveResult(forfeit.result)}
            className="h-7"
            title={`Set result to ${forfeit.result}`}
          >
            Forfeit win: {forfeit.winner}
          </Button>
        </div>
      ) : null}
      <form
        className="flex items-center gap-2 px-3 py-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (!saving && dirty) void saveResult(value);
        }}
      >
        <label className="sr-only" htmlFor={`result-${matchId}`}>
          Result
        </label>
        <select
          id={`result-${matchId}`}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={saving}
          className="border-input bg-background ring-offset-background focus-visible:ring-ring h-8 flex-1 rounded-md border px-2 py-1 text-xs focus-visible:ring-2 focus-visible:ring-offset-1 disabled:opacity-50"
        >
          {RESULT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <Button type="submit" size="sm" disabled={!dirty || saving} className="h-8">
          {saving ? "Saving…" : "Save"}
        </Button>
        {error ? (
          <span className="text-destructive text-xs" role="alert">
            {error}
          </span>
        ) : showSaved ? (
          <span className="text-emerald-600 text-xs dark:text-emerald-400">Saved</span>
        ) : null}
      </form>
    </div>
  );
}
