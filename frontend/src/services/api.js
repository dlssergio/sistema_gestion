// frontend/src/services/api.js
import axios from 'axios'

/**
 * Multi-tenant real por hostname (Opción A - recomendada):
 * - PROD: si estás en https://cliente1.tudominio.com -> API = https://cliente1.tudominio.com/api
 * - DEV:
 *   - si estás en http://localhost:5173 -> API = http://{VITE_DEFAULT_TENANT}.localhost:8000/api
 *   - si estás en http://tenant1.localhost:5173 -> API = http://tenant1.localhost:8000/api
 *
 * Opción B (comentada): API centralizada en https://api.tudominio.com
 */

// === Helpers ===============================================================

function getTenantFromHostname(hostname) {
  // "cliente1.tudominio.com" => "cliente1"
  // "tenant1.localhost" => "tenant1"
  // "localhost" => null
  if (!hostname) return null
  const host = String(hostname).trim().toLowerCase()
  if (!host || host === 'localhost') return null

  const first = host.split('.')[0]
  if (!first || first === 'www') return null
  return first
}

function computeApiBaseUrl() {
  // 1) Override explícito por env (si lo definís, manda siempre)
  // Ej: VITE_API_BASE_URL=http://tenant1.localhost:8000
  const envBase = import.meta.env.VITE_API_BASE_URL
  if (envBase) return String(envBase).replace(/\/+$/, '')

  const { protocol, hostname, port } = window.location

  // 2) DEV: Vite en localhost (5173) -> backend en {tenant}.localhost:8000
  const isLocalhost = hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '0.0.0.0'

  if (isLocalhost) {
    const defaultTenant = import.meta.env.VITE_DEFAULT_TENANT || 'tenant1'
    return `http://${defaultTenant}.localhost:8000`
  }

  // 3) DEV: si corrés Vite en tenant1.localhost:5173 -> backend en tenant1.localhost:8000
  // (usamos el mismo hostname, cambiando el puerto a 8000)
  const isLocalhostSubdomain = hostname.endsWith('.localhost')
  if (isLocalhostSubdomain) {
    return `http://${hostname}:8000`
  }

  // 4) PROD (Opción A): misma origin (mismo subdominio) -> API bajo /api
  // baseURL debe ser origin (sin /api) porque axios luego concatena /api/... en las llamadas
  // (nosotros llamamos api.get('/api/...'))
  const origin =
    port && port !== '80' && port !== '443'
      ? `${protocol}//${hostname}:${port}`
      : `${protocol}//${hostname}`
  return origin
}

// === BaseURL final =========================================================

const API_BASE_URL = computeApiBaseUrl()

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

// --- Request: agrega Bearer token ---
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('accessToken')
    if (token) {
      config.headers = config.headers || {}
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

// --- Response: refresh automático si expira el access ---
let isRefreshing = false
let refreshQueue = []

function resolveQueue(error, token = null) {
  refreshQueue.forEach((p) => {
    if (error) p.reject(error)
    else p.resolve(token)
  })
  refreshQueue = []
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config
    const status = error?.response?.status

    // Evitar loop infinito
    if (!original || original._retry) return Promise.reject(error)

    if (status === 401) {
      const refresh = localStorage.getItem('refreshToken')
      if (!refresh) return Promise.reject(error)

      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          refreshQueue.push({ resolve, reject })
        }).then((newAccess) => {
          original._retry = true
          original.headers = original.headers || {}
          original.headers.Authorization = `Bearer ${newAccess}`
          return api(original)
        })
      }

      isRefreshing = true
      original._retry = true

      try {
        // IMPORTANTE:
        // - En Opción A (misma origin), esto pega a `${origin}/api/token/refresh/`
        // - En DEV, pega a `http://tenantX.localhost:8000/api/token/refresh/`
        //
        // Opción B (API centralizada): descomentá estas líneas y ajustá VITE_API_CENTRAL
        // const API_CENTRAL = import.meta.env.VITE_API_CENTRAL || 'https://api.tudominio.com'
        // const refreshUrl = `${API_CENTRAL.replace(/\/+$/, '')}/api/token/refresh/`
        // const { data } = await axios.post(refreshUrl, { refresh })

        const { data } = await axios.post(`${API_BASE_URL}/api/token/refresh/`, { refresh })

        const newAccess = data?.access
        if (!newAccess) throw new Error('No vino access en token/refresh')

        localStorage.setItem('accessToken', newAccess)
        resolveQueue(null, newAccess)

        original.headers = original.headers || {}
        original.headers.Authorization = `Bearer ${newAccess}`
        return api(original)
      } catch (e) {
        resolveQueue(e, null)
        localStorage.removeItem('accessToken')
        localStorage.removeItem('refreshToken')
        return Promise.reject(e)
      } finally {
        isRefreshing = false
      }
    }

    return Promise.reject(error)
  },
)

export default api
export { api, API_BASE_URL, getTenantFromHostname }
