import type { NextConfig } from "next";

// The app is a static export served by the backend itself, so the browser
// reaches the API on the same origin and needs no absolute URL at all
// (see src/app/api-client.ts). NEXT_PUBLIC_* values are inlined at build time,
// which is how a stale port ended up baked into the shipped bundle once: the
// build ran with NEXT_PUBLIC_API_URL set to a port the service no longer used,
// and every request came back ERR_CONNECTION_REFUSED until the next build.
//
// Fail the build instead of shipping that. The dev server still needs the
// variable, so the check only runs for a production export.
const bakedApiUrl = process.env.NEXT_PUBLIC_API_URL;
if (process.env.NODE_ENV === "production" && bakedApiUrl) {
  throw new Error(
    `Refusing to build: NEXT_PUBLIC_API_URL="${bakedApiUrl}" would be inlined ` +
      "into the bundle. The backend serves this page, so the API is same-origin " +
      "and no absolute URL is needed -- leaving the variable unset makes the " +
      "bundle follow whatever host serves it. Unset it and rebuild."
  );
}

const nextConfig: NextConfig = {
  output: "export",
  allowedDevOrigins: ["localhost", "127.0.0.1"],
};

export default nextConfig;
