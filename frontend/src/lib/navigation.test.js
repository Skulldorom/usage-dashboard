import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { usageSubmenuItems, visibleUsageSubmenuItems } from './navigation.js'

const appSource = readFileSync(new URL('../App.jsx', import.meta.url), 'utf8')
const styles = readFileSync(new URL('../styles.css', import.meta.url), 'utf8')

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

describe('primary sidebar presentation and routes', () => {
  it('shows the full product name and retains primary and settings navigation', () => {
    expect(appSource).toContain('<strong>Usage Dashboard</strong>')
    expect(appSource).toContain('<span>Command Center</span>')
    expect(appSource).toContain('{ to: "/", label: "Dashboard"')
    expect(appSource).toContain('{ to: "/usage", label: "Usage"')
    expect(appSource).toContain('{ to: "/settings", label: "Settings"')
    expect(appSource).toContain('showSettingsSubmenu &&')
    expect(appSource).toContain('settingsSubmenuItems.map((subitem) => (')
    expect(appSource).toContain('href={subitem.href}')
  })

  it('keeps a scrollable desktop sidebar with focus-visible navigation states', () => {
    expect(styles).toMatch(/\.sidebar\s*\{[^}]*overflow-y:\s*auto/s)
    expect(styles).toMatch(/\.side-navigation\s*\{[^}]*flex-direction:\s*column/s)
    expect(styles).toMatch(/\.sidebar-lower-section\s*\{[^}]*margin-top:\s*auto/s)
    expect(styles).toContain('.nav-link:focus-visible')
    expect(styles).toContain('.nav-submenu-link:focus-visible')
    expect(styles).toMatch(/@media \(prefers-reduced-motion:\s*reduce\)/)
    const tabletRules = styles.match(/@media \(max-width:\s*900px\)\s*\{([\s\S]*?)\n\}/)
    expect(tabletRules?.[1]).toContain('.sidebar {')
    expect(tabletRules?.[1]).toContain('display: none')
  })
})
