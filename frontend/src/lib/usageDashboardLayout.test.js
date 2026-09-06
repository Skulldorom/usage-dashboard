import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const page = readFileSync(resolve(currentDir, '../pages/UsageDashboardPage.jsx'), 'utf8')
const styles = readFileSync(resolve(currentDir, '../styles.css'), 'utf8')

describe('usage dashboard information architecture', () => {
  it('keeps user-facing sections in the requested order', () => {
    const headings = ['Provider usage & quota', 'Usage over time', 'Cost & value', 'Breakdown', 'Data sources & quality']
    let last = -1
    for (const heading of headings) {
      const next = page.indexOf(heading)
      expect(next).toBeGreaterThan(last)
      last = next
    }
    expect(page).not.toContain('Provider Pressure')
    expect(page).not.toContain('Highest Utilization')
  })

  it('keeps diagnostics collapsed and tables viewport-safe', () => {
    expect(page).toContain('<Collapse in={open}>')
    expect(styles).toMatch(/\.usage-table-scroll\s*\{[^}]*overflow-x:\s*auto;/s)
  })

  it('keeps controls and summary cards intentional on mobile', () => {
    expect(styles).toMatch(/@media \(max-width: 700px\)[\s\S]*\.usage-page-heading\s*\{[^}]*flex-direction:\s*column;/s)
    expect(page).toContain('size={{ xs: 6, lg: 3 }}')
  })
})
