import createOpenApiClient from "openapi-fetch";
import { WebSocket as ReconnectingWebSocket } from "partysocket";
import type { paths } from "./generated";
import { type WSMessage, wsMessage } from "./ws-messages";

export interface ClientInit {
  // Default headers applied to every request — used by the Next SSR layer
  // to forward Django's `sessionid` cookie, which FastAPI resolves into
  // permission flags on `RoundMatchesDTO.viewer`.
  headers?: HeadersInit;
}

export function createClient(baseUrl: string, init: ClientInit = {}) {
  return createOpenApiClient<paths>(
    init.headers === undefined ? { baseUrl } : { baseUrl, headers: init.headers },
  );
}

export interface MatchStream {
  close(): void;
}

export function connectMatchStream(
  baseUrl: string,
  roundId: number,
  onMessage: (msg: WSMessage) => void,
  onError?: (err: unknown) => void,
): MatchStream {
  const ws = new ReconnectingWebSocket(toWsUrl(baseUrl, `/ws/rounds/${roundId}/matches`), [], {
    minReconnectionDelay: 1000,
    maxReconnectionDelay: 30_000,
    reconnectionDelayGrowFactor: 2,
  });

  ws.addEventListener("message", (ev) => {
    try {
      const parsed = wsMessage.parse(JSON.parse(ev.data as string));
      onMessage(parsed);
    } catch (err) {
      onError?.(err);
    }
  });

  if (onError) {
    ws.addEventListener("error", onError);
  }

  return {
    close() {
      ws.close();
    },
  };
}

// Resolve a WebSocket URL from a baseUrl that may be absolute (`http(s)://host`)
// or path-relative (`/v2/api`). For path-relative, we resolve against the
// current page's origin so the connection rides the same TLS cert as the page.
function toWsUrl(baseUrl: string, path: string): string {
  if (/^https?:\/\//i.test(baseUrl)) {
    return baseUrl.replace(/^http/i, "ws") + path;
  }
  const wsOrigin = window.location.origin.replace(/^http/i, "ws");
  return `${wsOrigin}${baseUrl}${path}`;
}
