import { describe, expect, it, vi } from 'vitest'
import { createExtensionBridge } from './extensionBridge.js'

function runtimeWithResponses(responses) {
  const calls = []
  const runtime = {
    lastError: null,
    sendMessage(extensionId, message, callback) {
      calls.push({ extensionId, message })
      const response = responses.shift()
      if (response instanceof Error) {
        runtime.lastError = { message: response.message }
        callback(undefined)
        runtime.lastError = null
        return
      }
      if (response !== 'no-callback') callback(response)
    },
  }
  return { runtime, calls }
}

const chromeTarget = { key: 'chrome', id: 'chrome-id', transport: 'chromium', label: 'Chrome' }
const edgeTarget = { key: 'edge', id: 'edge-id', transport: 'chromium', label: 'Edge' }

describe('extensionBridge', () => {
  it('reports unsupported-browser when no runtime transport is available', async () => {
    const bridge = createExtensionBridge({ runtime: null, targets: [chromeTarget], timeoutMs: 1 })

    await expect(bridge.ping()).resolves.toMatchObject({ status: 'unsupported-browser' })
  })

  it('pings candidates with protocol version 1 and stops on the first compatible target', async () => {
    const { runtime, calls } = runtimeWithResponses([
      { ok: false, protocolVersion: 1, code: 'not-this-one' },
      { ok: true, protocolVersion: 1 },
    ])
    const bridge = createExtensionBridge({ runtime, targets: [chromeTarget, edgeTarget], timeoutMs: 20 })

    const result = await bridge.ping()

    expect(result).toMatchObject({ status: 'available', target: edgeTarget })
    expect(calls).toEqual([
      { extensionId: 'chrome-id', message: { type: 'usage-dashboard:ping', protocolVersion: 1 } },
      { extensionId: 'edge-id', message: { type: 'usage-dashboard:ping', protocolVersion: 1 } },
    ])
  })

  it('distinguishes incompatible protocol from not-installed runtime errors', async () => {
    const incompatible = runtimeWithResponses([{ ok: true, protocolVersion: 2 }])
    await expect(createExtensionBridge({ runtime: incompatible.runtime, targets: [chromeTarget], timeoutMs: 20 }).ping()).resolves.toMatchObject({
      status: 'incompatible-protocol',
    })

    const notInstalled = runtimeWithResponses([new Error('Could not establish connection. Receiving end does not exist.')])
    await expect(createExtensionBridge({ runtime: notInstalled.runtime, targets: [chromeTarget], timeoutMs: 20 }).ping()).resolves.toMatchObject({
      status: 'not-installed',
    })
  })

  it('times out unavailable candidates and continues probing', async () => {
    vi.useFakeTimers()
    const { runtime, calls } = runtimeWithResponses(['no-callback', { ok: true, protocolVersion: 1 }])
    const bridge = createExtensionBridge({ runtime, targets: [chromeTarget, edgeTarget], timeoutMs: 5 })
    const pending = bridge.ping()

    await vi.advanceTimersByTimeAsync(5)
    await vi.runAllTimersAsync()
    const result = await pending

    expect(result).toMatchObject({ status: 'available', target: edgeTarget })
    expect(calls.map((call) => call.extensionId)).toEqual(['chrome-id', 'edge-id'])
    vi.useRealTimers()
  })


  it('pre-authorizes the dashboard origin before token creation', async () => {
    const { runtime, calls } = runtimeWithResponses([{ ok: true, protocolVersion: 1, authorized: true }])
    const bridge = createExtensionBridge({ runtime, targets: [chromeTarget], timeoutMs: 20 })

    const result = await bridge.authorizeOrigin({ target: chromeTarget })

    expect(result).toMatchObject({ status: 'authorized' })
    expect(calls).toEqual([
      { extensionId: 'chrome-id', message: { type: 'usage-dashboard:authorize-origin', protocolVersion: 1 } },
    ])
  })

  it('maps pre-authorization permission denial without a token', async () => {
    const { runtime } = runtimeWithResponses([{ ok: false, protocolVersion: 1, code: 'permission-denied' }])
    const bridge = createExtensionBridge({ runtime, targets: [chromeTarget], timeoutMs: 20 })

    await expect(bridge.authorizeOrigin({ target: chromeTarget })).resolves.toMatchObject({ status: 'permission-denied' })
  })

  it('configures a target with token only and no dashboard url', async () => {
    const { runtime, calls } = runtimeWithResponses([{ ok: true, configured: true, reachable: false, protocolVersion: 1 }])
    const bridge = createExtensionBridge({ runtime, targets: [chromeTarget], timeoutMs: 20 })

    const result = await bridge.configure({ target: chromeTarget, token: 'udt_secret' })

    expect(result).toMatchObject({ status: 'connected-degraded', configured: true, reachable: false })
    expect(calls).toEqual([
      {
        extensionId: 'chrome-id',
        message: { type: 'usage-dashboard:configure', protocolVersion: 1, token: 'udt_secret' },
      },
    ])
    expect(JSON.stringify(calls[0].message)).not.toContain('dashboardUrl')
  })

  it('passes explicit replacement intent and maps permission denial', async () => {
    const { runtime, calls } = runtimeWithResponses([{ ok: false, protocolVersion: 1, code: 'permission-denied' }])
    const bridge = createExtensionBridge({ runtime, targets: [chromeTarget], timeoutMs: 20 })

    const result = await bridge.configure({ target: chromeTarget, token: 'udt_secret', replaceExisting: true })

    expect(result).toMatchObject({ status: 'permission-denied' })
    expect(calls[0].message).toEqual({
      type: 'usage-dashboard:configure',
      protocolVersion: 1,
      token: 'udt_secret',
      replaceExisting: true,
    })
  })

  it('preserves error details for unknown configure failures', async () => {
    const { runtime } = runtimeWithResponses([{ ok: false, protocolVersion: 1, code: 'origin-mismatch', error: 'Origin did not match the saved dashboard.' }])
    const bridge = createExtensionBridge({ runtime, targets: [chromeTarget], timeoutMs: 20 })

    const result = await bridge.configure({ target: chromeTarget, token: 'udt_secret' })

    expect(result).toMatchObject({
      status: 'origin-mismatch',
      error: 'Origin did not match the saved dashboard.',
    })
  })
})
