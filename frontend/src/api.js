const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'
const V1 = `${API_BASE}/v1`
const TOKEN_STORAGE_KEY = 'usage_dashboard_admin_session_token'

export function getAdminToken() {
  return localStorage.getItem(TOKEN_STORAGE_KEY) || ''
}

export function setAdminToken(token) {
  const trimmed = token.trim()
  if (trimmed) localStorage.setItem(TOKEN_STORAGE_KEY, trimmed)
  else localStorage.removeItem(TOKEN_STORAGE_KEY)
}

export function clearAdminToken() {
  localStorage.removeItem(TOKEN_STORAGE_KEY)
}

async function parseErrorResponse(res) {
  const text = await res.text()
  const contentType = res.headers.get('content-type') || ''
  if (contentType.includes('application/json') && text) {
    try {
      const payload = JSON.parse(text)
      return payload.detail || payload.message || text
    } catch {
      return text
    }
  }
  return text || `${res.status} ${res.statusText}`
}

async function parseJsonResponse(res, path) {
  const text = await res.text()
  if (!text) return null

  const contentType = res.headers.get('content-type') || ''
  if (!contentType.includes('application/json')) {
    const looksLikeHtml = text.trimStart().startsWith('<')
    throw new Error(
      looksLikeHtml
        ? `API request for ${V1}${path} returned HTML instead of JSON. Check VITE_API_BASE_URL/nginx proxy routing; the frontend is probably hitting the SPA fallback.`
        : `API request for ${V1}${path} returned ${contentType || 'an unknown content type'} instead of JSON.`,
    )
  }

  try {
    return JSON.parse(text)
  } catch (err) {
    throw new Error(`API request for ${V1}${path} returned invalid JSON: ${err.message}`, { cause: err })
  }
}

export const UNAUTHORIZED_EVENT = 'usage-dashboard:unauthorized'

async function request(path, options = {}) {
  const token = getAdminToken()
  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {}
  const { headers: optionHeaders = {}, ...fetchOptions } = options
  const res = await fetch(`${V1}${path}`, {
    ...fetchOptions,
    headers: { 'Content-Type': 'application/json', ...authHeaders, ...optionHeaders },
  })
  if (res.status === 401 && token) {
    // The stored admin session token is no longer valid. Clear it and tell the app to
    // log the user out instead of surfacing an "Invalid bearer token" banner.
    clearAdminToken()
    window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT))
  }
  if (!res.ok) throw new Error(await parseErrorResponse(res))
  if (res.status === 204) return null
  return parseJsonResponse(res, path)
}

async function authRequest(path, payload) {
  return request(path, { method: 'POST', body: JSON.stringify(payload) })
}

export const api = {
  authStatus: () => request('/auth/status'),
  setupAuth: (payload) => authRequest('/auth/setup', payload),
  login: (payload) => authRequest('/auth/login', payload),
  requestPasswordReset: () => request('/auth/reset/request', { method: 'POST' }),
  completePasswordReset: (payload) => authRequest('/auth/reset/complete', payload),
  logout: () => request('/auth/logout', { method: 'POST' }),
  apiTokens: () => request('/api-tokens'),
  createApiToken: (payload) => request('/api-tokens', { method: 'POST', body: JSON.stringify(payload) }),
  revokeApiToken: (id) => request(`/api-tokens/${id}/revoke`, { method: 'POST' }),
  providers: () => request('/providers'),
  configs: () => request('/configs'),
  testConfig: (payload) => request('/configs/test', { method: 'POST', body: JSON.stringify(payload) }),
  startCodexDeviceOAuth: () => request('/codex/oauth/device/start', { method: 'POST' }),
  pollCodexDeviceOAuth: (flowId, payload = {}) => request(`/codex/oauth/device/${encodeURIComponent(flowId)}/poll`, { method: 'POST', body: JSON.stringify(payload) }),
  startCodexBrowserOAuth: () => request('/codex/oauth/browser/start', { method: 'POST' }),
  completeCodexBrowserOAuth: (flowId, payload) => request(`/codex/oauth/browser/${encodeURIComponent(flowId)}/complete`, { method: 'POST', body: JSON.stringify(payload) }),
  createConfig: (payload) => request('/configs', { method: 'POST', body: JSON.stringify(payload) }),
  updateConfig: (id, payload) => request(`/configs/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  reorderConfigs: (configIds) => request('/configs/order', { method: 'PATCH', body: JSON.stringify({ config_ids: configIds }) }),
  deleteConfig: (id) => request(`/configs/${id}`, { method: 'DELETE' }),
  usage: () => request('/usage'),
  history: (id, params = {}) => request(`/configs/${id}/history?${new URLSearchParams(params)}`),
  pollAll: () => request('/poll', { method: 'POST' }),
  pollConfig: (id) => request(`/configs/${id}/poll`, { method: 'POST' }),
  pollStatus: () => request('/poll/status'),
  homepage: () => request('/homepage'),
  analyticsSummary: () => request('/analytics/summary'),
  analyticsOverview: (params = {}) => request(`/analytics/overview?${new URLSearchParams(params)}`),
  analyticsProvider: (id) => request(`/analytics/providers/${id}`),
  analyticsTimeseries: (id, params = {}) => request(`/analytics/providers/${id}/timeseries?${new URLSearchParams(params)}`),
  analyticsDaily: (id, params = {}) => request(`/analytics/providers/${id}/daily?${new URLSearchParams(params)}`),
  analyticsHourly: (id, params = {}) => request(`/analytics/providers/${id}/hourly?${new URLSearchParams(params)}`),
  analyticsForecast: (id, params = {}) => request(`/analytics/providers/${id}/forecast?${new URLSearchParams(params)}`),
  analyticsComparison: (id, params = {}) => request(`/analytics/providers/${id}/comparison?${new URLSearchParams(params)}`),
  analyticsCapacity: (id, params = {}) => request(`/analytics/providers/${id}/capacity?${new URLSearchParams(params)}`),
  analyticsAttribution: (id, params = {}) => request(`/analytics/providers/${id}/attribution?${new URLSearchParams(params)}`),
  hermesBreakdown: (params = {}) => request(`/analytics/hermes?${new URLSearchParams(params)}`),
  dataSourceCatalog: () => request('/datasources'),
  dataSourceConfigs: () => request('/datasources/configs'),
  createDataSourceConfig: (payload) => request('/datasources/configs', { method: 'POST', body: JSON.stringify(payload) }),
  updateDataSourceConfig: (id, payload) => request(`/datasources/configs/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteDataSourceConfig: (id) => request(`/datasources/configs/${id}`, { method: 'DELETE' }),
  testDataSource: (id) => request(`/datasources/configs/${id}/test`, { method: 'POST' }),
  syncDataSource: (id) => request(`/datasources/configs/${id}/sync`, { method: 'POST' }),
  inspectDataSource: (id, params = {}) => request(`/datasources/configs/${id}/observations?${new URLSearchParams(params)}`),
  dataSourceStatus: (id) => request(`/datasources/configs/${id}/status`),
  dataSourceProviderMappings: (id) => request(`/datasources/configs/${id}/provider-mappings`),
  updateDataSourceProviderMappings: (id, payload) => request(`/datasources/configs/${id}/provider-mappings`, { method: 'PUT', body: JSON.stringify(payload) }),
}
