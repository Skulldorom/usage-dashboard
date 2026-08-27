// Usage-page submenu model. Provider-specific sections only exist when a single
// provider is selected, so the submenu must hide those anchors on the
// "All providers" view rather than showing navigation that goes nowhere.

export const usageSubmenuItems = [
  { href: '#usage-filters', label: 'Filters' },
  { href: '#usage-overview', label: 'Overview' },
  { href: '#usage-provider-trends', label: 'Provider trends', providerOnly: true },
  { href: '#usage-breakdowns', label: 'Daily / hourly', providerOnly: true },
  { href: '#usage-attribution', label: 'Attribution', providerOnly: true },
]

export function visibleUsageSubmenuItems(hasProviderSelected) {
  return usageSubmenuItems.filter((item) => !item.providerOnly || hasProviderSelected)
}
