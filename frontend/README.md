# Litour frontend

Bun workspace containing all browser/Node JavaScript for Litour.

| Package | Path | Purpose |
| --- | --- | --- |
| `@litour/api-client` | `api-client/` | Typed FastAPI client + WebSocket helper. Generated from `openapi.json`. Bundled to an IIFE for the legacy Django pairings page. |
| `litour-ui` | `ui/` | Next.js 15 + shadcn UI. Mounted at `/v2/*` in production. |

## Install

```sh
cd frontend
bun install
```

## Common scripts

```sh
# Re-generate api-client types from openapi.json (run after API changes)
bun run --filter @litour/api-client generate

# Type-check + lint everything
bun run typecheck
bun run lint

# Run the Next.js dev server
bun run --filter litour-ui dev
```

The api-client publishes to two outputs:

- `dist/index.js` (ESM) — consumed by `litour-ui` via the workspace dep `"@litour/api-client": "workspace:*"`.
- `dist/litour-api-client.iife.js` — copied into `heltour/tournament/static/tournament/js/` during the Docker `base` build, loaded via `{% static %}` in the Django pairings template.
