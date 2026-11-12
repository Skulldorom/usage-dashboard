// @vitest-environment jsdom
import { act, createElement } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App.jsx'
import { usageSubmenuItems, visibleUsageSubmenuItems } from './navigation.js'

describe('usage submenu', () => {
  it('shows only always-present sections on the all-providers view', () => {
    const items = visibleUsageSubmenuItems(false)
    expect(items.map((item) => item.label)).toEqual(['Filters', 'Overview'])
  })

  it('shows every section once a provider is selected', () => {
    const items = visibleUsageSubmenuItems(true)
    expect(items).toHaveLength(usageSubmenuItems.length)
    expect(items.map((item) => item.label)).toEqual([
      'Filters',
      'Overview',
      'Provider trends',
      'Daily / hourly',
      'Attribution',
    ])
  })
})

describe('rendered primary navigation', () => {
  let root, container
  const sidebar = () => container.querySelector('.sidebar nav')
  const submenuLinks = () => [...sidebar().querySelectorAll('.nav-submenu a')]
  const labels = () => submenuLinks().map((link) => link.textContent)

  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true
    localStorage.clear()
    localStorage.setItem('usage_dashboard_admin_session_token', 'navigation-test-session')
    // Stub only the HTTP boundary; render the real shell, router and pages.
    const provider = { config_id: 1, provider: 'codex', label: 'Navigation fixture' }
    vi.stubGlobal('fetch', vi.fn(async (url) => {
      const path = new URL(url, window.location.origin).pathname
      const payload = path.endsWith('/auth/status') ? { setup_required: false }
        : path.endsWith('/usage') ? [{ config: { id: 1, provider: 'codex' } }]
        : path.endsWith('/analytics/overview') ? { providers: [provider] }
        : path.includes('/analytics/') ? {} : []
      return new Response(JSON.stringify(payload), { headers: { 'Content-Type': 'application/json' } })
    }))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(async () => {
    await act(async () => root.unmount())
    container.remove()
    localStorage.clear()
    window.history.replaceState({}, '', '/')
    vi.unstubAllGlobals()
  })

  async function render(path) {
    window.history.replaceState({}, '', path)
    await act(async () => root.render(createElement(App)))
  }

  async function click(link) {
    await act(async () => {
      link.click()
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
  }

  it.each(['/usage', '/usage?provider=all', '/usage?provider=1'])(
    'renders the appropriate Usage anchors at %s', async (path) => {
      await render(path)
      const expected = visibleUsageSubmenuItems(path.endsWith('=1'))
      expect(labels()).toEqual(expected.map((item) => item.label))
      expect(submenuLinks().map((link) => link.getAttribute('href'))).toEqual(expected.map((item) => item.href))
      expect(sidebar().querySelector('a[aria-current="page"]').textContent).toBe('Usage')
      const overview = submenuLinks().find((link) => link.textContent === 'Overview')
      overview.focus()
      expect(document.activeElement).toBe(overview)
      await click(overview)
      expect(window.location.hash).toBe('#usage-overview')
      expect(sidebar().querySelector('.nav-submenu-link.active').textContent).toBe('Overview')
    },
  )

  it('navigates between primary routes and retains Settings section anchors', async () => {
    await render('/usage')
    expect(sidebar().querySelector('.brand-lockup').textContent).toBe('Usage DashboardCommand Center')
    const primary = [...sidebar().querySelectorAll('.nav-link')]
    expect(primary.map((link) => [link.textContent, link.getAttribute('href')])).toEqual([
      ['Dashboard', '/'], ['Usage', '/usage'], ['Settings', '/settings'],
    ])
    await click(primary.find((link) => link.textContent === 'Settings'))
    expect(window.location.pathname).toBe('/settings')
    expect(sidebar().querySelector('a[aria-current="page"]').textContent).toBe('Settings')
    expect(labels()).toEqual(['Provider settings', 'Data sources', 'Integrations', 'Integration tokens'])
    for (const link of submenuLinks()) {
      await click(link)
      expect(window.location.hash).toBe(link.getAttribute('href'))
      expect(document.getElementById(link.hash.slice(1))).not.toBeNull()
    }
    const mobile = container.querySelector('.mobile-navigation')
    expect([...mobile.querySelectorAll('.nav-link')].map((link) => link.textContent)).toEqual(['Dashboard', 'Usage', 'Settings'])
    expect(mobile.querySelector('.nav-submenu')).toBeNull()
    await click(mobile.querySelector('a[href="/"]'))
    expect(window.location.pathname).toBe('/')
    expect(sidebar().querySelector('a[aria-current="page"]').textContent).toBe('Dashboard')
    expect(submenuLinks()).toHaveLength(0)
  })
})
