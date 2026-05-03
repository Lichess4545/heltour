"use client";

import type { components } from "@litour/api-client";
import { Activity } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { Button } from "@/components/ui/button";

type PlayerPresence = components["schemas"]["PlayerPresenceDTO"];

interface Props {
  presence: PlayerPresence;
  username: string;
  // Card alignment — the popover anchors against the trigger but is
  // portaled into the body, so the row's `overflow-hidden` doesn't clip
  // it. `side` decides whether the panel hangs off the trigger to the
  // right (default) or to the left (when triggered on the right side of
  // a row, where right-anchoring would push it off-screen).
  side: "left" | "right";
}

const PANEL_WIDTH_PX = 288; // w-72
// Conservative estimate used before the panel mounts so we can choose
// above vs below placement on the first frame; refined to the real
// `offsetHeight` immediately after mount.
const PANEL_HEIGHT_ESTIMATE = 240;

// Hover/focus opens the panel; tap on touch devices toggles. The panel
// keeps itself open while the pointer is on either the trigger or the
// panel — a small grace period on leave avoids closing when the cursor
// crosses the gap between them.
const CLOSE_DELAY_MS = 120;

export function PresenceLogTrigger({ presence, username, side }: Props) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeTimer = useRef<number | null>(null);
  // Online players get a saturated emerald to draw the eye; offline ones
  // are rendered as a low-opacity outline so the row still acknowledges
  // the staff surface but doesn't compete for attention.
  const tone = presence.was_online
    ? "text-emerald-600 dark:text-emerald-400"
    : "text-muted-foreground/40";

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

  return (
    <span className="inline-flex">
      <Button
        ref={triggerRef}
        variant="ghost"
        size="icon"
        className={`size-6 ${tone}`}
        title={`Presence log — ${username}`}
        aria-label={`Presence log for ${username}`}
        aria-expanded={open}
        onMouseEnter={show}
        onMouseLeave={scheduleClose}
        onFocus={show}
        onBlur={scheduleClose}
        onClick={show}
      >
        <Activity className="size-3.5" />
      </Button>
      {open ? (
        <PresencePortal
          triggerRef={triggerRef}
          presence={presence}
          username={username}
          side={side}
          onClose={() => setOpen(false)}
          onPanelEnter={show}
          onPanelLeave={scheduleClose}
        />
      ) : null}
    </span>
  );
}

interface PortalProps {
  triggerRef: React.RefObject<HTMLButtonElement | null>;
  presence: PlayerPresence;
  username: string;
  side: "left" | "right";
  onClose: () => void;
  onPanelEnter: () => void;
  onPanelLeave: () => void;
}

function PresencePortal({
  triggerRef,
  presence,
  username,
  side,
  onClose,
  onPanelEnter,
  onPanelLeave,
}: PortalProps) {
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // Compute panel position from trigger rect. Recomputed on open + on
  // viewport resize/scroll so the panel tracks the trigger when the page
  // moves underneath it. Picks above vs below based on which side of
  // the trigger has more room.
  useEffect(() => {
    function computePos() {
      const trigger = triggerRef.current;
      if (!trigger) return;
      const vh = document.documentElement.clientHeight;
      const rect = trigger.getBoundingClientRect();
      const panelHeight = panelRef.current?.offsetHeight ?? PANEL_HEIGHT_ESTIMATE;
      const spaceBelow = vh - rect.bottom;
      const spaceAbove = rect.top;
      const placeAbove = spaceBelow < panelHeight + 12 && spaceAbove > spaceBelow;
      const top = placeAbove
        ? Math.max(window.scrollY + 8, rect.top + window.scrollY - panelHeight - 4)
        : rect.bottom + window.scrollY + 4;
      const rawLeft = side === "right" ? rect.right - PANEL_WIDTH_PX : rect.left;
      // Clamp to viewport so the panel never escapes the screen edges.
      const maxLeft = window.scrollX + document.documentElement.clientWidth - PANEL_WIDTH_PX - 8;
      const minLeft = window.scrollX + 8;
      const left = Math.max(minLeft, Math.min(maxLeft, rawLeft + window.scrollX));
      setPos({ top, left });
    }
    computePos();
    window.addEventListener("scroll", computePos, true);
    window.addEventListener("resize", computePos);
    return () => {
      window.removeEventListener("scroll", computePos, true);
      window.removeEventListener("resize", computePos);
    };
  }, [triggerRef, side]);

  // After mount, re-position with the real panel height so a first-frame
  // estimate that put us below doesn't leave us clipping the viewport.
  useLayoutEffect(() => {
    const panel = panelRef.current;
    const trigger = triggerRef.current;
    if (!panel || !trigger || !pos) return;
    const vh = document.documentElement.clientHeight;
    const rect = trigger.getBoundingClientRect();
    const panelHeight = panel.offsetHeight;
    const spaceBelow = vh - rect.bottom;
    const spaceAbove = rect.top;
    const placeAbove = spaceBelow < panelHeight + 12 && spaceAbove > spaceBelow;
    const desiredTop = placeAbove
      ? Math.max(window.scrollY + 8, rect.top + window.scrollY - panelHeight - 4)
      : rect.bottom + window.scrollY + 4;
    if (Math.abs(desiredTop - pos.top) > 1) {
      setPos({ ...pos, top: desiredTop });
    }
  }, [pos, triggerRef]);

  // Outside-click + Escape close.
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

  if (pos == null) return null;
  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      ref={panelRef}
      role="dialog"
      aria-label={`Presence log for ${username}`}
      style={{ position: "absolute", top: pos.top, left: pos.left, width: PANEL_WIDTH_PX }}
      className="bg-popover text-popover-foreground z-50 rounded-md border p-3 text-xs shadow-md"
      onMouseEnter={onPanelEnter}
      onMouseLeave={onPanelLeave}
    >
      <div className="mb-2 border-b pb-2 text-sm">
        <strong>{username}</strong>
        <span className="text-muted-foreground">
          {" · "}
          {presence.was_online ? "online during round" : "not online"}
          {" · "}
          {presence.plies_played} plies
        </span>
      </div>
      {presence.events.length === 0 ? (
        <p className="text-muted-foreground">No events recorded.</p>
      ) : (
        <ul className="max-h-64 space-y-1 overflow-y-auto">
          {presence.events.map((ev, i) => (
            <li key={`${ev.timestamp}-${i}`} className="font-mono">
              <time dateTime={ev.timestamp} className="text-muted-foreground">
                {formatTimestamp(ev.timestamp)}
              </time>{" "}
              · {ev.event_type_display}
              {ev.game_id ? <span className="text-muted-foreground"> ({ev.game_id})</span> : null}
            </li>
          ))}
        </ul>
      )}
    </div>,
    document.body,
  );
}

function formatTimestamp(iso: string): string {
  // Trim to seconds, drop timezone, keep `YYYY-MM-DD HH:MM:SS` for parity
  // with the legacy popover. Inputs are ISO-8601 from the API.
  const t = iso.replace("T", " ");
  const dot = t.indexOf(".");
  const trimmed = dot === -1 ? t : t.slice(0, dot);
  return trimmed.replace(/[+-]\d{2}:?\d{2}$/, "").trim();
}
