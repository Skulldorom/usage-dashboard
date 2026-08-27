import { describe, expect, it } from 'vitest'
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
