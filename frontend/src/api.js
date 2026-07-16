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

async function request(path, options = {}) {
  const token = getAdminToken()
  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {}
  const res = await fetch(`${V1}${path}`, { headers: { 'Content-Type': 'application/json', ...authHeaders, ...(options.headers || {}) }, ...options })
  if (!res.ok) throw new Error(await res.text() || `${res.status} ${res.statusText}`)
  if (res.status === 204) return null
  return res.json()
}
export const api = {
  providers: () => request('/providers'),
  configs: () => request('/configs'),
  createConfig: (payload) => request('/configs', { method: 'POST', body: JSON.stringify(payload) }),
  updateConfig: (id, payload) => request(`/configs/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteConfig: (id) => request(`/configs/${id}`, { method: 'DELETE' }),
  usage: () => request('/usage'),
  history: (id, params = {}) => request(`/configs/${id}/history?${new URLSearchParams(params)}`),
  pollAll: () => request('/poll', { method: 'POST' }),
  pollConfig: (id) => request(`/configs/${id}/poll`, { method: 'POST' }),
  homepage: () => request('/homepage'),
}
