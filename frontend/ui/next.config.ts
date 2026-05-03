import type { NextConfig } from "next";

// `frontend/ui/.env` is a symlink to the repo-root `.env` (created by
// devenv.nix `enterShell`), so Next.js's native loader picks up
// NEXT_PUBLIC_LITOUR_API_URL, LITOUR_API_BASE_URL, and LITOUR_UI_BASE_PATH
// without any per-package duplication.
const basePath = process.env["LITOUR_UI_BASE_PATH"];

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  basePath: basePath === undefined ? "/v2" : basePath,
  // Consume `@litour/api-client` from source, not a built `dist/`. This
  // collapses the dev-mode rebuild cascade (schema → generated.ts → dist
  // → Next) into a single file change, which Next's HMR handles cleanly.
  // `tsc` still works as a build script for any non-Next consumer.
  transpilePackages: ["@litour/api-client"],
};

export default nextConfig;
