const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'
const V1 = `${API_BASE}/v1`
const TOKEN_STORAGE_KEY = 'usage_dashboard_admin_token'

export function getAdminToken() {
  return localStorage.getItem(TOKEN_STORAGE_KEY) || import.meta.env.VITE_ADMIN_TOKEN || ''
}

export function setAdminToken(token) {
  const trimmed = token.trim()
  if (trimmed) localStorage.setItem(TOKEN_STORAGE_KEY, trimmed)
  else localStorage.removeItem(TOKEN_STORAGE_KEY)
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
    throw new Error(`API request for ${V1}${path} returned invalid JSON: ${err.message}`)
  }
}

async function request(path, options = {}) {
  const token = getAdminToken()
  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {}
  const { headers: optionHeaders = {}, ...fetchOptions } = options
  const res = await fetch(`${V1}${path}`, {
    ...fetchOptions,
    headers: { 'Content-Type': 'application/json', ...authHeaders, ...optionHeaders },
  })
  if (!res.ok) throw new Error(await parseErrorResponse(res))
  if (res.status === 204) return null
  return parseJsonResponse(res, path)
}

export const api = {
  providers: () => request('/providers'),
  configs: () => request('/configs'),
  testConfig: (payload) => request('/configs/test', { method: 'POST', body: JSON.stringify(payload) }),
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
}
