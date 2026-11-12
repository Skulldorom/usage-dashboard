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
    expect(container.textContent).toContain('alternative to this development build')
    expect(container.textContent).not.toContain('→')
  })
  it('shows installed-to-latest versions and a safe keyboard-accessible external action', async () => {
    await render()
    expect(container.textContent).toContain('Update available')
    const comparison = container.querySelector('.update-version-change')
    expect(comparison.querySelector('.update-version-installed').textContent).toBe('v1.2.0')
    expect(comparison.querySelector('.update-version-latest').textContent).toBe('v1.3.0')
    expect(comparison.querySelector('[aria-hidden="true"]').textContent).toBe('→')
    expect(comparison.querySelector('.update-new-badge').textContent).toBe('New')
    const comparisonLabel = comparison.querySelector('.update-version-comparison-label')
    expect(comparisonLabel.textContent).toBe('to')
    expect(comparisonLabel.hasAttribute('aria-hidden')).toBe(false)
    expect(comparisonLabel.closest('[role="status"]')).toBeNull()
    const copyStatus = container.querySelector('[role="status"]')
    expect(copyStatus.className).toBe('version-copy-status')
    expect(copyStatus.textContent).toBe('')
    const link = container.querySelector('a')
    expect(link.textContent).toContain('View release')
    expect(link.querySelector('svg').getAttribute('aria-hidden')).toBe('true')
    expect(link.getAttribute('href')).toBe(update.release_url)
    expect(link.target).toBe('_blank')
    expect(link.rel).toBe('noopener noreferrer')
    const close = container.querySelector('button[aria-label^="Dismiss"]')
    expect(close.getAttribute('aria-label')).toBe('Dismiss update v1.3.0')
    close.focus()
    expect(document.activeElement).toBe(close)
  })
  it('keeps long verified version labels and the release action available on mobile', async () => {
    const installed = `v1.2.${'1'.repeat(80)}`
    const latest = `v1.3.${'2'.repeat(80)}`
    vi.stubEnv('VITE_APP_VERSION', installed)
    await render({ compact: true, update: {
      ...update, current_version: installed, latest_version: latest,
      release_url: `https://github.com/Skulldorom/usage-dashboard/releases/tag/${latest}`,
    } })
    expect(container.querySelector('.version-footer-mobile')).not.toBeNull()
    expect(container.querySelector('.update-version-installed').textContent).toBe(installed)
    expect(container.querySelector('.update-version-latest').textContent).toBe(latest)
    expect(container.querySelector('a').href).toContain(latest)
  })
  it('shows stable alternatives for development without a version comparison', async () => {
    const development = 'v0.0.0-dev.abcdef1234567'
    vi.stubEnv('VITE_APP_VERSION', development)
    await render({ update: { ...update, current_version: development, status: 'stable_release_available' } })
    expect(container.textContent).toContain('Stable release available')
    expect(container.textContent).toContain('A stable release is available as an alternative')
    expect(container.querySelector('.update-version-installed')).toBeNull()
    expect(container.querySelector('.update-new-badge')).toBeNull()
    expect(container.querySelector('.update-version-latest').textContent).toBe('v1.3.0')
    expect(container.textContent).toContain('v1.3.0')
    expect(container.textContent).not.toContain('→')
  })
  it('shows version metadata independent from the update notification', async () => {
    await render({ update: { ...update, status: 'up_to_date' } })
    expect(container.textContent).toContain('v1.2.0')
    expect(container.querySelector('button[aria-label="Version details"]')).not.toBeNull()
    expect(container.querySelector('button[aria-label="Copy full version metadata"]')).not.toBeNull()
    expect(container.textContent).not.toContain('Up to date')
  })
  it.each([
    { current_version: null, latest_version: 'v1.3.0', status: 'update_available' },
    { current_version: 'v1.2.0', latest_version: null, status: 'update_available' },
    { current_version: 'v1.2.0', latest_version: 'v1.3.0', status: 'unverified_release' },
    { current_version: 'v1.2.0', latest_version: 'v1.3.0', status: 'update_available', cache_status: 'stale' },
  ])('suppresses comparisons for unknown, stale, or unverified metadata %j', async (patch) => {
    await render({ update: { ...update, ...patch } })
    expect(container.querySelector('.update-version-change')).toBeNull()
    expect(container.querySelector('a')).toBeNull()
  })
  it('keeps release verification and version diagnostics independent from the card', async () => {
    await render({ update: { ...update, latest_version: 'v1.2.0', release_url: 'https://github.com/Skulldorom/usage-dashboard/releases/tag/v1.2.0', status: 'up_to_date' } })
    expect(container.querySelector('a')).toBeNull()
    expect(container.textContent).not.toContain('Up to date')
    expect(container.querySelector('.version-diagnostic')).toBeNull()
    expect(container.querySelector('button[aria-label="Version details"]')).not.toBeNull()
    expect(container.querySelector('button[aria-label="Copy full version metadata"]')).not.toBeNull()
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
    { current_version: 'v1.4.0', status: 'ahead_of_release', expected: 'Ahead of published release' },
    { current_version: 'v0.0.0', status: 'unknown', expected: 'Version unknown' },
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
    { checked_at: new Date(Date.now() - 22 * 60000).toISOString() },
    { checked_at: null },
    { checked_at: new Date(Date.now() + 60000).toISOString() },
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
    await render({ update: { ...update, checked_at: new Date(Date.now() - 20 * 60000 - 30000).toISOString() } })
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
    await act(async () => vi.advanceTimersByTime(16 * 60 * 1000))
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(container.textContent).toBe('')
    expect(vi.getTimerCount()).toBe(0)
  })
  it('polls every 15 minutes and rechecks when visible after being hidden', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...update, checked_at: new Date().toISOString() }), { headers: { 'content-type': 'application/json' } }))
    vi.stubGlobal('fetch', fetch)
    await act(async () => root.render(createElement(Harness, { authenticated: true })))
    expect(fetch).toHaveBeenCalledTimes(1)
    await act(async () => vi.advanceTimersByTime(15 * 60 * 1000 - 1))
    expect(fetch).toHaveBeenCalledTimes(1)
    await act(async () => vi.advanceTimersByTime(1))
    expect(fetch).toHaveBeenCalledTimes(2)
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    await act(async () => vi.advanceTimersByTime(15 * 60 * 1000))
    expect(fetch).toHaveBeenCalledTimes(2)
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
    await act(async () => document.dispatchEvent(new Event('visibilitychange')))
    expect(fetch).toHaveBeenCalledTimes(3)
  })
  it.each(['update_available', 'stable_release_available'])('keeps %s visible through the polling interval and a delayed refresh', async (status) => {
    const current_version = status === 'stable_release_available' ? 'v0.0.0-dev.abcdef1234567' : 'v1.2.0'
    vi.stubEnv('VITE_APP_VERSION', current_version)
    const response = (checked_at) => new Response(JSON.stringify({ ...update, current_version, status, checked_at }), { headers: { 'content-type': 'application/json' } })
    let resolve
    const fetch = vi.fn()
      .mockResolvedValueOnce(response(new Date(Date.now() - 5 * 60000 + 1).toISOString()))
      .mockImplementationOnce(() => new Promise((done) => { resolve = done }))
      .mockImplementation(() => new Promise(() => {}))
    vi.stubGlobal('fetch', fetch)
    await act(async () => root.render(createElement(Harness, { authenticated: true })))
    for (let minute = 1; minute <= 15; minute++) {
      await act(async () => vi.advanceTimersByTime(60000))
      expect(container.querySelector('a')).not.toBeNull()
    }
    expect(fetch).toHaveBeenCalledTimes(2)
    await act(async () => vi.advanceTimersByTime(30000))
    expect(container.querySelector('a')).not.toBeNull()
    await act(async () => resolve(response(new Date().toISOString())))
    await act(async () => vi.advanceTimersByTime(15 * 60000))
    expect(container.querySelector('a')).not.toBeNull()
    expect(fetch).toHaveBeenCalledTimes(3)
    await act(async () => vi.advanceTimersByTime(6 * 60000))
    expect(container.querySelector('a')).toBeNull()
    expect(container.textContent).toContain('Release metadata stale')
  })
  it('suppresses a visible banner immediately when a scheduled request fails', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...update, checked_at: new Date().toISOString() }), { headers: { 'content-type': 'application/json' } }))
      .mockRejectedValueOnce(new Error('offline'))
    vi.stubGlobal('fetch', fetch)
    await act(async () => root.render(createElement(Harness, { authenticated: true })))
    expect(container.querySelector('a')).not.toBeNull()
    await act(async () => vi.advanceTimersByTime(15 * 60000))
    expect(container.querySelector('a')).toBeNull()
    expect(container.textContent).toContain('Update check unavailable')
    expect(container.textContent).not.toContain('Up to date')
    expect(container.textContent).toContain('v1.2.0')
  })
  it('starts the next polling interval from a visibility-triggered check', async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ ...update, checked_at: new Date().toISOString() }), { headers: { 'content-type': 'application/json' } })))
    vi.stubGlobal('fetch', fetch)
    await act(async () => root.render(createElement(Harness, { authenticated: true })))
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    await act(async () => vi.advanceTimersByTime(16 * 60000))
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
    await act(async () => document.dispatchEvent(new Event('visibilitychange')))
    expect(fetch).toHaveBeenCalledTimes(2)
    await act(async () => vi.advanceTimersByTime(14 * 60000))
    expect(fetch).toHaveBeenCalledTimes(2)
    await act(async () => vi.advanceTimersByTime(60000))
    expect(fetch).toHaveBeenCalledTimes(3)
    expect(container.querySelector('a')).not.toBeNull()
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
