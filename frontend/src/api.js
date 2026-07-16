const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'
const V1 = `${API_BASE}/v1`
async function request(path, options = {}) {
  const res = await fetch(`${V1}${path}`, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options })
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
  pollAll: () => request('/poll', { method: 'POST' }),
  pollConfig: (id) => request(`/configs/${id}/poll`, { method: 'POST' }),
  homepage: () => request('/homepage'),
}
