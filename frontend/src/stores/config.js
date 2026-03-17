// frontend/src/stores/config.js
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import api, { getTenantFromHostname } from '@/services/api'

/**
 * Helpers de persistencia (cache por tenant)
 */
const LS_KEYS = {
  theme: 'theme',
  sidebarPreset: 'sidebarPreset',
  lastNombreFantasia: (tenant) => `lastNombreFantasia:${tenant || 'default'}`,
  lastLogoUrl: (tenant) => `lastLogoUrl:${tenant || 'default'}`,
}

const safeGet = (k, fallback = null) => {
  try {
    const v = localStorage.getItem(k)
    return v ?? fallback
  } catch {
    return fallback
  }
}

const safeSet = (k, v) => {
  try {
    if (v === undefined || v === null) localStorage.removeItem(k)
    else localStorage.setItem(k, String(v))
  } catch {}
}

const isProbablyGenericName = (s) => {
  if (!s) return true
  const v = String(s).trim().toLowerCase()
  return v === 'empresa' || v === 'company' || v === 'sin nombre' || v === 'default'
}

const resolveAbsoluteUrl = (maybeUrl) => {
  if (!maybeUrl) return null
  const u = String(maybeUrl).trim()
  if (!u) return null

  if (u.startsWith('http://') || u.startsWith('https://') || u.startsWith('data:')) return u

  // Si viene relativo, lo colgamos de baseURL del backend (api.defaults.baseURL)
  const base = api.defaults.baseURL
  if (base) {
    try {
      return new URL(u, base).toString()
    } catch {}
  }

  try {
    return new URL(u, window.location.origin).toString()
  } catch {
    return u
  }
}

/**
 * Presets de Sidebar
 */
const SIDEBAR_PRESETS = {
  blue: { top: '#1e3a8a', bottom: '#0f172a', accent: '#2563eb', accentRgb: '37, 99, 235' },
  slate: { top: '#1e293b', bottom: '#0f172a', accent: '#64748b', accentRgb: '100, 116, 139' },
  emerald: { top: '#065f46', bottom: '#0f172a', accent: '#10b981', accentRgb: '16, 185, 129' },
  gray: { top: '#374151', bottom: '#111827', accent: '#9ca3af', accentRgb: '156, 163, 175' },
  orange: { top: '#9a3412', bottom: '#0f172a', accent: '#f97316', accentRgb: '249, 115, 22' },
  red: { top: '#7f1d1d', bottom: '#0f172a', accent: '#ef4444', accentRgb: '239, 68, 68' },
}

/** ---- color helpers (para primary-2) ---- */
const clamp01 = (n) => Math.max(0, Math.min(1, n))

const hexToRgb = (hex) => {
  const h = String(hex || '')
    .replace('#', '')
    .trim()
  if (h.length !== 6) return null
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  if ([r, g, b].some((x) => Number.isNaN(x))) return null
  return { r, g, b }
}

const rgbToHex = ({ r, g, b }) =>
  `#${[r, g, b]
    .map((x) =>
      Math.max(0, Math.min(255, Math.round(x)))
        .toString(16)
        .padStart(2, '0'),
    )
    .join('')}`

const mix = (a, b, t) => Math.round(a + (b - a) * clamp01(t))

// lightens color towards white (t=0..1)
const lighten = (hex, t = 0.18) => {
  const rgb = hexToRgb(hex)
  if (!rgb) return hex
  return rgbToHex({
    r: mix(rgb.r, 255, t),
    g: mix(rgb.g, 255, t),
    b: mix(rgb.b, 255, t),
  })
}

const applyCssVars = (presetKey) => {
  const p = SIDEBAR_PRESETS[presetKey] || SIDEBAR_PRESETS.blue
  const root = document.documentElement

  // Sidebar
  root.style.setProperty('--sider-gradient-top', p.top)
  root.style.setProperty('--sider-gradient-bottom', p.bottom)
  root.style.setProperty('--sider-accent', p.accent)
  root.style.setProperty('--accent-rgb', p.accentRgb)

  // ✅ CLAVE: AntD / botones / tokens deben seguir al preset
  // (esto evita que quede fijo en azul)
  root.style.setProperty('--primary', p.accent)
  root.style.setProperty('--primary-2', lighten(p.accent, 0.18))
}

const applyThemeClassNow = (theme) => {
  const t = theme === 'dark' ? 'dark' : 'light'
  const root = document.documentElement
  const body = document.body

  root.classList.remove('theme-light', 'theme-dark')
  root.classList.add(`theme-${t}`)

  // ✅ algunos layouts/vars se leen desde body
  if (body) {
    body.classList.remove('theme-light', 'theme-dark')
    body.classList.add(`theme-${t}`)
  }
}

// Aplicar theme (robusto: si body aún no existe, reintenta al DOMContentLoaded)
const applyThemeClass = (theme) => {
  applyThemeClassNow(theme)
  if (!document.body) {
    window.addEventListener(
      'DOMContentLoaded',
      () => {
        applyThemeClassNow(theme)
      },
      { once: true },
    )
  }
}

function getTenantSlugForCache() {
  const hostTenant = getTenantFromHostname(window.location.hostname)
  if (hostTenant) return hostTenant

  const envDefault = import.meta.env.VITE_DEFAULT_TENANT
  if (envDefault) return String(envDefault).trim() || 'default'

  return 'default'
}

export const useConfigStore = defineStore('config', () => {
  const empresa = ref(null)

  const currentTheme = ref(safeGet(LS_KEYS.theme, 'light'))
  const sidebarPreset = ref(safeGet(LS_KEYS.sidebarPreset, 'blue'))

  // aplicar theme + preset al iniciar
  applyThemeClass(currentTheme.value)
  applyCssVars(sidebarPreset.value)

  const tenantSlug = computed(() => getTenantSlugForCache())

  const nombreFantasia = computed(() => {
    const apiName = empresa.value?.nombre_fantasia || empresa.value?.nombreFantasia
    if (apiName && !isProbablyGenericName(apiName)) return apiName

    const cached = safeGet(LS_KEYS.lastNombreFantasia(tenantSlug.value), '')
    if (cached && !isProbablyGenericName(cached)) return cached

    return 's423 ERP'
  })

  const logoUrl = computed(() => {
    const raw =
      empresa.value?.logo ||
      empresa.value?.logo_url ||
      empresa.value?.url_logo ||
      empresa.value?.logoUrl ||
      null

    const abs = resolveAbsoluteUrl(raw)
    if (abs) return abs

    const cached = safeGet(LS_KEYS.lastLogoUrl(tenantSlug.value), null)
    return cached ? resolveAbsoluteUrl(cached) : null
  })

  const setTheme = (t) => {
    const theme = t === 'dark' ? 'dark' : 'light'
    currentTheme.value = theme
    safeSet(LS_KEYS.theme, theme)
    applyThemeClass(theme)

    // (útil si el preset depende del theme)
    applyCssVars(sidebarPreset.value)
  }

  const setSidebarPreset = (key) => {
    const presetKey = SIDEBAR_PRESETS[key] ? key : 'blue'
    sidebarPreset.value = presetKey
    safeSet(LS_KEYS.sidebarPreset, presetKey)
    applyCssVars(presetKey)
  }

  const cargarConfiguracion = async () => {
    const { data } = await api.get('/api/parametros/configuracion/')
    empresa.value = data

    const apiName = data?.nombre_fantasia || data?.nombreFantasia
    if (apiName && !isProbablyGenericName(apiName)) {
      safeSet(LS_KEYS.lastNombreFantasia(tenantSlug.value), apiName)
    }

    const rawLogo = data?.logo || data?.logo_url || data?.url_logo || data?.logoUrl
    const absLogo = resolveAbsoluteUrl(rawLogo)
    if (absLogo) safeSet(LS_KEYS.lastLogoUrl(tenantSlug.value), absLogo)

    // reaplicar preset (por si el layout se montó antes)
    applyCssVars(sidebarPreset.value)
  }

  return {
    empresa,
    currentTheme,
    sidebarPreset,
    nombreFantasia,
    logoUrl,
    setTheme,
    setSidebarPreset,
    cargarConfiguracion,
  }
})
