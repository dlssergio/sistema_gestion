// frontend/src/services/dashboard.js
import api from './api'

export async function fetchDashboardMetrics() {
  const { data } = await api.get('/api/dashboard/metrics/')
  return data
}

export async function fetchLatestSales({ limit = 5 } = {}) {
  // Primer intento: con ordering por fecha
  try {
    const { data } = await api.get('/api/comprobantes-venta/', {
      params: { ordering: '-fecha', page_size: limit },
    })
    const rows = Array.isArray(data) ? data : data?.results || []
    return rows.slice(0, limit)
  } catch (e) {
    // Fallback: sin ordering (evita 500 por campo inexistente)
    const { data } = await api.get('/api/comprobantes-venta/', {
      params: { page_size: limit },
    })
    const rows = Array.isArray(data) ? data : data?.results || []
    return rows.slice(0, limit)
  }
}
