import { Badge } from "@/components/ui/badge";

export type ConnectionState = "connecting" | "live" | "reconnecting";

export function ConnectionBadge({ state }: { state: ConnectionState }) {
  if (state === "live") {
    return <Badge variant="secondary">Live</Badge>;
  }
  if (state === "reconnecting") {
    return <Badge variant="destructive">Reconnecting…</Badge>;
  }
  return <Badge variant="outline">Connecting…</Badge>;
}
