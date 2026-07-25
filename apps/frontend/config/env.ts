/**
 * Centralized environment configuration. No module should read
 * `process.env` directly outside of this file.
 *
 * `NEXT_PUBLIC_*` values MUST be read via a static `process.env.NEXT_PUBLIC_X`
 * expression (not a dynamic/bracket lookup) — Next.js inlines them into the
 * browser bundle at build time via static analysis, so a dynamic lookup like
 * `process.env[name]` silently resolves to `undefined` on the client.
 */

function withFallback(value: string | undefined, fallback: string): string {
  return value && value.length > 0 ? value : fallback;
}

export const env = {
  apiBaseUrl: withFallback(process.env.NEXT_PUBLIC_API_BASE_URL, "http://localhost:8000"),
  appEnv: withFallback(process.env.NEXT_PUBLIC_APP_ENV, "development"),
} as const;
