/**
 * Single source of truth for the backend URL used by the browser.
 *
 * Why this exists
 * ---------------
 * `NEXT_PUBLIC_*` values are inlined at BUILD time. The previous code read
 * `process.env.NEXT_PUBLIC_API_URL` in three places and each had its own
 * fallback, so a bundle built while a stale value was set kept calling that
 * port forever: the app was served by the backend on 8000 while the baked
 * constant still pointed at 8010, and every request came back
 * `net::ERR_CONNECTION_REFUSED`. Rebuilding fixed it once; nothing stopped it
 * from happening again.
 *
 * The rule
 * --------
 * When the backend serves this page, the API is on the SAME ORIGIN, so the
 * correct base is "" (relative URLs). That answer is derived from
 * `window.location` at RUNTIME, so it is correct on 8000, on any other port,
 * over a LAN IP, and behind a reverse proxy, with no rebuild.
 *
 * The only case that needs an absolute URL is the `next dev` server, which runs
 * on :3000 and is not the backend. That is detected by the port, and its target
 * is still `NEXT_PUBLIC_API_URL` so a developer can point dev at another host
 * without touching code. When neither applies we fall back to the same-origin
 * relative form, which is the safe default: a wrong host is unreachable, while
 * a wrong path can at least be served by the same backend that sent the page.
 */

const DEV_SERVER_PORTS = new Set(["3000", "3001"]);

/** Origin of the `next dev` server, used only when the page came from it. */
function devServerOrigin(): string | null {
  if (typeof window === "undefined") return null;
  if (!DEV_SERVER_PORTS.has(window.location.port)) return null;
  return `${window.location.protocol}//${window.location.hostname}:8000`;
}

/**
 * Base URL for API calls, without a trailing slash.
 *
 * Returns "" when the API is same-origin, which is the case for the built app
 * served by the backend. Callers can always concatenate: `${API}/health`.
 */
export function apiBase(): string {
  if (typeof window === "undefined") {
    // Server components / prerender: the API lives on the backend, which during
    // `next build` is the dev target. Empty keeps the export static.
    return process.env.NEXT_PUBLIC_API_URL ?? "";
  }
  return devServerOrigin() ?? process.env.NEXT_PUBLIC_API_URL ?? "";
}

/** Build a full API URL for `path` (which must start with "/"). */
export function apiUrl(path: string): string {
  return `${apiBase()}${path}`;
}
