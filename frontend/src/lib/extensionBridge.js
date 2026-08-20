import { EXTENSION_MESSAGE_TYPES, EXTENSION_PROTOCOL_VERSION, getExtensionTargets } from './extensionTargets.js'

const DEFAULT_TIMEOUT_MS = 1000

function defaultRuntime() {
  return globalThis.chrome?.runtime || null
}

function timeoutResult() {
  return { timedOut: true }
}

function sendRuntimeMessage({ runtime, target, message, timeoutMs }) {
  return new Promise((resolve) => {
    let settled = false
    const timeout = globalThis.setTimeout(() => {
      if (settled) return
      settled = true
      resolve(timeoutResult())
    }, timeoutMs)

    try {
      runtime.sendMessage(target.id, message, (response) => {
        if (settled) return
        settled = true
        globalThis.clearTimeout(timeout)
        const lastError = runtime.lastError
        if (lastError) resolve({ error: lastError.message || 'Extension messaging failed.' })
        else resolve({ response })
      })
    } catch (err) {
      if (settled) return
      settled = true
      globalThis.clearTimeout(timeout)
      resolve({ error: err instanceof Error ? err.message : 'Extension messaging failed.' })
    }
  })
}

function statusFromError(message = '') {
  if (/receiving end does not exist|could not establish connection|does not exist/i.test(message)) return 'not-installed'
  return 'error'
}

function responseErrorMessage(response) {
  return response?.detail || response?.error || response?.message || ''
}

function logBridgeFailure(stage, detail) {
  if (!detail?.status || ['available', 'authorized', 'connected', 'connected-degraded'].includes(detail.status)) return
  console.warn('[Usage Dashboard] extension bridge failure', { stage, ...detail })
}

export function extensionSupportsOneClickSetup(response) {
  return Array.isArray(response?.capabilities) && response.capabilities.includes('authorize-origin')
}

function mapConfigureResponse(response) {
  if (response?.ok && response.protocolVersion === EXTENSION_PROTOCOL_VERSION) {
    return {
      status: response.reachable === false ? 'connected-degraded' : 'connected',
      configured: Boolean(response.configured),
      reachable: response.reachable !== false,
      response,
    }
  }
  if (response?.protocolVersion && response.protocolVersion !== EXTENSION_PROTOCOL_VERSION) {
    return { status: 'incompatible-protocol', response }
  }
  if (!response?.ok && response?.code) return { status: response.code, error: responseErrorMessage(response), response }
  return { status: 'error', error: responseErrorMessage(response), response }
}

export function createExtensionBridge({ runtime = defaultRuntime(), targets = getExtensionTargets(), timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
  async function ping() {
    if (!runtime?.sendMessage) return { status: 'unsupported-browser' }
    if (!targets.length) return { status: 'unsupported-browser' }

    let sawTimeout = false
    let sawIncompatible = false
    let sawNotInstalled = false

    for (const target of targets) {
      if (target.transport !== 'chromium') continue
      const result = await sendRuntimeMessage({
        runtime,
        target,
        timeoutMs,
        message: { type: EXTENSION_MESSAGE_TYPES.ping, protocolVersion: EXTENSION_PROTOCOL_VERSION },
      })

      if (result.timedOut) {
        sawTimeout = true
        continue
      }
      if (result.error) {
        if (statusFromError(result.error) === 'not-installed') sawNotInstalled = true
        continue
      }
      if (result.response?.ok && result.response.protocolVersion === EXTENSION_PROTOCOL_VERSION) {
        return { status: 'available', target, response: result.response }
      }
      if (result.response?.protocolVersion && result.response.protocolVersion !== EXTENSION_PROTOCOL_VERSION) sawIncompatible = true
    }

    if (sawIncompatible) return { status: 'incompatible-protocol' }
    if (sawTimeout) return { status: 'timeout' }
    if (sawNotInstalled) return { status: 'not-installed' }
    return { status: 'not-installed' }
  }

  async function authorizeOrigin({ target }) {
    if (!runtime?.sendMessage) return { status: 'unsupported-browser' }
    if (!target) return { status: 'not-installed' }

    const result = await sendRuntimeMessage({
      runtime,
      target,
      timeoutMs,
      message: { type: EXTENSION_MESSAGE_TYPES.authorizeOrigin, protocolVersion: EXTENSION_PROTOCOL_VERSION },
    })
    if (result.timedOut) { const detail = { status: 'timeout' }; logBridgeFailure('authorize-origin', detail); return detail }
    if (result.error) { const detail = { status: statusFromError(result.error), error: result.error }; logBridgeFailure('authorize-origin', detail); return detail }
    if (result.response?.ok && result.response.protocolVersion === EXTENSION_PROTOCOL_VERSION) return { status: 'authorized', response: result.response }
    if (!result.response?.ok && result.response?.code) { const detail = { status: result.response.code, error: responseErrorMessage(result.response), response: result.response }; logBridgeFailure('authorize-origin', detail); return detail }
    { const detail = { status: 'error', error: responseErrorMessage(result.response), response: result.response }; logBridgeFailure('authorize-origin', detail); return detail }
  }

  async function configure({ target, token, replaceExisting = false }) {
    if (!runtime?.sendMessage) return { status: 'unsupported-browser' }
    if (!target) return { status: 'not-installed' }

    const message = { type: EXTENSION_MESSAGE_TYPES.configure, protocolVersion: EXTENSION_PROTOCOL_VERSION, token }
    if (replaceExisting) message.replaceExisting = true

    const result = await sendRuntimeMessage({ runtime, target, timeoutMs, message })
    if (result.timedOut) { const detail = { status: 'timeout' }; logBridgeFailure('authorize-origin', detail); return detail }
    if (result.error) { const detail = { status: statusFromError(result.error), error: result.error }; logBridgeFailure('authorize-origin', detail); return detail }
    return mapConfigureResponse(result.response)
  }

  return { ping, authorizeOrigin, configure }
}

export const extensionBridge = createExtensionBridge()
