// Browser-safe API helpers — no `next/headers` import, so this module can
// be imported from `"use client"` components without dragging in the
// server-only request scope.

export function publicApiBaseUrl(): string {
  const url = process.env["NEXT_PUBLIC_LITOUR_API_URL"];
  if (!url) {
    throw new Error("NEXT_PUBLIC_LITOUR_API_URL is not set");
  }
  return url;
}
