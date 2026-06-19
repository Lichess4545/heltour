export default function HomePage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-3xl font-semibold tracking-tight">Litour UI</h1>
      <p className="mt-4 text-muted-foreground">
        Next-gen Litour interface. Pages live under <code className="font-mono">/v2/*</code>.
      </p>
      <p className="mt-2 text-muted-foreground text-sm">
        Round-matches URL pattern:{" "}
        <code className="font-mono">
          /v2/&lt;leagueTag&gt;/&lt;eventTag&gt;/round/&lt;n&gt;/matches
        </code>
        .
      </p>
    </main>
  );
}
