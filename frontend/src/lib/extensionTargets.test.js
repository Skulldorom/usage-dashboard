import { describe, expect, it } from 'vitest'
import { EXTENSION_PROTOCOL_VERSION, EXTENSION_TARGETS, getExtensionTargets } from './extensionTargets.js'

describe('extensionTargets', () => {
  it('uses protocol version 1', () => {
    expect(EXTENSION_PROTOCOL_VERSION).toBe(1)
  })

  it('stores the stable Chrome Web Store extension id in source', () => {
    expect(EXTENSION_TARGETS.chrome).toMatchObject({
      id: 'lajooelgpfeholbdkmammfladpefohgk',
      transport: 'chromium',
    })
  })

  it('returns production targets without requiring self-hosted configuration', () => {
    expect(getExtensionTargets({})).toEqual([
      expect.objectContaining({
        key: 'chrome',
        id: 'lajooelgpfeholbdkmammfladpefohgk',
        transport: 'chromium',
      }),
    ])
  })

  it('allows development override ids without changing the production registry', () => {
    expect(getExtensionTargets({ VITE_EXTENSION_TARGET_CHROME_ID: 'dev-extension-id' })).toEqual([
      expect.objectContaining({ key: 'chrome', id: 'dev-extension-id', productionId: 'lajooelgpfeholbdkmammfladpefohgk' }),
    ])
    expect(EXTENSION_TARGETS.chrome.id).toBe('lajooelgpfeholbdkmammfladpefohgk')
  })

  it('omits unpublished targets until an id or override exists', () => {
    const targets = getExtensionTargets({})
    expect(targets.map((target) => target.key)).not.toContain('firefox')
    expect(targets.map((target) => target.key)).not.toContain('safari')
  })

  it('prefers runtime extension target ids over Vite env and source defaults', () => {
    globalThis.__USAGE_DASHBOARD_CONFIG__ = { extensionTargets: { chrome: 'runtime-chrome-id' } }

    expect(getExtensionTargets({ VITE_EXTENSION_TARGET_CHROME_ID: 'vite-dev-id' })).toEqual([
      expect.objectContaining({ key: 'chrome', id: 'runtime-chrome-id', productionId: 'lajooelgpfeholbdkmammfladpefohgk' }),
    ])

    delete globalThis.__USAGE_DASHBOARD_CONFIG__
  })

  it('ignores blank runtime extension target ids', () => {
    globalThis.__USAGE_DASHBOARD_CONFIG__ = { extensionTargets: { chrome: '' } }

    expect(getExtensionTargets({ VITE_EXTENSION_TARGET_CHROME_ID: 'vite-dev-id' })[0].id).toBe('vite-dev-id')

    delete globalThis.__USAGE_DASHBOARD_CONFIG__
  })
})
