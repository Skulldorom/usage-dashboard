// @vitest-environment jsdom
import { act, createElement } from 'react'
import userEvent from '@testing-library/user-event'
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
  let root, container, user, scrollIntoView
  const sidebar = () => container.querySelector('.sidebar nav')
  const submenuLinks = () => [...sidebar().querySelectorAll('.nav-submenu a')]
  const labels = () => submenuLinks().map((link) => link.textContent)

  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true
    user = userEvent.setup()
    // jsdom has no layout or scrolling; keep the real router and DOM targets.
    scrollIntoView = vi.fn()
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { configurable: true, value: scrollIntoView })
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
    delete HTMLElement.prototype.scrollIntoView
    vi.unstubAllGlobals()
  })

  async function render(path) {
    window.history.replaceState({}, '', path)
    await act(async () => root.render(createElement(App)))
  }

  async function click(link) {
    await act(async () => user.click(link))
  }

  it.each(['/usage', '/usage?provider=all', '/usage?provider=1'])(
    'renders the appropriate Usage anchors at %s', async (path) => {
      await render(path)
      const expected = visibleUsageSubmenuItems(path.endsWith('=1'))
      expect(labels()).toEqual(expected.map((item) => item.label))
      expect(submenuLinks().map((link) => link.getAttribute('href'))).toEqual(expected.map((item) => `${path}${item.href}`))
      expect(sidebar().querySelector('a[aria-current="page"]').textContent).toBe('Usage')
      const overview = submenuLinks().find((link) => link.textContent === 'Overview')
      for (const link of submenuLinks()) {
        expect(document.getElementById(link.hash.slice(1))).not.toBeNull()
      }
      overview.focus()
      expect(document.activeElement).toBe(overview)
      await click(overview)
      expect(window.location.pathname + window.location.search).toBe(path)
      expect(window.location.hash).toBe('#usage-overview')
      expect(sidebar().querySelector('.nav-submenu-link.active').textContent).toBe('Overview')
    },
  )

  it('commits the active section together with the hash navigation', async () => {
    await render('/usage?provider=1')
    const overview = submenuLinks().find((link) => link.textContent === 'Overview')
    act(() => overview.click())
    expect(window.location.hash).toBe('#usage-overview')
    expectActive('Overview')
  })

  async function traverse(direction) {
    await act(async () => {
      const popped = new Promise((resolve) => window.addEventListener('popstate', resolve, { once: true }))
      window.history[direction]()
      await popped
    })
  }

  function expectActive(label) {
    expect(submenuLinks().filter((link) => link.classList.contains('active')).map((link) => link.textContent)).toEqual([label])
  }

  it.each(['/usage', '/usage?provider=all', '/usage?provider=1'])(
    'supports section switching and browser history at %s', async (path) => {
      await render(path)
      await click(submenuLinks().find((link) => link.textContent === 'Overview'))
      expectActive('Overview')
      const requests = fetch.mock.calls.length
      await click(submenuLinks().find((link) => link.textContent === 'Filters'))
      expectActive('Filters')
      expect(window.location.hash).toBe('#usage-filters')
      await traverse('back')
      expectActive('Overview')
      expect(window.location.hash).toBe('#usage-overview')
      await traverse('forward')
      expectActive('Filters')
      expect(window.location.hash).toBe('#usage-filters')
      expect(window.location.pathname + window.location.search).toBe(path)
      expect(fetch.mock.calls).toHaveLength(requests)
    },
  )

  it.each(['/usage', '/usage?provider=all', '/usage?provider=1'])(
    'activates a direct Overview deep link at %s', async (path) => {
      await render(`${path}#usage-overview`)
      expectActive('Overview')
      expect(document.getElementById('usage-overview')).not.toBeNull()
      expect(scrollIntoView.mock.contexts.at(-1)).toBe(document.getElementById('usage-overview'))
    },
  )

  it('supports keyboard activation without losing link focus', async () => {
    await render('/usage?provider=1')
    const filters = submenuLinks()[0]
    filters.focus()
    await act(async () => user.tab())
    const overview = submenuLinks()[1]
    expect(document.activeElement).toBe(overview)
    expect(overview.tagName).toBe('A')
    await act(async () => user.keyboard('{Enter}'))
    expectActive('Overview')
    expect(window.location.hash).toBe('#usage-overview')
    expect(window.location.search).toBe('?provider=1')
    expect(document.activeElement).toBe(overview)
  })

  it.each(usageSubmenuItems.filter((item) => item.providerOnly))(
    'retains provider-specific deep link $href', async ({ href, label }) => {
      await render(`/usage?provider=1${href}`)
      expectActive(label)
      expect(document.getElementById(href.slice(1))).not.toBeNull()
      await click(submenuLinks()[0])
      await traverse('back')
      expectActive(label)
      expect(window.location.search).toBe('?provider=1')
    },
  )

  it('updates submenu visibility when the provider filter changes', async () => {
    await render('/usage?provider=1')
    const providerSelect = container.querySelector('[role="combobox"]')
    await click(providerSelect)
    const allProviders = [...document.querySelectorAll('[role="option"]')].find((option) => option.textContent === 'All providers')
    await click(allProviders)
    expect(window.location.search).toBe('')
    expect(labels()).toEqual(['Filters', 'Overview'])
    await traverse('back')
    expect(window.location.search).toBe('?provider=1')
    expect(labels()).toEqual(usageSubmenuItems.map((item) => item.label))
  })

  it('scrolls to the selected section without refetching data or losing focus', async () => {
    await render('/usage?provider=1')
    const requests = fetch.mock.calls.length
    for (const link of submenuLinks()) {
      await click(link)
      expectActive(link.textContent)
      expect(window.location.hash).toBe(link.hash)
      expect(document.activeElement).toBe(link)
      expect(scrollIntoView.mock.contexts.at(-1)).toBe(document.getElementById(link.hash.slice(1)))
    }
    expect(fetch.mock.calls).toHaveLength(requests)
  })

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
