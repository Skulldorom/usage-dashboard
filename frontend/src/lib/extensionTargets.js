export const EXTENSION_PROTOCOL_VERSION = 1

export const EXTENSION_MESSAGE_TYPES = {
  ping: 'usage-dashboard:ping',
  configure: 'usage-dashboard:configure',
  authorizeOrigin: 'usage-dashboard:authorize-origin',
}

export const EXTENSION_TARGETS = {
  chrome: {
    id: 'lajooelgpfeholbdkmammfladpefohgk',
    transport: 'chromium',
    label: 'Chrome / Brave',
    browserHints: ['chrome', 'brave'],
    devOverrideEnv: 'VITE_EXTENSION_TARGET_CHROME_ID',
  },
  edge: {
    id: '',
    transport: 'chromium',
    label: 'Microsoft Edge',
    browserHints: ['edge'],
    devOverrideEnv: 'VITE_EXTENSION_TARGET_EDGE_ID',
  },
  opera: {
    id: '',
    transport: 'chromium',
    label: 'Opera',
    browserHints: ['opera'],
    devOverrideEnv: 'VITE_EXTENSION_TARGET_OPERA_ID',
  },
  firefox: {
    id: '',
    transport: 'firefox',
    label: 'Firefox',
    browserHints: ['firefox'],
    devOverrideEnv: 'VITE_EXTENSION_TARGET_FIREFOX_ID',
  },
  safari: {
    id: '',
    transport: 'safari',
    label: 'Safari',
    browserHints: ['safari'],
    devOverrideEnv: 'VITE_EXTENSION_TARGET_SAFARI_ID',
  },
}

function runtimeExtensionTargetId(key) {
  return globalThis.__USAGE_DASHBOARD_CONFIG__?.extensionTargets?.[key] || ''
}

export function getExtensionTargets(env = import.meta.env) {
  return Object.entries(EXTENSION_TARGETS)
    .map(([key, target]) => {
      const runtimeId = runtimeExtensionTargetId(key)
      const overrideId = target.devOverrideEnv ? env?.[target.devOverrideEnv] : ''
      const id = runtimeId || overrideId || target.id
      if (!id) return null
      return {
        key,
        ...target,
        productionId: target.id,
        id,
      }
    })
    .filter(Boolean)
}
