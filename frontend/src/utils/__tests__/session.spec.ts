import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  consumeRedirect,
  expireSession,
  onSessionExpired,
  resetSessionState,
  sanitizeRedirect,
} from '../session'

describe('session expiry', () => {
  beforeEach(() => {
    resetSessionState()
  })

  it('notifies the registered handler with the current path', () => {
    const handler = vi.fn()
    onSessionExpired(handler)

    expireSession('/jobs/abc')

    expect(handler).toHaveBeenCalledTimes(1)
    expect(handler).toHaveBeenCalledWith('/jobs/abc')
  })

  it('notifies only once while the session stays expired', () => {
    const handler = vi.fn()
    onSessionExpired(handler)

    expireSession('/jobs/abc')
    expireSession('/jobs/abc')
    expireSession('/dashboard')

    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('falls back to the dashboard when already on a public route', () => {
    const handler = vi.fn()
    onSessionExpired(handler)

    expireSession('/login')

    expect(handler).toHaveBeenCalledWith('/dashboard')
  })

  it('exposes the redirect target for the login page to consume', () => {
    expireSession('/logs')

    expect(consumeRedirect()).toBe('/logs')
    expect(consumeRedirect()).toBeNull()
  })

  it('only accepts in-app paths as a redirect target', () => {
    expect(sanitizeRedirect('/jobs/abc?tab=trigger')).toBe('/jobs/abc?tab=trigger')
    expect(sanitizeRedirect('//evil.test/steal')).toBeNull()
    expect(sanitizeRedirect('https://evil.test')).toBeNull()
    expect(sanitizeRedirect(undefined)).toBeNull()
  })
})
