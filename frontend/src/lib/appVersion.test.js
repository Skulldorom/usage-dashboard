import { describe, expect, it } from 'vitest'
import { appVersion, newerStable } from './appVersion.js'

describe('application version metadata', () => {
  it.each(['unknown', 'main', '', null, 'v0.0.0', '0.0.0+build', 'v01.2.3', '1.2', '1.2.3-rc.01'])('does not classify %s as stable', (version) => {
    expect(appVersion(version).kind).toBe('unknown')
  })
  it.each(['v1.0.0', '1.0.0', 'v1.0.0+build'])('shortens stable version %s without losing metadata', (version) => {
    expect(appVersion(version)).toMatchObject({ kind: 'stable', label: 'v1.0.0', full: version })
  })
  it.each(['v0.0.0-dev.abcdef1234567890.dirty', 'v9.0.0-dev.abcdef1234567890'])('shortens SHA in %s', (version) => {
    expect(appVersion(version)).toMatchObject({ kind: 'development', label: 'Development', sha: 'abcdef1', full: version })
  })
  it('keeps other prereleases in the development channel without inventing a SHA', () => {
    expect(appVersion('v1.0.0-rc.1')).toMatchObject({ kind: 'development', label: 'Development', sha: undefined })
  })
  it.each([
    ['v1.0.0', 'v1.0.0', false],
    ['v1.0.0', 'v1.0.1', true],
    ['v1.0.1', 'v1.0.0', false],
    ['v1.10.0', 'v1.9.0', false],
    ['v9007199254740992.0.0', 'v9007199254740993.0.0', true],
    ['v0.0.0-dev.abcdef123', 'v1.0.0', false],
    ['unknown', 'v1.0.0', false],
  ])('compares only known stable versions %s / %s', (current, latest, expected) => {
    expect(newerStable(appVersion(current), appVersion(latest))).toBe(expected)
  })
})
