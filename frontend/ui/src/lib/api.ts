import "server-only";

import { createClient } from "@litour/api-client";
import { cookies } from "next/headers";

export type LitourClient = ReturnType<typeof createClient>;

export function serverApiBaseUrl(): string {
  const url = process.env["LITOUR_API_BASE_URL"];
  if (!url) {
    throw new Error("LITOUR_API_BASE_URL is not set");
  }
  return url;
}

// Forward the inbound request's Cookie header so FastAPI can resolve the
// Django session and answer permission flags. SSR runs in Node — cookies
// don't propagate automatically the way they do for browser fetches, so
// the page component must opt in by calling this from a Server Component
// (or any function that runs in the request scope).
export async function serverClient(): Promise<LitourClient> {
  const jar = await cookies();
  const cookieHeader = jar
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");
  return cookieHeader
    ? createClient(serverApiBaseUrl(), { headers: { cookie: cookieHeader } })
    : createClient(serverApiBaseUrl());
}
