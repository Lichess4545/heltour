// Browser entry point: bundled to an IIFE that assigns these exports to
// `window.LitourApi`. Used by Django templates via a {% static %} <script> tag.
export { createClient, connectMatchStream } from "./client";
export type { MatchStream } from "./client";
export { wsMessage } from "./ws-messages";
export type {
  WSMessage,
  WSMatchUpdate,
  WSTeamMatchUpdate,
  WSPing,
} from "./ws-messages";
