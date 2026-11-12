// @vitest-environment jsdom
import { act, createElement } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import UpdateNotification from './UpdateNotification.jsx'
import useUpdateStatus from '../lib/useUpdateStatus.js'

const update = {
  current_version: 'v1.2.0', latest_version: 'v1.3.0', status: 'update_available',
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
  it('keeps matching SHA development versions visible without a stable update claim', async () => {
    const development = 'v0.0.0-dev.abc123'
    vi.stubEnv('VITE_APP_VERSION', development)
    await render({ update: { ...update, current_version: development, status: 'unknown' } })
    expect(container.textContent).toContain(development)
    expect(container.textContent).not.toContain('Update available')
    expect(container.querySelector('a')).toBeNull()
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
    const close = container.querySelector('button')
    expect(close.getAttribute('aria-label')).toBe('Dismiss update v1.3.0')
    close.focus()
    expect(document.activeElement).toBe(close)
  })
  it('dismisses per release, survives remount, and keeps the current version visible', async () => {
    await render()
    await act(async () => container.querySelector('button').click())
    expect(container.textContent).not.toContain('Update available')
    expect(container.textContent).toContain('v1.2.0')
    expect(localStorage.getItem('usage-dashboard:dismissed-update')).toBe('v1.3.0')
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
    expect(container.textContent).toBe('Version unknown')
    await render({ update: { ...update, current_version: 'v1.1.0' } })
    expect(container.querySelector('a')).toBeNull()
    expect(container.textContent).toContain('Frontend v1.2.0')
  })
  it('survives restricted dismissal storage', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('restricted') })
    await render()
    await act(async () => container.querySelector('button').click())
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
  it('ignores late requests on logout and handles API failures silently', async () => {
    let resolve
    vi.stubGlobal('fetch', vi.fn(() => new Promise((done) => { resolve = done })))
    await act(async () => root.render(createElement(Harness, { authenticated: true })))
    await act(async () => root.render(createElement(Harness, { authenticated: false })))
    await act(async () => resolve(new Response(JSON.stringify(update), { headers: { 'content-type': 'application/json' } })))
    expect(container.textContent).toBe('')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    await act(async () => root.render(createElement(Harness, { authenticated: true })))
    expect(container.textContent).toBe('')
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
