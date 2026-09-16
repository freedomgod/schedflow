/**
 * Session-expiry plumbing shared by the API client, the router and the login
 * page.
 *
 * Kept dependency-free on purpose: `api/client.ts` must not import the auth
 * store (that would create an import cycle through `api/auth.ts`), so the
 * interceptor only reports "the session is gone" here and `main.ts` wires the
 * actual cleanup and navigation.
 */

/** Routes that already handle an unauthenticated visitor. */
const PUBLIC_PATHS = ['/login', '/init-setup']

export const DEFAULT_REDIRECT = '/dashboard'

export type SessionExpiredHandler = (redirect: string) => void

let handler: SessionExpiredHandler | null = null
let expired = false
let pendingRedirect: string | null = null

/** Register the single handler invoked when the session expires. */
export function onSessionExpired(fn: SessionExpiredHandler): void {
  handler = fn
}

/** Re-arm the module: call after a successful login/init-setup. */
export function resetSessionState(): void {
  expired = false
  pendingRedirect = null
}

/**
 * Take (and clear) the path captured when the session expired, so the login
 * page can return the user where they were.
 */
export function consumeRedirect(): string | null {
  const target = pendingRedirect
  pendingRedirect = null
  return target
}

/**
 * Accept only in-app paths as a redirect target, so a crafted `?redirect=`
 * cannot bounce the user to another origin.
 */
export function sanitizeRedirect(value: unknown): string | null {
  if (typeof value !== 'string') return null
  if (!value.startsWith('/') || value.startsWith('//')) return null
  return value
}

function locationPath(): string {
  if (typeof window === 'undefined') return DEFAULT_REDIRECT
  return `${window.location.pathname}${window.location.search}`
}

/**
 * Report an expired/invalid session.
 *
 * Idempotent while the session stays expired: a page firing several requests
 * at once must not produce several redirects or several toasts. Call
 * {@link resetSessionState} once the user is authenticated again.
 */
export function expireSession(path: string = locationPath()): void {
  if (expired) return
  expired = true

  const [pathname] = path.split('?')
  pendingRedirect = PUBLIC_PATHS.includes(pathname) ? DEFAULT_REDIRECT : path
  handler?.(pendingRedirect)
}
