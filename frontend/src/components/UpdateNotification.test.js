// @vitest-environment jsdom
import { act, createElement } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import UpdateNotification from './UpdateNotification.jsx'
import useUpdateStatus from '../lib/useUpdateStatus.js'

const update = {
  current_version: 'v1.2.0', latest_version: 'v1.3.0', status: 'update_available',
  cache_status: 'fresh', checked_at: new Date().toISOString(),
  release_url: 'https://github.com/Skulldorom/usage-dashboard/releases/tag/v1.3.0',
}
let root, container
async function render(props = {}) {
  await act(async () => root.render(createElement(UpdateNotification, { update, ...props })))
}
function Harness({ authenticated }) {
  const result = useUpdateStatus(authenticated)
  return createElement(UpdateNotification, { update: result })
}
beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true
  localStorage.clear()
  vi.stubEnv('VITE_APP_VERSION', 'v1.2.0')
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
})
afterEach(async () => {
  await act(async () => root.unmount())
  container.remove()
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  vi.useRealTimers()
})
describe('UpdateNotification', () => {
  it('shortens long development metadata and offers a separate stable notice', async () => {
    const development = 'v0.0.0-dev.1feb31f89b6582764d57cc2c2603db1626e2d7415'
    vi.stubEnv('VITE_APP_VERSION', development)
    await render({ update: { ...update, current_version: development, status: 'stable_release_available' } })
    expect(container.textContent).toContain('Development')
    expect(container.querySelector('code').textContent).toBe('1feb31f')
    expect(container.textContent).not.toContain(development)
    expect(container.textContent).toContain('Stable release available')
    expect(container.textContent).not.toContain('Update available')
    expect(container.textContent).toContain('not a newer-version comparison')
  })
  it('shows versions and a safe keyboard-accessible external action', async () => {
    await render()
    expect(container.textContent).toContain('Update available')
    expect(container.textContent).toContain('v1.2.0')
    expect(container.textContent).toContain('v1.3.0')
    const link = container.querySelector('a')
    expect(link.getAttribute('href')).toBe(update.release_url)
    expect(link.target).toBe('_blank')
    expect(link.rel).toBe('noopener noreferrer')
    const close = container.querySelector('button[aria-label^="Dismiss"]')
    expect(close.getAttribute('aria-label')).toBe('Dismiss update v1.3.0')
    close.focus()
    expect(document.activeElement).toBe(close)
  })
  it('dismisses per release, survives remount, and keeps the current version visible', async () => {
    await render()
    await act(async () => container.querySelector('button[aria-label^="Dismiss"]').click())
    expect(container.textContent).not.toContain('Update available')
    expect(container.textContent).toContain('v1.2.0')
    expect(localStorage.getItem('usage-dashboard:dismissed-update:update_available')).toBe('v1.3.0')
    await act(async () => root.unmount())
    root = createRoot(container)
    await render()
    expect(container.querySelector('a')).toBeNull()
    await render({ update: { ...update, latest_version: 'v1.4.0', release_url: update.release_url.replace('v1.3.0', 'v1.4.0') } })
    expect(container.textContent).toContain('Update available')
  })
  it.each(['up_to_date', 'unknown', 'check_failed', 'stale'])('does not advertise %s as an update', async (status) => {
    await render({ update: { ...update, status } })
    expect(container.querySelector('a')).toBeNull()
    expect(container.textContent).toContain('v1.2.0')
  })
  it('does not guess unknown or mismatched installed versions', async () => {
    await render({ update: { ...update, current_version: null } })
    expect(container.textContent).toContain('Version unknown')
    await render({ update: { ...update, current_version: 'v1.1.0' } })
    expect(container.querySelector('a')).toBeNull()
    expect(container.textContent).toContain('Version mismatch')
  })
  it.each([
    { current_version: 'v1.3.0', status: 'up_to_date', expected: 'Up to date' },
    { current_version: 'v1.4.0', status: 'ahead_of_release', expected: 'Ahead of published release' },
    { current_version: 'v0.0.0', status: 'unknown', expected: 'Version unknown' },
    { current_version: 'v1.2.0', status: 'no_stable_release', expected: 'No stable release published' },
    { current_version: 'v1.2.0', status: 'check_failed', expected: 'Update check unavailable' },
    { current_version: 'v1.2.0', status: 'unverified_release', expected: 'Release unverified' },
  ])('renders diagnostic $expected without a release claim', async ({ expected, ...patch }) => {
    vi.stubEnv('VITE_APP_VERSION', patch.current_version)
    await render({ update: { ...update, ...patch } })
    expect(container.textContent).toContain(expected)
    expect(container.querySelector('a')).toBeNull()
  })
  it.each([
    { cache_status: 'stale' },
    { checked_at: new Date(Date.now() - 7 * 3600000).toISOString() },
    { checked_at: null },
    { checked_at: new Date(Date.now() + 3600000).toISOString() },
    { release_url: 'https://evil.example/release' },
    { latest_version: 'v1.3.0-rc.1' },
    { latest_version: 'v0.0.0' },
    { current_version: 'v1.4.0' },
  ])('fails closed on stale, unverified or incompatible metadata %j', async (patch) => {
    await render({ update: { ...update, ...patch } })
    expect(container.querySelector('a')).toBeNull()
    expect(container.textContent).not.toContain('Up to date')
  })
  it('does not accept contradictory or unverified up-to-date claims', async () => {
    for (const patch of [{}, { latest_version: 'v1.2.0', release_url: 'https://evil.example/release' }]) {
      await render({ update: { ...update, status: 'up_to_date', ...patch } })
      expect(container.textContent).not.toContain('Up to date')
      expect(container.textContent).toContain('Release status unknown')
    }
  })
  it.each(['check_failed', 'unverified_release'])('retains %s alongside stale diagnostics', async (status) => {
    await render({ update: { ...update, status, cache_status: 'stale' } })
    expect(container.textContent).toContain(status === 'check_failed' ? 'Update check unavailable' : 'Release unverified')
    expect(container.textContent).toContain('Release metadata stale')
  })
  it('expires a visible notice without another API response', async () => {
    vi.useFakeTimers()
    await render({ update: { ...update, checked_at: new Date(Date.now() - 6 * 3600000 + 30000).toISOString() } })
    expect(container.querySelector('a')).not.toBeNull()
    await act(async () => vi.advanceTimersByTime(60000))
    expect(container.querySelector('a')).toBeNull()
    expect(container.textContent).toContain('Release metadata stale')
  })
  it('keeps dismissal types separate and synchronizes desktop and mobile instances', async () => {
    localStorage.setItem('usage-dashboard:dismissed-update:update_available', 'v1.3.0')
    const development = 'v0.0.0-dev.abcdef1234567'
    vi.stubEnv('VITE_APP_VERSION', development)
    const props = { update: { ...update, current_version: development, status: 'stable_release_available' } }
    await act(async () => root.render(createElement('div', null,
      createElement(UpdateNotification, props), createElement(UpdateNotification, { ...props, compact: true }))))
    expect(container.querySelectorAll('a')).toHaveLength(2)
    expect(container.querySelector('.version-footer-mobile')).not.toBeNull()
    await act(async () => container.querySelector('button[aria-label^="Dismiss"]').click())
    expect(container.querySelectorAll('a')).toHaveLength(0)
    expect(localStorage.getItem('usage-dashboard:dismissed-update:stable_release_available')).toBe('v1.3.0')
  })
  it('exposes full metadata by keyboard tooltip and copies the exact version', async () => {
    const development = 'v0.0.0-dev.1feb31f89b6582764d57cc2c2603db1626e2d7415'
    vi.stubEnv('VITE_APP_VERSION', development)
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    await render({ update: { ...update, current_version: development, status: 'stable_release_available' } })
    const details = container.querySelector('button[aria-label="Version details"]')
    await act(async () => { details.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true })); details.focus() })
    expect(document.activeElement).toBe(details)
    await act(async () => new Promise((resolve) => setTimeout(resolve, 150)))
    expect(document.querySelector('[role="tooltip"]').textContent).toContain(development)
    expect(document.querySelector('[role="tooltip"]').textContent).toContain("Development channel: stable releases are alternatives, not newer-version comparisons.")
    await act(async () => container.querySelector('button[aria-label="Copy full version metadata"]').click())
    expect(writeText).toHaveBeenCalledWith(development)
    expect(container.querySelector('[role="status"]').textContent).toBe('Version copied')
    writeText.mockRejectedValueOnce(new Error('denied'))
    await act(async () => container.querySelector('button[aria-label="Copy full version metadata"]').click())
    expect(container.querySelector('[role="status"]').textContent).toContain('Copy unavailable')
  })
  it('survives restricted dismissal storage', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('restricted') })
    await render()
    await act(async () => container.querySelector('button[aria-label^="Dismiss"]').click())
    expect(container.querySelector('a')).toBeNull()
  })
})
describe('authenticated update lifecycle', () => {
  beforeEach(() => { vi.useFakeTimers() })
  it('checks only authenticated sessions, does not repeat on render, and clears timers on logout', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(update), { headers: { 'content-type': 'application/json' } }))
    vi.stubGlobal('fetch', fetch)
    await act(async () => root.render(createElement(Harness, { authenticated: false })))
    expect(fetch).not.toHaveBeenCalled()
    await act(async () => root.render(createElement(Harness, { authenticated: true })))
    expect(fetch).toHaveBeenCalledTimes(1)
    await act(async () => root.render(createElement(Harness, { authenticated: true })))
    expect(fetch).toHaveBeenCalledTimes(1)
    await act(async () => root.render(createElement(Harness, { authenticated: false })))
    await act(async () => vi.advanceTimersByTime(7 * 60 * 60 * 1000))
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(container.textContent).toBe('')
    expect(vi.getTimerCount()).toBe(0)
  })
  it('ignores late requests on logout and diagnoses API failures', async () => {
    let resolve
    vi.stubGlobal('fetch', vi.fn(() => new Promise((done) => { resolve = done })))
    await act(async () => root.render(createElement(Harness, { authenticated: true })))
    await act(async () => root.render(createElement(Harness, { authenticated: false })))
    await act(async () => resolve(new Response(JSON.stringify(update), { headers: { 'content-type': 'application/json' } })))
    expect(container.textContent).toBe('')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    await act(async () => root.render(createElement(Harness, { authenticated: true })))
    expect(container.textContent).toContain('Version unknown')
    expect(container.textContent).toContain('Update check unavailable')
  })
  it('skips hidden checks and refreshes when visible and stale', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(update), { headers: { 'content-type': 'application/json' } }))
    vi.stubGlobal('fetch', fetch)
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    await act(async () => root.render(createElement(Harness, { authenticated: true })))
    expect(fetch).not.toHaveBeenCalled()
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
    await act(async () => document.dispatchEvent(new Event('visibilitychange')))
    expect(fetch).toHaveBeenCalledTimes(1)
    await act(async () => root.unmount())
    root = createRoot(container)
    expect(vi.getTimerCount()).toBe(0)
  })
})
