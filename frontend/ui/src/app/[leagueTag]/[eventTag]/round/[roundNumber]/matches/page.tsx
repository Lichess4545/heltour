import type { ReactNode } from "react";
import { z } from "zod";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { serverClient } from "@/lib/api";
import { publicApiBaseUrl } from "@/lib/api-public";

import { MatchesLive } from "./MatchesLive";

const slugSchema = z.string().min(1).max(64);
const roundNumberSchema = z.coerce.number().int().positive();

export default async function RoundMatchesPage({
  params,
}: {
  params: Promise<{ leagueTag: string; eventTag: string; roundNumber: string }>;
}) {
  const raw = await params;
  const league = slugSchema.safeParse(raw.leagueTag);
  const event = slugSchema.safeParse(raw.eventTag);
  const round = roundNumberSchema.safeParse(raw.roundNumber);

  if (!league.success || !event.success || !round.success) {
    return (
      <ErrorCard title="Invalid URL">
        Could not parse league / event / round from{" "}
        <code className="font-mono">
          /{raw.leagueTag}/{raw.eventTag}/round/{raw.roundNumber}/matches
        </code>
        .
      </ErrorCard>
    );
  }

  const client = await serverClient();
  const { data, error, response } = await client.GET(
    "/v1/leagues/{league_tag}/events/{event_tag}/rounds/{round_number}/matches",
    {
      params: {
        path: {
          league_tag: league.data,
          event_tag: event.data,
          round_number: round.data,
        },
      },
    },
  );

  if (error || !data) {
    return (
      <ErrorCard title={`Could not load round ${round.data}`}>
        API responded {response.status} {response.statusText}.
      </ErrorCard>
    );
  }

  return <MatchesLive initial={data} apiBaseUrl={publicApiBaseUrl()} />;
}

function ErrorCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <Card>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
        </CardHeader>
        <CardContent className="text-muted-foreground text-sm">{children}</CardContent>
      </Card>
    </main>
  );
}
