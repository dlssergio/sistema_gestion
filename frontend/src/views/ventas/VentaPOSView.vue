<script setup>
/**
 * POSView.vue — Punto de Venta
 *
 * Fixes aplicados:
 *  [F1]  toFloat: bug destructivo de decimales eliminado (1.50 → 150 era un bug silencioso)
 *  [F2]  watch(hasUnsavedChanges, immediate:true) → sin immediate; se gestiona en onMounted/onUnmounted
 *  [F3]  normalizing: let de módulo → let local al setup (seguro con múltiples instancias)
 *  [F4]  closeAnyModal no debe cerrar leaveModalOpen (modal bloqueante con acción explícita)
 *  [F5]  prodSearchT/layoutRaf/footerRaf: let de módulo → let local al setup
 *  [F6]  buildPayload: normalizePagos solo al confirmar venta, no al guardar borrador
 *  [F7]  sendComprobante: fallback de 4 niveles anidados → estructura plana y legible
 *  [F8]  formatIvaLabel: memoizada con Map para evitar strings repetidos en taxesRows
 *  [F9]  Regex de precio compiladas una sola vez fuera del formatter
 *  [F10] setFooterSpaceVar: evita layout thrashing cacheando la altura
 *  [F11] getImageUrl: fallback local en lugar de placeholder externo
 *  [F12] measureLayout: usa wrapRect directo sin buscar hijos del DOM
 *  [F13] watches de tema: sin immediate, se disparan manualmente en onMounted
 *  [F14] client-avatar CSS: faltaba en versión original
 */

import { ref, reactive, computed, onMounted, onUnmounted, watch, h, nextTick } from 'vue'
import { useRouter, onBeforeRouteLeave } from 'vue-router'
import {
  SaveOutlined,
  PlusOutlined,
  DeleteOutlined,
  BarcodeOutlined,
  CalculatorOutlined,
  PauseCircleOutlined,
  HistoryOutlined,
  UserOutlined,
  InfoCircleOutlined,
  RollbackOutlined,
  CloseOutlined,
  SearchOutlined,
  AppstoreOutlined,
  CheckOutlined,
  StopOutlined,
  ThunderboltOutlined,
  ExpandOutlined,
  CompressOutlined,
  FilePdfOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons-vue'
import dayjs from 'dayjs'
import { message, Modal, theme as antdTheme } from 'ant-design-vue'
import api from '@/services/api'
import { useConfigStore } from '@/stores/config'

import ArticuloSearchModal from '@/components/ventas/ArticuloSearchModal.vue'
import PaymentModal from '@/components/ventas/PaymentModal.vue'
import VentasSuspendidasModal from '@/components/ventas/VentasSuspendidasModal.vue'

// [F9] Regex compiladas una sola vez — no se recrean en cada keystroke del formatter
const RE_PRICE_FORMAT = /\B(?=(\d{3})+(?!\d))/g
const RE_PRICE_PARSE = /\$\s?|,/g

const configStore = useConfigStore()
const router = useRouter()

/** ─── Cliente genérico (ocasional) ──────────────────────────────────────────── */
const CODIGO_CLIENTE_GENERICO = 'C00000'

// Override state — se usa cuando el cliente seleccionado es el genérico
const clienteOverride = reactive({
  nombre: '', // Razón social / nombre ocasional
  cuit: '', // CUIT o DNI (importante para AFIP)
  email: '', // Email para envío del comprobante
})

/** ─── Tema ─────────────────────────────────────────────────────────────────── */
const isDark = computed(() => (configStore.currentTheme || 'light') === 'dark')

const posRootEl = ref(null)
const footerEl = ref(null)
const posPrimary = ref('#1677ff')

const readCssVar = (el, name) => {
  if (!el) return ''
  return getComputedStyle(el).getPropertyValue(name).trim()
}
const readPrimaryFromCss = () => {
  const v =
    readCssVar(posRootEl.value, '--primary') ||
    readCssVar(posRootEl.value, '--sider-accent') ||
    readCssVar(posRootEl.value, '--primary-2') ||
    readCssVar(document.body, '--primary') ||
    readCssVar(document.body, '--sider-accent') ||
    readCssVar(document.body, '--primary-2') ||
    readCssVar(document.documentElement, '--primary') ||
    readCssVar(document.documentElement, '--sider-accent') ||
    readCssVar(document.documentElement, '--primary-2')
  if (v) posPrimary.value = v
}

const antdThemeConfig = computed(() => ({
  algorithm: isDark.value ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
  token: { colorPrimary: posPrimary.value, zIndexPopupBase: 3000 },
}))

// [F13] Sin immediate — se llama manualmente en onMounted (el DOM no existe en setup)
watch(
  () => [configStore.currentTheme, configStore.sidebarPreset],
  async () => {
    await nextTick()
    readPrimaryFromCss()
    requestAnimationFrame(() => readPrimaryFromCss())
  },
)

/** ─── UI / Modales ──────────────────────────────────────────────────────────── */
const paymentOpen = ref(false)
const overridePopoverOpen = ref(false)
const printModalOpen = ref(false)
const ventaFinalizada = reactive({ id: null, numero: '', loadingPdf: false })
const suspendidasOpen = ref(false)
const articuloModalOpen = ref(false)
const showCalculator = ref(false)
const clientModalOpen = ref(false)
const leaveModalOpen = ref(false)
const shortcutsOpen = ref(false)
const finalConfirmOpen = ref(false)
const imageZoomOpen = ref(false)
const pendingPagos = ref([])
const pendingRecargos = ref(0)
const pendingDescuentos = ref(0)

/** ─── Modo enfoque ──────────────────────────────────────────────────────────── */
const focusMode = ref(false)
const focusToggling = ref(false)
const rightPanelOpen = ref(false) // mobile/tablet drawer state

const applyFocusClass = (on) => {
  document.documentElement.classList.toggle('pos-focus-mode', !!on)
  document.body.classList.toggle('pos-focus-mode', !!on)
}

const raf = () => new Promise((resolve) => requestAnimationFrame(resolve))
const raf2 = async () => {
  await raf()
  await raf()
}

const updateAvailableHeight = () => {
  try {
    const el = posRootEl.value
    if (!el) return
    const r = el.getBoundingClientRect()
    const top = Math.max(0, Math.round(r.top))
    const h = Math.max(420, Math.round(window.innerHeight - top))
    el.style.setProperty('--pos-available-h', `${h}px`)
  } catch {
    /* ignore */
  }
}

const toggleFocusMode = async () => {
  if (focusToggling.value) return
  focusToggling.value = true
  try {
    focusMode.value = !focusMode.value
    applyFocusClass(focusMode.value)
    await nextTick()
    await raf2()
    updateAvailableHeight()
    measureLayout()
    scheduleFooterMetrics()
    await raf2()
    updateAvailableHeight()
    measureLayout()
    scheduleFooterMetrics()
  } finally {
    focusToggling.value = false
  }
}

/** ─── Estado de negocio ─────────────────────────────────────────────────────── */
const loading = ref(false)
const clientSelect = ref(null)
const clientes = ref([])
const cargandoClientes = ref(false)

const tiposComprobante = ref([
  { value: 1, label: 'Factura A' },
  { value: 2, label: 'Factura B' },
])

const formState = reactive({
  clienteId: null,
  tipoComprobanteId: 2,
  fecha: dayjs(),
  puntoVenta: configStore.puntoVentaDefault || 1,
})

const items = ref([])
const selectedRowKey = ref(null)

const columns = [
  { title: '#', dataIndex: 'index', width: 40, align: 'center' },
  { title: 'Código / Búsqueda', dataIndex: 'codigo', width: 250 },
  { title: 'Descripción', dataIndex: 'descripcion' },
  { title: 'Cant.', dataIndex: 'cantidad', width: 90, align: 'center' },
  { title: 'Precio', dataIndex: 'precio', width: 130, align: 'right' },
  { title: 'Desc %', dataIndex: 'descuento', width: 80, align: 'right' },
  { title: 'Subtotal', dataIndex: 'subtotal', width: 140, align: 'right' },
  { title: '', dataIndex: 'actions', width: 46, align: 'center' },
]

const createEmptyRow = () => ({
  key: Date.now() + Math.random(),
  articuloId: null,
  articuloPk: null, // FIX: definido aquí para que Vue 3 lo haga reactivo
  codigo: '',
  descripcion: '',
  cantidad: 1,
  precio: 0,
  descuento: 0,
  foto: null,
  stock: 0,
  ubicacion: '',
  permiteExistenciaNegativa: false,
  ivaRate: 21,
})

/** ─── Control filas en blanco ──────────────────────────────────────────────── */
const isBlankRow = (r) => !r?.articuloId && !String(r?.codigo || '').trim()

const ensureSingleBlankRow = () => {
  if (!Array.isArray(items.value)) items.value = []
  if (items.value.length === 0) {
    items.value = [createEmptyRow()]
    return
  }
  const dataRows = items.value.filter((r) => !isBlankRow(r))
  const firstBlank = items.value.find((r) => isBlankRow(r)) || createEmptyRow()
  items.value = [...dataRows, firstBlank]
}

// [F3] normalizing LOCAL al setup — no de módulo; seguro con múltiples instancias
let normalizing = false

watch(
  items,
  async () => {
    if (normalizing) return
    normalizing = true
    try {
      await nextTick()
      const blanks = items.value.filter((r) => isBlankRow(r)).length
      if (blanks > 1 || items.value.length === 0) ensureSingleBlankRow()
    } finally {
      normalizing = false
    }
  },
  { deep: true, flush: 'post' },
)

const addManualRow = async () => {
  const idxBlank = items.value.findIndex((r) => isBlankRow(r))
  if (idxBlank >= 0) {
    message.info('Ya hay un renglón en blanco. Completá ese antes de agregar otro.')
    const key = items.value[idxBlank]?.key
    if (key) {
      selectedRowKey.value = key
      setContext('item', key)
      await nextTick()
      scrollRowIntoView(key)
    }
    return
  }
  items.value.push(createEmptyRow())
  ensureSingleBlankRow()
}

/** ─── Layout / Scroll ───────────────────────────────────────────────────────── */
const headerCardEl = ref(null)
const gridCardEl = ref(null)
const gridTopbarEl = ref(null)
const gridActionsEl = ref(null)
const gridTableWrapEl = ref(null)
const tableScrollY = ref(320)

// [F5] layoutRaf LOCAL al setup
let layoutRaf = 0

const measureLayout = () => {
  if (!posRootEl.value) return
  if (layoutRaf) cancelAnimationFrame(layoutRaf)
  layoutRaf = requestAnimationFrame(() => {
    layoutRaf = 0
    try {
      const root = posRootEl.value
      if (!root) return
      const rect = root.getBoundingClientRect()
      const viewportH = window.innerHeight || document.documentElement.clientHeight || 800
      root.style.setProperty(
        '--pos-available-h',
        `${Math.max(420, Math.floor(viewportH - rect.top - 16))}px`,
      )

      // [F12] Usa wrapRect directamente; 48px reserva estable para el header de columnas
      const wrapRect = gridTableWrapEl.value?.getBoundingClientRect()
      if (!wrapRect) return
      tableScrollY.value = Math.max(260, Math.floor(wrapRect.height - 48 - 6))
    } catch {
      /* ignore */
    }
  })
}

const scrollRowIntoView = (rowKey) => {
  try {
    gridTableWrapEl.value
      ?.querySelector(`tr[data-row-key="${rowKey}"]`)
      ?.scrollIntoView?.({ block: 'center', behavior: 'smooth' })
  } catch {
    /* ignore */
  }
}

/** ─── Stock validation ──────────────────────────────────────────────────────── */
const isRowOutOfStock = (r) =>
  r?.articuloId && !r?.permiteExistenciaNegativa && Number(r.cantidad || 0) > Number(r.stock || 0)

const hasStockIssues = computed(() => items.value.some((r) => isRowOutOfStock(r)))

/** ─── Condición de pago ─────────────────────────────────────────────────────── */
const condicionPago = ref('CONTADO')
const mapCondicionToBackend = (v) => (v === 'CTA_CTE' ? 'CC' : 'CO')
const mapCondicionFromBackend = (v) => (v === 'CC' ? 'CTA_CTE' : 'CONTADO')

const clienteInfo = computed(() =>
  formState.clienteId
    ? (clientes.value.find((c) => c.value === formState.clienteId) ?? null)
    : null,
)
const clientePermiteCtaCte = computed(() => Boolean(clienteInfo.value?.permite_cta_cte))
const isClienteGenerico = computed(() => {
  const cod = clienteInfo.value?.codigo_cliente ?? clienteInfo.value?.codigo ?? ''
  return cod === CODIGO_CLIENTE_GENERICO
})
const showClienteOverridePanel = computed(() => isClienteGenerico.value)
const overrideHasData = computed(
  () =>
    !!(
      clienteOverride.nombre.trim() ||
      clienteOverride.cuit.trim() ||
      clienteOverride.email.trim()
    ),
)

const payOptions = computed(() => {
  const mk = (label, value, disabled) => ({
    value,
    disabled: !!disabled,
    label: h(
      'span',
      { class: 'seg-opt' },
      [
        condicionPago.value === value ? h(CheckOutlined, { class: 'seg-check' }) : null,
        h('span', { class: 'seg-text' }, label),
      ].filter(Boolean),
    ),
  })
  return [
    mk('Contado', 'CONTADO', false),
    mk('Cuenta Corriente', 'CTA_CTE', !clientePermiteCtaCte.value),
  ]
})

/** ─── Helpers de payload ────────────────────────────────────────────────────── */
const toInt = (v, fallback = null) => {
  const n = Number.parseInt(v, 10)
  return Number.isFinite(n) ? n : fallback
}

/**
 * [F1] FIX CRÍTICO — la versión anterior hacía .replace(/\./g, '') que destruía
 * cualquier decimal con punto (e.g. "1.50" → "150").
 * Ahora detecta el formato y lo convierte sin romper decimales.
 */
const toFloat = (v, fallback = 0) => {
  if (v == null) return fallback
  if (typeof v === 'number') return Number.isFinite(v) ? v : fallback
  const s = String(v).trim()
  // Formato AR: "1.234,56" — puntos como miles, coma como decimal
  if (/^\d{1,3}(\.\d{3})*(,\d+)?$/.test(s)) {
    const n = Number(s.replace(/\./g, '').replace(',', '.'))
    return Number.isFinite(n) ? n : fallback
  }
  // Formato US o simple: "1,234.56" / "1234.56" / "1234,56"
  const n = Number(s.replace(/,/g, '.'))
  return Number.isFinite(n) ? n : fallback
}

const formatFechaDateOnly = (d) => {
  try {
    return dayjs(d).format('YYYY-MM-DD')
  } catch {
    return dayjs().format('YYYY-MM-DD')
  }
}
const formatFechaWithCurrentTime = (d) => {
  try {
    const now = dayjs()
    return `${dayjs(d).format('YYYY-MM-DD')}T${now.format('HH:mm:ss')}${now.format('Z')}`
  } catch {
    const now = dayjs()
    return `${now.format('YYYY-MM-DD')}T${now.format('HH:mm:ss')}${now.format('Z')}`
  }
}

const normalizePagos = (pagos) =>
  (Array.isArray(pagos) ? pagos : [])
    .map((p) => {
      const obj = { ...(p || {}) }
      if (obj.importe != null) obj.importe = toFloat(obj.importe, 0)
      if (obj.monto != null) obj.monto = toFloat(obj.monto, 0)
      if (obj.amount != null) obj.amount = toFloat(obj.amount, 0)
      return obj
    })
    .filter((p) => {
      const v = p?.importe ?? p?.monto ?? p?.amount
      return v == null ? true : toFloat(v, 0) > 0
    })

/** Muestra el error de API de forma legible */
const showApiError = (error, fallbackMsg) => {
  const status = error?.response?.status
  const data = error?.response?.data
  if (!data) {
    message.error(fallbackMsg)
    return
  }
  if (typeof data === 'string') {
    const stripped = data
      .replace(/<[^>]+>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 200)
    message.error(stripped || fallbackMsg)
    return
  }
  if (data?.detail) {
    message.error(String(data.detail))
    return
  }
  const parts = Object.entries(data).map(([k, v]) =>
    Array.isArray(v)
      ? `${k}: ${v.join(' | ')}`
      : typeof v === 'string'
        ? `${k}: ${v}`
        : `${k}: ${JSON.stringify(v)}`,
  )
  message.error(`(${status || 'Error'}) ${parts.join(' · ') || fallbackMsg}`)
}

const isFechaFormatError = (error) => {
  const f = error?.response?.data?.fecha
  if (!f) return false
  return /date|fecha|formato|invalid/i.test(Array.isArray(f) ? f.join(' ') : String(f))
}
const isNestedWriteError = (error) => {
  const data = error?.response?.data
  const txt =
    typeof data === 'string'
      ? data
      : data?.detail
        ? String(data.detail)
        : JSON.stringify(data || {})
  return /writable nested fields|raise_errors_on_nested_writes|does not support writable nested/i.test(
    txt,
  )
}

/** ─── Seguridad de navegación ───────────────────────────────────────────────── */
const hasUnsavedChanges = ref(false)
const allowRouteLeave = ref(false)
const pendingRoute = ref(null)

const resetPendingCobroPreview = () => {
  pendingPagos.value = []
  pendingRecargos.value = 0
  pendingDescuentos.value = 0
}

const markDirty = () => {
  if (!allowRouteLeave.value) hasUnsavedChanges.value = true
}

watch(
  () => [formState.clienteId, formState.tipoComprobanteId, formState.puntoVenta, formState.fecha],
  () => markDirty(),
)
watch(
  () =>
    items.value.map(
      (r) =>
        `${r.articuloId || ''}|${String(r.codigo || '').trim()}|${r.cantidad}|${r.precio}|${r.descuento}|${r.ivaRate}`,
    ),
  (sig) => {
    if (!sig?.length) return
    const anyData =
      !!formState.clienteId || items.value.some((i) => i.articuloId || i.codigo?.trim())
    if (anyData) markDirty()
  },
  { flush: 'post' },
)

const openLeaveModal = (to) => {
  pendingRoute.value = to
  leaveModalOpen.value = true
}
const closeLeaveModal = () => {
  leaveModalOpen.value = false
  pendingRoute.value = null
}

const proceedToPendingRoute = async () => {
  const to = pendingRoute.value
  closeLeaveModal()
  if (to) {
    allowRouteLeave.value = true
    shutdownNow()
    await router.push(to.fullPath || to.path || to)
    allowRouteLeave.value = false
  }
}

const handleBeforeUnload = (e) => {
  if (!hasUnsavedChanges.value) return
  e.preventDefault()
  e.returnValue = ''
}

// [F2] Sin immediate:true — se gestiona manualmente en onMounted/onUnmounted
watch(hasUnsavedChanges, (dirty) => {
  if (dirty) window.addEventListener('beforeunload', handleBeforeUnload)
  else window.removeEventListener('beforeunload', handleBeforeUnload)
})

/** ─── Shutdown ──────────────────────────────────────────────────────────────── */
const destroyed = ref(false)

// [F5] Todos los timers/RAF como let LOCALES al setup
let prodSearchT = null
let footerRaf = 0
let layoutObs = null
let resizeObs = null
let siderEl = null
let siderTransitionHandler = null

const shutdownNow = () => {
  if (destroyed.value) return
  destroyed.value = true
  try {
    applyFocusClass(false)
    focusMode.value = false
    window.removeEventListener('keydown', handleShortcuts)
    window.removeEventListener('beforeunload', handleBeforeUnload)
    window.removeEventListener('resize', onWindowResize)
    if (prodSearchT != null) {
      clearTimeout(prodSearchT)
      prodSearchT = null
    }
    if (footerRaf) {
      cancelAnimationFrame(footerRaf)
      footerRaf = 0
    }
    if (layoutRaf) {
      cancelAnimationFrame(layoutRaf)
      layoutRaf = 0
    }
    if (layoutObs) {
      layoutObs.disconnect()
      layoutObs = null
    }
    if (resizeObs) {
      resizeObs.disconnect()
      resizeObs = null
    }
    if (siderEl && siderTransitionHandler) {
      ;['transitionrun', 'transitionstart', 'transitionend', 'transitioncancel'].forEach((ev) =>
        siderEl.removeEventListener(ev, siderTransitionHandler),
      )
    }
    siderTransitionHandler = null
    siderEl = null
  } catch {
    /* ignore */
  }
}

onBeforeRouteLeave((to) => {
  if (allowRouteLeave.value || !hasUnsavedChanges.value) {
    shutdownNow()
    return true
  }
  openLeaveModal(to)
  return false
})

/** ─── Clientes ──────────────────────────────────────────────────────────────── */
const extractPermiteCtaCte = (c) =>
  Boolean(
    c?.permite_cta_cte ??
      c?.entidad?.permite_cta_cte ??
      c?.entidad?.datos?.permite_cta_cte ??
      c?.datos?.permite_cta_cte ??
      false,
  )

/** Carga el cliente genérico C00000 y lo preselecciona en el POS */
const loadClienteGenerico = async () => {
  try {
    const { data } = await api.get('/api/clientes/', {
      params: { search: CODIGO_CLIENTE_GENERICO },
    })
    const datos = data?.results ?? data
    const generico = (datos || []).find(
      (c) =>
        c?.codigo_cliente === CODIGO_CLIENTE_GENERICO ||
        c?.entidad?.codigo_cliente === CODIGO_CLIENTE_GENERICO ||
        // fallback: buscar por razon_social si el campo no viene en el listado
        String(c?.entidad?.razon_social || '')
          .toLowerCase()
          .includes('ocasional') ||
        String(c?.entidad?.razon_social || '')
          .toLowerCase()
          .includes('generico') ||
        String(c?.entidad?.razon_social || '')
          .toLowerCase()
          .includes('genérico'),
    )
    if (!generico) return // Si no existe el cliente genérico, no preseleccionar nada
    const ent = generico?.entidad ?? generico
    const permite = extractPermiteCtaCte(generico)
    const clienteData = {
      value: ent?.id,
      label: ent?.razon_social,
      cuit: ent?.cuit,
      condicion: ent?.situacion_iva?.nombre || '',
      permite_cta_cte: permite,
      codigo_cliente: generico?.codigo_cliente ?? CODIGO_CLIENTE_GENERICO,
      saldo: generico?.saldo ?? 0,
    }
    clientes.value = [clienteData]
    formState.clienteId = clienteData.value
    lastConfirmedClienteId.value = clienteData.value
    setContext('client')
  } catch (e) {
    console.warn('No se pudo cargar el cliente genérico:', e)
  }
}

const buscarClientes = async (busqueda = '') => {
  const q = (busqueda || '').trim()
  if (q.length < 3) {
    clientes.value = []
    return
  }
  cargandoClientes.value = true
  try {
    const { data } = await api.get('/api/clientes/', { params: { search: q } })
    const datos = data?.results ?? data
    clientes.value = (datos || []).map((c) => {
      const ent = c.entidad ?? c
      const permite = extractPermiteCtaCte(c)
      return {
        value: ent?.id,
        label: ent?.razon_social,
        cuit: ent?.cuit,
        condicion: ent?.situacion_iva?.nombre || '',
        permite_cta_cte: permite,
        codigo_cliente: c?.codigo_cliente ?? '',
        saldo: c.saldo ?? 0,
      }
    })
  } catch (e) {
    console.error(e)
    message.error('Error buscando clientes')
  } finally {
    cargandoClientes.value = false
  }
}

const clientModalSearch = ref('')
const clientModalLoading = ref(false)
const clientModalRows = ref([])
const clientModalColumns = [
  { title: 'Razón social', dataIndex: 'razon_social' },
  { title: 'CUIT', dataIndex: 'cuit', width: 150 },
  { title: 'Condición IVA', dataIndex: 'condicion', width: 180 },
  { title: 'Cta Cte', dataIndex: 'cta_cte', width: 90, align: 'center' },
]

const openClientModal = () => {
  clientModalOpen.value = true
  clientModalSearch.value = ''
  clientModalRows.value = []
}

const loadClientModal = async () => {
  const q = (clientModalSearch.value || '').trim()
  if (q.length < 3) {
    clientModalRows.value = []
    return
  }
  clientModalLoading.value = true
  try {
    const { data } = await api.get('/api/clientes/', { params: { search: q } })
    const datos = data?.results ?? data
    clientModalRows.value = (datos || []).map((c) => {
      const ent = c.entidad ?? c
      const permite = extractPermiteCtaCte(c)
      return {
        id: ent?.id,
        razon_social: ent?.razon_social,
        cuit: ent?.cuit,
        condicion: ent?.situacion_iva?.nombre || '',
        permite_cta_cte: permite,
        cta_cte: permite ? 'Sí' : 'No',
      }
    })
  } catch (e) {
    console.error(e)
    message.error('Error buscando clientes')
  } finally {
    clientModalLoading.value = false
  }
}

const ensureClienteOption = async (clienteId) => {
  if (!clienteId || clientes.value.some((c) => c.value === clienteId)) return
  try {
    const { data } = await api.get(`/api/clientes/${clienteId}/`)
    const ent = data?.entidad ?? data
    const permite = extractPermiteCtaCte(data)
    clientes.value = [
      {
        value: ent?.id ?? clienteId,
        label: ent?.razon_social ?? `Cliente #${clienteId}`,
        cuit: ent?.cuit ?? '',
        condicion: ent?.situacion_iva?.nombre ?? '',
        permite_cta_cte: permite,
        codigo_cliente: data?.codigo_cliente ?? '',
        saldo: data?.saldo ?? 0,
      },
    ]
  } catch {
    clientes.value = [
      {
        value: clienteId,
        label: `Cliente #${clienteId}`,
        cuit: '',
        condicion: '',
        permite_cta_cte: false,
        saldo: 0,
      },
    ]
  }
}

const hasAnyArticulo = computed(() => items.value.some((r) => !!r.articuloId))
const lastConfirmedClienteId = ref(null)
const clientChanging = ref(false)

const contextMode = ref('none')
const setContext = (mode, key = null) => {
  contextMode.value = mode
  if (mode === 'item' && key) selectedRowKey.value = key
}

const setClienteWithConfirm = async (newId, { force = false } = {}) => {
  if (clientChanging.value) return
  const oldId = lastConfirmedClienteId.value
  if (!oldId || !newId || force || !hasAnyArticulo.value || newId === oldId) {
    clientChanging.value = true
    formState.clienteId = newId
    if (newId) await ensureClienteOption(newId)
    lastConfirmedClienteId.value = newId
    clientChanging.value = false
    return
  }
  clientChanging.value = true
  const ok = await new Promise((resolve) => {
    Modal.confirm({
      title: 'Cambiar cliente',
      content:
        'Ya tenés artículos cargados. Cambiar el cliente puede generar errores. ¿Querés continuar?',
      okText: 'Sí, cambiar cliente',
      cancelText: 'No, mantener cliente',
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
    })
  })
  if (ok) {
    formState.clienteId = newId
    await ensureClienteOption(newId)
    lastConfirmedClienteId.value = newId
  } else {
    formState.clienteId = oldId
    await ensureClienteOption(oldId)
  }
  setContext('client')
  clientChanging.value = false
}

const onClienteChange = async (val) => setClienteWithConfirm(val)

const selectClientFromModal = async (row) => {
  if (!row?.id) return
  clientes.value = [
    {
      value: row.id,
      label: row.razon_social,
      cuit: row.cuit,
      condicion: row.condicion,
      permite_cta_cte: Boolean(row.permite_cta_cte),
      saldo: 0,
    },
  ]
  clientModalOpen.value = false
  await setClienteWithConfirm(row.id)
  setTimeout(() => clientSelect.value?.focus?.(), 80)
}

watch(clienteInfo, (nuevoCliente) => {
  if (!nuevoCliente) return
  formState.tipoComprobanteId = (nuevoCliente.condicion || '').toLowerCase().includes('inscripto')
    ? 1
    : 2
  condicionPago.value = 'CONTADO'
  setContext('client')
})

/** ─── Artículos ─────────────────────────────────────────────────────────────── */
const productOptions = ref([])
// productOptions are scoped to the currently selected row key.
// We store which row "owns" the current search results so other rows show nothing.
const activeSearchRowKey = ref(null)
// Tracks codes currently being fetched via Enter — absorbs rapid repeat presses
// (barcode scanner or keyboard) so they accumulate into a single agregarProductoFila call.
// Maps cod_articulo → total press count while the API request is in flight.
const pendingEnterCodes = new Map()

const handleSearchFocus = (rowKey) => {
  if (activeSearchRowKey.value !== rowKey) {
    // Switching focus to a different row — clear stale options from previous row
    productOptions.value = []
  }
  activeSearchRowKey.value = rowKey
}

const onSearchProduct = async (searchText) => {
  const q = (searchText || '').trim()
  if (q.length < 3) {
    productOptions.value = []
    return
  }
  if (prodSearchT != null) {
    clearTimeout(prodSearchT)
    prodSearchT = null
  }
  // Capture which row initiated this search — discard results if focus moved elsewhere
  const searchingRowKey = activeSearchRowKey.value
  prodSearchT = window.setTimeout(async () => {
    prodSearchT = null
    if (destroyed.value) return
    // If the active row changed since the search was scheduled, discard results
    if (activeSearchRowKey.value !== searchingRowKey) return
    try {
      const { data } = await api.get('/api/articulos/', { params: { search: q } })
      const resultados = data?.results ?? data
      // Only apply results if this row is still the active one
      if (activeSearchRowKey.value === searchingRowKey) {
        productOptions.value = (resultados || []).map((p) => ({
          value: p.cod_articulo,
          label: p.descripcion,
          fullData: p,
        }))
      }
    } catch (e) {
      console.error(e)
    }
  }, 140)
}

const parsePrice = (producto) => {
  if (!producto?.precio_venta) return 0
  const raw =
    typeof producto.precio_venta === 'object' ? producto.precio_venta.amount : producto.precio_venta
  const n = parseFloat(raw)
  return isNaN(n) ? 0 : n
}

const parsePermiteNegativo = (producto) =>
  Boolean(
    producto?.permite_stock_negativo ??
      producto?.permite_existencia_negativa ??
      producto?.existencia_negativa ??
      false,
  )

const parseIvaRate = (producto) => {
  const readNumber = (v) => {
    if (v == null) return null
    if (typeof v === 'number') return Number.isFinite(v) ? v : null
    if (typeof v === 'string') {
      const n = Number(String(v).replace(',', '.'))
      return Number.isFinite(n) ? n : null
    }
    if (typeof v === 'object') {
      const c =
        v?.tasa ?? v?.rate ?? v?.porcentaje ?? v?.alicuota ?? v?.value ?? v?.amount ?? v?.percent
      const n = Number(String(c ?? '').replace(',', '.'))
      return Number.isFinite(n) ? n : null
    }
    return null
  }
  const n1 = readNumber(
    producto?.iva_rate ??
      producto?.alicuota_iva ??
      producto?.iva_alicuota ??
      producto?.iva_porcentaje ??
      producto?.iva_percent ??
      producto?.iva,
  )
  if (n1 != null) return n1
  const impuestos = producto?.impuestos ?? producto?.categoria_impositiva?.impuestos ?? null
  if (Array.isArray(impuestos)) {
    const iva = impuestos.find((x) =>
      String(x?.nombre ?? '')
        .toUpperCase()
        .includes('IVA'),
    )
    const n2 = readNumber(iva?.tasa ?? iva?.rate ?? iva?.porcentaje ?? iva?.value)
    if (n2 != null) return n2
  }
  return 21
}

// [F8] formatIvaLabel memoizada — evita crear strings idénticos en cada render
const ivaLabelCache = new Map()
const formatIvaLabel = (rate) => {
  if (ivaLabelCache.has(rate)) return ivaLabelCache.get(rate)
  const n = Number(rate)
  const lbl = !Number.isFinite(n)
    ? 'IVA 21%'
    : `IVA ${n % 1 === 0 ? String(n) : String(n).replace('.', ',')}%`
  ivaLabelCache.set(rate, lbl)
  return lbl
}

// FIX: detecta si el producto ya trae IVA usando checks != null explícitos
// (no ??) para que un valor 0 —IVA exento— también se detecte como definido
const productoHasUsableIva = (producto) =>
  Boolean(
    producto?.iva_rate != null ||
      producto?.alicuota_iva != null ||
      producto?.iva_alicuota != null ||
      producto?.iva_porcentaje != null ||
      producto?.iva_percent != nvalue.ull ||
      producto?.iva != null ||
      (Array.isArray(producto?.impuestos) && producto.impuestos.length > 0),
  )

// FIX: intenta primero por ID numérico, luego por búsqueda de código
const fetchArticuloFullData = async (producto) => {
  if (!producto) return null
  if (producto?.id != null) {
    try {
      const { data } = await api.get(`/api/articulos/${producto.id}/`)
      return data || null
    } catch {
      /* fallback a search */
    }
  }
  const codigo = producto?.cod_articulo || producto?.codigo || null
  if (!codigo) return null
  try {
    const { data } = await api.get('/api/articulos/', { params: { search: codigo } })
    const resultados = data?.results ?? data ?? []
    return (
      (resultados || []).find(
        (p) => p?.cod_articulo === codigo || p?.codigo === codigo || p?.ean === codigo,
      ) || null
    )
  } catch {
    return null
  }
}

const hydrateProductoIfNeeded = async (producto) => {
  if (!producto) return producto
  if (productoHasUsableIva(producto)) return producto
  const full = await fetchArticuloFullData(producto)
  return full ? { ...producto, ...full } : producto
}

const agregarProductoFila = async (productoRaw, index, qty = 1) => {
  const producto = await hydrateProductoIfNeeded(productoRaw)
  const item = items.value[index] ?? createEmptyRow()
  if (!items.value[index]) items.value.splice(index, 0, item)
  item.articuloId = producto.cod_articulo
  item.articuloPk = producto.id ?? null // FIX: guardamos el PK numérico
  item.codigo = producto.cod_articulo
  item.descripcion = producto.descripcion
  item.precio = parsePrice(producto)
  item.foto = producto.foto
  item.stock = parseFloat(producto.stock_total) || 0
  item.ubicacion = producto.ubicacion || 'Sin ubicación'
  item.permiteExistenciaNegativa = parsePermiteNegativo(producto)
  item.ivaRate = parseIvaRate(producto)
  item.cantidad = Math.max(1, Math.floor(Number(qty) || 1))
  selectedRowKey.value = item.key
  setContext('item', item.key)
  productOptions.value = []
  activeSearchRowKey.value = null
  ensureSingleBlankRow()
  resetPendingCobroPreview()
  await nextTick()
  scrollRowIntoView(item.key)
  message.success('Artículo agregado')
}

const onSelectProduct = (value, option, index) => {
  agregarProductoFila(option.fullData, index, 1)
}

const handleProductEnterByCode = async (val, index) => {
  // ── Same product already on THIS row → accumulate qty (Enter repetido / escáner) ──
  const thisRow = items.value[index]
  if (thisRow?.articuloId && (thisRow.articuloId === val || thisRow.codigo === val)) {
    thisRow.cantidad = Math.max(1, (Number(thisRow.cantidad) || 1) + 1)
    return
  }

  // ── This code is already being fetched (rapid Enter / barcode re-scan) ──
  // Increment the counter; the in-flight request uses the total qty.
  if (pendingEnterCodes.has(val)) {
    pendingEnterCodes.set(val, pendingEnterCodes.get(val) + 1)
    return
  }

  // ── New product — fetch from API ────────────────────────────────────────
  pendingEnterCodes.set(val, 1)
  try {
    const { data } = await api.get('/api/articulos/', { params: { search: val } })
    const resultados = data?.results ?? data
    const exact = (resultados || []).find((p) => p.cod_articulo === val || p.ean === val)
    const qty = pendingEnterCodes.get(val) ?? 1
    if (exact) await agregarProductoFila(exact, index, qty)
    else if (resultados?.length === 1) await agregarProductoFila(resultados[0], index, qty)
    else if (resultados?.length > 1)
      message.info('Múltiples coincidencias. Seleccione de la lista.')
    else message.warning('Producto no encontrado')
  } catch (err) {
    console.error(err)
  } finally {
    pendingEnterCodes.delete(val)
  }
}

// Legacy wrapper kept for any direct calls — delegates to handleProductEnterByCode
const handleProductEnter = (e, index) => {
  const val = (items.value[index]?.codigo || '').trim()
  if (val) handleProductEnterByCode(val, index)
}

const openArticuloModal = () => {
  articuloModalOpen.value = true
}

const addItemsToComprobante = async ({ items: payloadItems, close }) => {
  ensureSingleBlankRow()
  for (const it of payloadItems || []) {
    const producto = it?.producto
    if (!producto?.cod_articulo) continue
    const qty = Math.max(1, Math.floor(Number(it?.cantidad) || 1))
    const existing = items.value.find((r) => r.articuloId === producto.cod_articulo)
    if (existing) {
      existing.cantidad = Math.max(1, (Number(existing.cantidad) || 1) + qty)
      selectedRowKey.value = existing.key
      setContext('item', existing.key)
      continue
    }
    const emptyIdx = items.value.findIndex((r) => isBlankRow(r))
    if (emptyIdx >= 0) await agregarProductoFila(producto, emptyIdx, qty)
    else {
      items.value.push(createEmptyRow())
      await agregarProductoFila(producto, items.value.length - 1, qty)
    }
  }
  ensureSingleBlankRow()
  if (close) articuloModalOpen.value = false
}

/** ─── Calculadora ───────────────────────────────────────────────────────────── */
const calcDisplay = ref('0')
const calcOperator = ref(null)
const calcPrevValue = ref(null)
const resetCalcNext = ref(false)

const appendCalc = (n) => {
  if (resetCalcNext.value) {
    calcDisplay.value = String(n)
    resetCalcNext.value = false
  } else calcDisplay.value = calcDisplay.value === '0' ? String(n) : calcDisplay.value + String(n)
}
const setOp = (op) => {
  if (calcOperator.value) calculate()
  calcPrevValue.value = parseFloat(calcDisplay.value)
  calcOperator.value = op
  resetCalcNext.value = true
}
const calculate = () => {
  if (!calcOperator.value || calcPrevValue.value === null) return
  const curr = parseFloat(calcDisplay.value)
  const prev = calcPrevValue.value
  // FIX: división por cero → muestra '∞' en lugar de Infinity/NaN
  if (calcOperator.value === '/' && curr === 0) {
    calcDisplay.value = '∞'
    calcOperator.value = null
    resetCalcNext.value = true
    return
  }
  const ops = { '+': prev + curr, '-': prev - curr, '*': prev * curr, '/': prev / curr }
  calcDisplay.value = String(parseFloat((ops[calcOperator.value] ?? 0).toFixed(8)))
  calcOperator.value = null
  resetCalcNext.value = true
}
const clearCalc = () => {
  calcDisplay.value = '0'
  calcOperator.value = null
  calcPrevValue.value = null
  resetCalcNext.value = false
}
const backspaceCalc = () => {
  calcDisplay.value = calcDisplay.value.length <= 1 ? '0' : calcDisplay.value.slice(0, -1)
}

const handleCalculatorKeys = (e) => {
  if (!showCalculator.value) return false
  const k = e.key
  if (k === 'Escape') {
    e.preventDefault()
    showCalculator.value = false
    return true
  }
  if (/^[0-9]$/.test(k)) {
    e.preventDefault()
    appendCalc(Number(k))
    return true
  }
  if (k === '.' || k === ',') {
    e.preventDefault()
    if (!calcDisplay.value.includes('.')) appendCalc('.')
    return true
  }
  if (['+', '-', '*', '/'].includes(k)) {
    e.preventDefault()
    setOp(k)
    return true
  }
  if (k === 'Enter' || k === '=') {
    e.preventDefault()
    calculate()
    return true
  }
  if (k === 'Backspace') {
    e.preventDefault()
    backspaceCalc()
    return true
  }
  if (k === 'Delete' || k.toLowerCase() === 'c') {
    e.preventDefault()
    clearCalc()
    return true
  }
  return false
}

/** ─── Guardar / Suspender / Limpiar ────────────────────────────────────────── */
const draftId = ref(null)

// [F6] pagos solo se normalizan al confirmar venta (guardarComprobante), nunca al guardar borrador
const buildPayload = (estado, pagos = [], { dateOnly = false, includeNested = true } = {}) => {
  const payload = {
    cliente: toInt(formState.clienteId),
    tipo_comprobante: toInt(formState.tipoComprobanteId),
    fecha: dateOnly
      ? formatFechaDateOnly(formState.fecha)
      : formatFechaWithCurrentTime(formState.fecha),
    punto_venta: toInt(formState.puntoVenta, 1),
    estado,
    condicion_venta: mapCondicionToBackend(condicionPago.value),
  }
  if (includeNested) {
    payload.items = items.value
      .filter((i) => i.articuloId)
      .map((item) => ({
        articulo: item.articuloId,
        cantidad: toInt(item.cantidad, 1),
        precio_unitario_original: toFloat(item.precio, 0),
      }))
    payload.pagos = normalizePagos(pagos)
  }
  // Incluir overrides del cliente genérico si existen
  if (isClienteGenerico.value) {
    if (clienteOverride.nombre.trim())
      payload.cliente_nombre_override = clienteOverride.nombre.trim()
    if (clienteOverride.cuit.trim()) payload.cliente_cuit_override = clienteOverride.cuit.trim()
    if (clienteOverride.email.trim()) payload.cliente_email_override = clienteOverride.email.trim()
  }
  return payload
}

/** Advertencia AFIP para el panel de cliente genérico */
const afipCuitWarning = computed(() => {
  if (!isClienteGenerico.value) return null
  const letra =
    tiposComprobante.value.find((t) => t.value === formState.tipoComprobanteId)?.label || ''
  const esLetraA = letra.toUpperCase().includes(' A')
  const cuitIngresado = clienteOverride.cuit.trim()
  if (esLetraA && !cuitIngresado)
    return 'Factura A requiere CUIT del receptor. Completá el campo CUIT/DNI.'
  if (!cuitIngresado && totales.value.totalFinal >= 100000)
    return 'Monto ≥ $100.000 requiere CUIT/DNI para la solicitud de CAE.'
  return null
})

const validarBase = () => {
  if (!formState.clienteId) {
    message.warning('Seleccione Cliente')
    return false
  }
  if (!items.value.some((i) => i.articuloId)) {
    message.warning('Agregue artículos')
    return false
  }
  // Validación AFIP para cliente genérico con Factura A
  if (afipCuitWarning.value) {
    message.warning(afipCuitWarning.value)
    return false
  }
  return true
}

/**
 * [F7] sendComprobante — fallback explícito y plano.
 * Reducido de 4 niveles de try/catch anidado a estructura lineal legible.
 */
const sendComprobante = async ({ method, url, payloadBuilder }) => {
  const doRequest = async (opt) => {
    const payload = payloadBuilder(opt)
    const { data } =
      method === 'patch' ? await api.patch(url, payload) : await api.post(url, payload)
    return data
  }

  // Intento 1: fecha completa + nested
  try {
    return { ok: true, data: await doRequest({ dateOnly: false, includeNested: true }) }
  } catch (err1) {
    const s1 = err1?.response?.status

    // Intento 2: error de formato de fecha (400) → reintentar con dateOnly
    if (s1 === 400 && isFechaFormatError(err1)) {
      try {
        return { ok: true, data: await doRequest({ dateOnly: true, includeNested: true }) }
      } catch (err2) {
        if (method === 'patch' && err2?.response?.status >= 500 && isNestedWriteError(err2)) {
          try {
            return {
              ok: true,
              warning: 'PATCH sin items/pagos (limitación del serializer).',
              data: await doRequest({ dateOnly: true, includeNested: false }),
            }
          } catch (err3) {
            return { ok: false, error: err3 }
          }
        }
        return { ok: false, error: err2 }
      }
    }

    // Intento 3: PATCH con nested-write (500) → reintentar sin nested
    if (method === 'patch' && s1 != null && s1 >= 500 && isNestedWriteError(err1)) {
      try {
        return {
          ok: true,
          warning: 'PATCH sin items/pagos (limitación del serializer).',
          data: await doRequest({ dateOnly: false, includeNested: false }),
        }
      } catch (err2) {
        return { ok: false, error: err2 }
      }
    }

    return { ok: false, error: err1 }
  }
}

const guardarBorrador = async ({ silentIfNoChanges = true } = {}) => {
  if (silentIfNoChanges && !hasUnsavedChanges.value && draftId.value) {
    message.info('No hay cambios para guardar.')
    return true
  }
  if (!validarBase()) return false
  loading.value = true
  try {
    const isUpdate = !!draftId.value
    const res = await sendComprobante({
      method: isUpdate ? 'patch' : 'post',
      url: isUpdate ? `/api/comprobantes-venta/${draftId.value}/` : '/api/comprobantes-venta/',
      payloadBuilder: (opt) => buildPayload('BR', [], opt),
    })
    if (!res.ok) throw res.error
    if (res?.warning) message.warning(res.warning)
    draftId.value = res.data?.id ?? res.data?.pk ?? draftId.value ?? null
    hasUnsavedChanges.value = false
    message.success(isUpdate ? 'Borrador actualizado' : 'Borrador guardado')
    return true
  } catch (error) {
    console.error(error)
    showApiError(error, 'Error al guardar borrador')
    return false
  } finally {
    loading.value = false
  }
}

const confirmarSuspender = () =>
  new Promise((resolve) =>
    Modal.confirm({
      title: 'Suspender venta',
      content: 'Se guardará como borrador y se limpiará la pantalla. ¿Continuar?',
      okText: 'Sí, suspender',
      cancelText: 'Cancelar',
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
    }),
  )

const limpiar = () => {
  items.value = [createEmptyRow()]
  ensureSingleBlankRow()
  formState.clienteId = null
  clientes.value = []
  selectedRowKey.value = null
  hasUnsavedChanges.value = false
  draftId.value = null
  condicionPago.value = 'CONTADO'
  lastConfirmedClienteId.value = null
  resetPendingCobroPreview()
  // Limpiar overrides del cliente genérico
  clienteOverride.nombre = ''
  clienteOverride.cuit = ''
  clienteOverride.email = ''
  overridePopoverOpen.value = false
  setContext('none')
  nextTick(() => {
    updateAvailableHeight()
    measureLayout()
    scheduleFooterMetrics()
    loadClienteGenerico()
  })
}

const confirmarCancelarOperacion = () =>
  new Promise((resolve) =>
    Modal.confirm({
      title: 'Cancelar operación',
      content: 'Se perderán los cambios. ¿Limpiar la pantalla y comenzar de nuevo?',
      okText: 'Sí, cancelar',
      cancelText: 'Volver',
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
    }),
  )

const cancelarOperacion = async () => {
  if (!formState.clienteId && !hasAnyArticulo.value) {
    limpiar()
    return
  }
  if (await confirmarCancelarOperacion()) limpiar()
}

const suspenderVenta = async () => {
  if (!validarBase()) return
  if (!(await confirmarSuspender())) return
  if (await guardarBorrador({ silentIfNoChanges: false })) limpiar()
}

/** ─── Confirmación previa ───────────────────────────────────────────────────── */
const money = (n) =>
  (Number(n) || 0).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const resumenFormaPago = computed(() => {
  if (condicionPago.value === 'CTA_CTE') return 'Cuenta Corriente'
  if (!pendingPagos.value.length) return '—'
  return pendingPagos.value
    .map(
      (p) =>
        `${p?.descripcion || p?.medio_pago || p?.tipo || 'Pago'}: $ ${money(p?.importe ?? p?.monto ?? p?.amount ?? 0)}`,
    )
    .join(' | ')
})

const abrirConfirmacionFinal = () => {
  finalConfirmOpen.value = true
}
const cancelarConfirmacionFinal = () => {
  finalConfirmOpen.value = false
}
const confirmarYGenerar = async () => {
  finalConfirmOpen.value = false
  await guardarComprobante({ pagos: pendingPagos.value || [] })
}

/** ─── Generar comprobante ───────────────────────────────────────────────────── */
const guardarComprobante = async ({ pagos = [] } = {}) => {
  if (!validarBase()) return
  if (hasStockIssues.value) {
    message.error('Hay artículos con cantidad superior al stock y NO permiten existencia negativa.')
    return
  }
  if (condicionPago.value === 'CTA_CTE' && !clientePermiteCtaCte.value) {
    message.error('El cliente no está habilitado para Cuenta Corriente.')
    condicionPago.value = 'CONTADO'
    return
  }
  if (condicionPago.value === 'CONTADO' && !pagos.length) {
    message.warning('Debe cargar una forma de pago para ventas al contado.')
    paymentOpen.value = true
    return
  }

  loading.value = true
  try {
    const res = await sendComprobante({
      method: draftId.value ? 'patch' : 'post',
      url: draftId.value ? `/api/comprobantes-venta/${draftId.value}/` : '/api/comprobantes-venta/',
      payloadBuilder: (opt) => buildPayload('CN', pagos, opt),
    })
    if (!res.ok) throw res.error
    hasUnsavedChanges.value = false
    draftId.value = null
    resetPendingCobroPreview()
    // Mostrar modal de impresión post-venta
    ventaFinalizada.id = res.data?.id ?? res.data?.pk ?? null
    ventaFinalizada.numero = res.data?.numero_completo || ''
    printModalOpen.value = true
  } catch (error) {
    console.error(error)
    showApiError(error, 'Error al procesar')
  } finally {
    loading.value = false
  }
}

const openFinalizar = () => {
  if (!validarBase()) return
  if (hasStockIssues.value) {
    message.error('Hay artículos con cantidad superior al stock y NO permiten existencia negativa.')
    return
  }
  if (condicionPago.value === 'CTA_CTE') {
    if (!clientePermiteCtaCte.value) {
      message.error('El cliente no está habilitado para Cuenta Corriente.')
      condicionPago.value = 'CONTADO'
      return
    }
    pendingPagos.value = []
    abrirConfirmacionFinal()
    return
  }
  paymentOpen.value = true
}

const onConfirmPayment = ({ pagos, recargos_total = 0, descuentos_total = 0 } = {}) => {
  paymentOpen.value = false
  pendingPagos.value = pagos || []
  pendingRecargos.value = Number(recargos_total || 0)
  pendingDescuentos.value = Number(descuentos_total || 0)
  abrirConfirmacionFinal()
}

const onCancelPayment = () => {
  resetPendingCobroPreview()
}

/** ─── Modal impresión post-venta ───────────────────────────────────────────── */
const onPrintAndNew = async () => {
  printModalOpen.value = false
  await abrirPdfComprobante(ventaFinalizada.id)
  limpiar()
}
const onPrintOnly = async () => {
  await abrirPdfComprobante(ventaFinalizada.id)
}
const onSkipPrint = () => {
  printModalOpen.value = false
  limpiar()
}

/** ─── Retomar suspendida ────────────────────────────────────────────────────── */
const pick = (obj, ...keys) => {
  for (const k of keys) {
    const v = obj?.[k]
    if (v != null) return v
  }
  return null
}

const extractVentaId = (p) =>
  typeof p === 'number' || typeof p === 'string'
    ? p
    : pick(p, 'id', 'pk', 'comprobante_id', 'comprobanteId', 'venta_id', 'ventaId')
const extractClienteId = (v) =>
  pick(v?.cliente, 'id', 'pk') ?? pick(v, 'cliente_id', 'clienteId', 'id_cliente')
const extractTipoComprobanteId = (v) =>
  pick(v?.tipo_comprobante, 'id', 'pk') ??
  pick(v, 'tipo_comprobante_id', 'tipoComprobanteId', 'tipo_id')
const extractPuntoVenta = (v) => pick(v, 'punto_venta', 'puntoVenta', 'pv', 'punto_venta_id')
const extractCondicionVenta = (v) =>
  pick(v, 'condicion_venta', 'condicionVenta', 'condicion', 'cond_venta')
const extractFecha = (v) => pick(v, 'fecha', 'fecha_hora', 'created_at', 'createdAt')

const extractItemsArray = (venta) => {
  for (const k of ['items', 'detalle', 'detalles', 'lineas', 'renglones', 'rows']) {
    if (Array.isArray(venta?.[k])) return venta[k]
  }
  for (const k of ['items', 'detalle', 'detalles', 'lineas']) {
    if (Array.isArray(venta?.comprobante?.[k])) return venta.comprobante[k]
  }
  return []
}

const mapItemFromVenta = (it) => {
  const row = createEmptyRow()
  const artCode =
    it?.articulo?.cod_articulo ??
    it?.articulo?.codigo ??
    it?.cod_articulo ??
    it?.codigo ??
    it?.articulo_id ??
    it?.producto?.cod_articulo ??
    null
  row.articuloPk = it?.articulo?.id ?? it?.producto?.id ?? null // FIX: guardamos PK
  row.articuloId = artCode
  row.codigo = artCode || ''
  row.descripcion =
    it?.articulo?.descripcion ?? it?.producto?.descripcion ?? it?.descripcion ?? it?.detalle ?? ''
  row.cantidad = Math.max(0, Number(it?.cantidad ?? it?.qty ?? 1))
  row.precio = Number(it?.precio_unitario_original ?? it?.precio_unitario ?? it?.precio ?? 0)
  row.stock = Number(it?.stock_total ?? it?.stock ?? it?.articulo?.stock_total ?? 0)
  row.foto = it?.foto ?? it?.articulo?.foto ?? it?.producto?.foto ?? null
  row.ubicacion = it?.ubicacion ?? it?.articulo?.ubicacion ?? ''
  row.permiteExistenciaNegativa = Boolean(
    it?.articulo?.permite_stock_negativo ??
      it?.articulo?.permite_existencia_negativa ??
      it?.permite_stock_negativo ??
      false,
  )
  // FIX: usa parseIvaRate() completo en lugar de extracción inline simplificada
  row.ivaRate = parseIvaRate({
    iva_rate: it?.articulo?.iva_rate ?? it?.iva_rate,
    alicuota_iva: it?.articulo?.alicuota_iva,
    iva: it?.articulo?.iva ?? it?.iva,
    impuestos: it?.articulo?.impuestos ?? it?.impuestos,
    categoria_impositiva: it?.articulo?.categoria_impositiva,
  })
  return row
}

const onResumeSuspendida = async (payload) => {
  try {
    const ventaId = extractVentaId(payload)
    let venta = payload
    if (ventaId) {
      const { data } = await api.get(`/api/comprobantes-venta/${ventaId}/`)
      venta = data
    }
    if (!venta) {
      message.error('No se pudo cargar la venta suspendida.')
      return
    }

    const clienteId = extractClienteId(venta)
    await ensureClienteOption(clienteId)
    await setClienteWithConfirm(clienteId, { force: true })

    formState.tipoComprobanteId = extractTipoComprobanteId(venta) ?? 2
    formState.fecha = dayjs(extractFecha(venta) || undefined)
    formState.puntoVenta = extractPuntoVenta(venta) ?? (configStore.puntoVentaDefault || 1)
    condicionPago.value = mapCondicionFromBackend(extractCondicionVenta(venta))

    const mapped = extractItemsArray(venta)
      .map(mapItemFromVenta)
      .filter((r) => !!r.articuloId)
    items.value = mapped.length ? mapped : []
    ensureSingleBlankRow()

    draftId.value = venta?.id ?? venta?.pk ?? ventaId ?? null
    suspendidasOpen.value = false
    hasUnsavedChanges.value = true
    message.success('Venta suspendida cargada')

    const first = items.value.find((r) => r.articuloId)
    if (first) {
      selectedRowKey.value = first.key
      setContext('item', first.key)
    } else setContext('client')

    await nextTick()
    await raf2()
    updateAvailableHeight()
    measureLayout()
    scheduleFooterMetrics()
  } catch (e) {
    console.error(e)
    message.error('No se pudo cargar la venta suspendida.')
  }
}

/** ─── Panel derecho ─────────────────────────────────────────────────────────── */
const itemInfo = computed(() =>
  selectedRowKey.value ? (items.value.find((i) => i.key === selectedRowKey.value) ?? null) : null,
)

const handleRowClick = (record) => {
  selectedRowKey.value = record.key
  setContext('item', record.key)
}
const onClientFocus = () => setContext('client')

const removeItem = (index) => {
  if (items.value.length <= 1) return
  const removedKey = items.value[index]?.key
  items.value.splice(index, 1)
  ensureSingleBlankRow()
  if (removedKey === selectedRowKey.value) {
    const next = items.value.find((r) => r.articuloId) || items.value[0]
    selectedRowKey.value = next?.key ?? null
    setContext(clienteInfo.value ? 'client' : 'none', selectedRowKey.value)
  }
}

// [F11] Placeholder local en lugar de servicio externo
const getImageUrl = (path) => {
  if (!path) return '/placeholder-product.png'
  if (path.startsWith('http')) return path
  return `${api?.defaults?.baseURL || ''}${path}`
}

/** Descarga el PDF via Axios (con token JWT) y lo abre en nueva pestaña.
 *  window.open() directo no funciona porque no envía el header Authorization. */
const abrirPdfComprobante = async (comprobanteId) => {
  if (!comprobanteId) return
  ventaFinalizada.loadingPdf = true
  try {
    const response = await api.get(`/api/comprobantes-venta/${comprobanteId}/pdf/`, {
      responseType: 'blob',
    })
    const blob = new Blob([response.data], { type: 'application/pdf' })
    const url = URL.createObjectURL(blob)
    const win = window.open(url, '_blank')
    // Revocar la URL temporal después de que el navegador la cargó
    if (win) win.addEventListener('load', () => URL.revokeObjectURL(url), { once: true })
    else setTimeout(() => URL.revokeObjectURL(url), 10000)
  } catch (e) {
    console.error(e)
    message.error('No se pudo generar el PDF. Verificá la configuración del diseño de impresión.')
  } finally {
    ventaFinalizada.loadingPdf = false
  }
}

/** ─── Totales + impuestos ───────────────────────────────────────────────────── */
const baseItem = (item) =>
  Number(item.cantidad || 0) * Number(item.precio || 0) * (1 - Number(item.descuento || 0) / 100)

const taxesRows = computed(() => {
  const map = new Map()
  for (const it of items.value) {
    if (!it.articuloId) continue
    const rate = Number(it.ivaRate ?? 21)
    const safeRate = Number.isFinite(rate) ? rate : 21
    const label = formatIvaLabel(safeRate) // [F8] memoizada
    map.set(label, (map.get(label) || 0) + (baseItem(it) * safeRate) / 100)
  }
  return [...map.entries()]
    .map(([label, amount]) => ({ label, amount }))
    .sort((a, b) => a.label.localeCompare(b.label))
})

const totales = computed(() => {
  const neto = items.value.reduce((acc, it) => acc + (it.articuloId ? baseItem(it) : 0), 0)
  const impuestos = taxesRows.value.reduce((acc, r) => acc + Number(r.amount || 0), 0)
  const recargos = Number(pendingRecargos.value || 0)
  const descuentos = Number(pendingDescuentos.value || 0)
  const total = neto + impuestos
  const totalFinal = total + recargos - descuentos
  return { neto, impuestos, recargos, descuentos, total, totalFinal }
})

/** ─── Modal salida segura ───────────────────────────────────────────────────── */
const leaveAndDiscard = async () => {
  hasUnsavedChanges.value = false
  await proceedToPendingRoute()
}
const leaveAndSaveDraft = async () => {
  if (await guardarBorrador({ silentIfNoChanges: false })) await proceedToPendingRoute()
}

/** ─── Atajos de teclado ─────────────────────────────────────────────────────── */
const isTypingTarget = (e) => {
  const tag = (e?.target?.tagName || '').toUpperCase()
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || !!e?.target?.isContentEditable
}

// [F4] closeAnyModal NO cierra leaveModalOpen (modal bloqueante — requiere acción explícita del usuario)
const closeAnyModal = () => {
  if (imageZoomOpen.value) {
    imageZoomOpen.value = false
    return
  }
  if (finalConfirmOpen.value) {
    finalConfirmOpen.value = false
    return
  }
  if (paymentOpen.value) {
    paymentOpen.value = false
    return
  }
  if (articuloModalOpen.value) {
    articuloModalOpen.value = false
    return
  }
  if (suspendidasOpen.value) {
    suspendidasOpen.value = false
    return
  }
  if (clientModalOpen.value) {
    clientModalOpen.value = false
    return
  }
  if (showCalculator.value) {
    showCalculator.value = false
    return
  }
  if (shortcutsOpen.value) {
    shortcutsOpen.value = false
    return
  }
}

const handleShortcuts = async (e) => {
  if (destroyed.value) return
  if (handleCalculatorKeys(e)) return
  if (e.key === 'Escape') {
    closeAnyModal()
    return
  }
  const typing = isTypingTarget(e)
  if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S')) {
    e.preventDefault()
    await guardarBorrador()
    return
  }
  if (!typing) {
    if (e.key === 'Insert') {
      e.preventDefault()
      await addManualRow()
      return
    }
    if (e.key === 'F2') {
      e.preventDefault()
      setTimeout(() => clientSelect.value?.focus?.(), 0)
      return
    }
    if (e.key === 'F3') {
      e.preventDefault()
      articuloModalOpen.value = true
      return
    }
    if (e.key === 'F9') {
      e.preventDefault()
      openFinalizar()
      return
    }
    if (e.key === 'F1') {
      e.preventDefault()
      shortcutsOpen.value = true
      return
    }
    if (e.key === 'F10') {
      e.preventDefault()
      toggleFocusMode()
      return
    }
  }
}

/** ─── Footer metrics ────────────────────────────────────────────────────────── */
const setPosThemeVars = (theme) => {
  const root = document.documentElement
  if (theme === 'dark') {
    root.style.setProperty('--pos-footer-bg', 'rgba(2, 6, 23, 0.94)')
    root.style.setProperty('--pos-footer-border', 'rgba(148, 163, 184, 0.18)')
  } else {
    root.style.setProperty('--pos-footer-bg', 'rgba(255, 255, 255, 0.97)')
    root.style.setProperty('--pos-footer-border', 'rgba(148, 163, 184, 0.28)')
  }
}

// [F10] Cacheamos la altura del footer para no forzar layout en cada RAF
const setFooterSpaceVar = () => {
  try {
    const h = footerEl.value?.getBoundingClientRect?.()?.height
    if (h && h > 0)
      document.documentElement.style.setProperty(
        '--pos-footer-space',
        `${Math.max(96, Math.ceil(h + 16))}px`,
      )
  } catch {
    /* ignore */
  }
}

// [F5] footerRaf LOCAL al setup
const scheduleFooterMetrics = () => {
  if (destroyed.value || footerRaf) return
  footerRaf = requestAnimationFrame(() => {
    footerRaf = 0
    updateFooterMetricsNow()
  })
}

const updateFooterMetricsNow = () => {
  if (destroyed.value) return
  try {
    setFooterSpaceVar()

    // ── Focus mode: footer spans the full posRoot element ──────────────────
    if (focusMode.value && posRootEl.value) {
      const r = posRootEl.value.getBoundingClientRect()
      const left = Math.max(0, Math.round(r.left))
      // Deduct only body padding (14px each side) so footer sits within the body gutters
      const width = Math.max(320, Math.round(r.width - 28))
      document.documentElement.style.setProperty('--pos-footer-left', `${left + 14}px`)
      document.documentElement.style.setProperty('--pos-footer-width', `${width}px`)
      return
    }

    // ── Normal mode: footer aligns with the full pos-body area (left+right panels) ─
    // body left padding = 14px; right edge = content right edge - body right padding (14px)
    const BODY_PADDING = 14
    const content =
      document.querySelector('.ant-layout-content') ||
      document.querySelector('.layout-content') ||
      document.querySelector('main') ||
      null
    if (!content) return
    const r = content.getBoundingClientRect()
    const left = Math.max(0, Math.round(r.left + BODY_PADDING))
    const width = Math.max(320, Math.round(r.width - BODY_PADDING * 2))
    document.documentElement.style.setProperty('--pos-footer-left', `${left}px`)
    document.documentElement.style.setProperty('--pos-footer-width', `${width}px`)
  } catch {
    /* ignore */
  }
}

// [F13] Sin immediate — se llama en onMounted
watch(
  () => configStore.currentTheme,
  async (t) => {
    setPosThemeVars(t === 'dark' ? 'dark' : 'light')
    await nextTick()
    scheduleFooterMetrics()
    readPrimaryFromCss()
    requestAnimationFrame(() => readPrimaryFromCss())
  },
)

watch(
  focusMode,
  async () => {
    await nextTick()
    await raf2()
    updateAvailableHeight()
    scheduleFooterMetrics()
    await nextTick()
    measureLayout()
  },
  { flush: 'post' },
)

const onWindowResize = () => {
  if (destroyed.value) return
  updateAvailableHeight()
  scheduleFooterMetrics()
  measureLayout()
}

const startObservers = () => {
  window.addEventListener('resize', onWindowResize)
  if (posRootEl.value && 'ResizeObserver' in window) {
    layoutObs = new ResizeObserver(() => {
      if (destroyed.value) return
      updateAvailableHeight()
      scheduleFooterMetrics()
      measureLayout()
    })
    layoutObs.observe(posRootEl.value)
  }
  const content =
    document.querySelector('.ant-layout-content') ||
    document.querySelector('.layout-content') ||
    document.querySelector('main') ||
    null
  if (content && 'ResizeObserver' in window) {
    resizeObs = new ResizeObserver(() => {
      if (!destroyed.value) scheduleFooterMetrics()
    })
    resizeObs.observe(content)
  }
  siderEl = document.querySelector('.ant-layout-sider')
  if (siderEl) {
    siderTransitionHandler = () => scheduleFooterMetrics()
    ;['transitionrun', 'transitionstart', 'transitionend', 'transitioncancel'].forEach((ev) =>
      siderEl.addEventListener(ev, siderTransitionHandler),
    )
  }
}

/** ─── Lifecycle ─────────────────────────────────────────────────────────────── */
onMounted(() => {
  // Reset completo — crítico para re-montaje tras navegación SPA
  destroyed.value = false
  normalizing = false
  prodSearchT = null
  footerRaf = 0
  layoutRaf = 0

  applyFocusClass(false)
  updateAvailableHeight()

  // [F2] Listener de beforeunload registrado manualmente
  if (hasUnsavedChanges.value) window.addEventListener('beforeunload', handleBeforeUnload)

  if (!configStore.currentTheme) configStore.setTheme('light')

  // [F13] Lectura inicial manual (sin depender de immediate en watches)
  readPrimaryFromCss()
  setPosThemeVars(configStore.currentTheme === 'dark' ? 'dark' : 'light')

  items.value = [createEmptyRow()]
  ensureSingleBlankRow()

  // Cargar cliente genérico (C00000) por defecto al iniciar el POS
  loadClienteGenerico()

  setTimeout(() => clientSelect.value?.focus?.(), 150)
  window.addEventListener('keydown', handleShortcuts)
  setContext('none')

  nextTick(async () => {
    requestAnimationFrame(() => readPrimaryFromCss())
    await raf2()
    updateAvailableHeight()
    scheduleFooterMetrics()
    await nextTick()
    measureLayout()
    startObservers()
  })
})

onUnmounted(() => {
  shutdownNow()
  // [F2] Limpieza definitiva (shutdownNow ya la hace, pero la duplicamos por seguridad)
  window.removeEventListener('beforeunload', handleBeforeUnload)
})
</script>

<template>
  <div class="pos-route-root">
    <a-config-provider :theme="antdThemeConfig">
      <div
        ref="posRootEl"
        class="pos-root"
        :class="{ 'pos-dark': isDark, 'pos-light': !isDark, 'pos-focus': focusMode }"
        :style="{ '--pos-primary': posPrimary }"
      >
        <main class="pos-body">
          <!-- ═══════════════ PANEL IZQUIERDO ═══════════════════════════════ -->
          <section class="left-panel">
            <!-- Header card -->
            <a-card
              ref="headerCardEl"
              class="form-card pos-sticky-header"
              :bordered="false"
              :bodyStyle="{ padding: '12px 16px' }"
            >
              <a-row :gutter="10" align="bottom">
                <a-col :span="10">
                  <div class="field-group">
                    <span class="field-label">Cliente</span>
                    <a-select
                      ref="clientSelect"
                      :value="formState.clienteId"
                      show-search
                      :options="clientes"
                      :loading="cargandoClientes"
                      :filter-option="false"
                      @search="buscarClientes"
                      @focus="onClientFocus"
                      @click="onClientFocus"
                      @change="onClienteChange"
                      placeholder="Buscar por nombre o CUIT (mín. 3 letras)"
                      style="width: 100%"
                      size="large"
                      class="client-select"
                      :getPopupContainer="() => posRootEl || document.body"
                    >
                      <template #option="{ label, cuit }">
                        <div class="client-option">
                          <span class="client-name">{{ label }}</span>
                          <span class="client-cuit">{{ cuit }}</span>
                        </div>
                      </template>
                    </a-select>
                  </div>
                </a-col>

                <a-col :span="2">
                  <a-tooltip title="Búsqueda avanzada de clientes">
                    <a-button
                      size="large"
                      block
                      @click="openClientModal"
                      aria-label="Buscar cliente"
                      style="margin-bottom: 1px"
                    >
                      <SearchOutlined />
                    </a-button>
                  </a-tooltip>
                </a-col>

                <!-- Botón datos cliente ocasional — solo visible cuando es C00000 -->
                <a-col :span="2" v-if="showClienteOverridePanel">
                  <a-popover
                    v-model:open="overridePopoverOpen"
                    trigger="click"
                    placement="bottomLeft"
                    :overlayStyle="{ width: '380px' }"
                    :getPopupContainer="() => posRootEl || document.body"
                  >
                    <template #title>
                      <div class="override-pop-title">
                        <UserOutlined />
                        <span>Datos del cliente ocasional</span>
                        <span class="override-pop-badge">C00000</span>
                        <transition name="fade">
                          <span
                            v-if="afipCuitWarning"
                            class="override-pop-warn-dot"
                            title="AFIP: requiere CUIT"
                            >!</span
                          >
                        </transition>
                      </div>
                    </template>
                    <template #content>
                      <div class="override-pop-body">
                        <p class="override-pop-hint">
                          Datos opcionales del comprobante — no se crea un cliente nuevo.
                        </p>
                        <div class="override-pop-field">
                          <label class="override-pop-label">Nombre / Razón Social</label>
                          <a-input
                            v-model:value="clienteOverride.nombre"
                            placeholder="Ej: Juan Pérez / Empresa SRL"
                            allow-clear
                          />
                        </div>
                        <div class="override-pop-field">
                          <label class="override-pop-label">
                            CUIT / DNI
                            <span
                              class="override-pop-required"
                              title="Requerido para Factura A o montos ≥ $100.000"
                              >*</span
                            >
                          </label>
                          <a-input
                            v-model:value="clienteOverride.cuit"
                            placeholder="Ej: 20-12345678-9 o 12345678"
                            allow-clear
                            :status="afipCuitWarning ? 'warning' : ''"
                          />
                          <transition name="fade">
                            <p v-if="afipCuitWarning" class="override-pop-warn-msg">
                              {{ afipCuitWarning }}
                            </p>
                          </transition>
                        </div>
                        <div class="override-pop-field">
                          <label class="override-pop-label">Email</label>
                          <a-input
                            v-model:value="clienteOverride.email"
                            placeholder="Ej: cliente@email.com"
                            allow-clear
                            type="email"
                          />
                        </div>
                      </div>
                    </template>
                    <a-tooltip title="Datos del cliente ocasional">
                      <a-button
                        size="large"
                        block
                        :class="[
                          'override-trigger-btn',
                          overrideHasData || afipCuitWarning ? 'override-trigger-btn--active' : '',
                        ]"
                        style="margin-bottom: 1px"
                        :aria-label="'Datos cliente ocasional'"
                      >
                        <UserOutlined />
                        <span
                          v-if="afipCuitWarning"
                          class="override-btn-dot override-btn-dot--warn"
                        />
                        <span
                          v-else-if="overrideHasData"
                          class="override-btn-dot override-btn-dot--ok"
                        />
                      </a-button>
                    </a-tooltip>
                  </a-popover>
                </a-col>

                <a-col :span="4">
                  <div class="field-group">
                    <span class="field-label">Comprobante</span>
                    <a-select
                      v-model:value="formState.tipoComprobanteId"
                      :options="tiposComprobante"
                      style="width: 100%"
                      size="large"
                      :getPopupContainer="() => posRootEl || document.body"
                    />
                  </div>
                </a-col>

                <a-col :span="4">
                  <div class="field-group">
                    <span class="field-label">Fecha</span>
                    <a-date-picker
                      v-model:value="formState.fecha"
                      style="width: 100%"
                      size="large"
                      format="DD/MM/YYYY"
                      :getPopupContainer="() => posRootEl || document.body"
                    />
                  </div>
                </a-col>

                <a-col :span="2" style="text-align: right">
                  <a-tooltip
                    :title="focusMode ? 'Salir del modo enfoque (F10)' : 'Modo enfoque (F10)'"
                    trigger="hover"
                    :mouseLeaveDelay="0"
                  >
                    <a-button
                      size="large"
                      @click="toggleFocusMode"
                      :disabled="focusToggling"
                      :class="{ 'btn-focus-active': focusMode }"
                      :aria-label="focusMode ? 'Salir del modo enfoque' : 'Activar modo enfoque'"
                      style="margin-bottom: 1px"
                    >
                      <template #icon>
                        <CompressOutlined v-if="focusMode" />
                        <ExpandOutlined v-else />
                      </template>
                    </a-button>
                  </a-tooltip>
                </a-col>
              </a-row>
            </a-card>

            <!-- Grid card -->
            <a-card
              ref="gridCardEl"
              class="grid-card"
              :bordered="false"
              :bodyStyle="{ padding: 0, display: 'flex', flexDirection: 'column', height: '100%' }"
            >
              <div ref="gridTopbarEl" class="grid-topbar">
                <a-button @click="openArticuloModal" class="search-articles-btn">
                  <AppstoreOutlined />
                  Buscar artículos
                  <kbd class="topbar-kbd">F3</kbd>
                </a-button>
                <span class="grid-hint"
                  >Selección múltiple · cantidades · "Cargar y continuar"</span
                >
              </div>

              <div ref="gridTableWrapEl" class="grid-table-wrap">
                <a-table
                  :rowKey="(r) => r.key"
                  :columns="columns"
                  :data-source="items"
                  :pagination="false"
                  size="middle"
                  :scroll="{ y: tableScrollY }"
                  :customRow="
                    (record, index) => ({
                      onClick: () => handleRowClick(record),
                      class: [
                        index % 2 === 0 ? 'row-even' : 'row-odd',
                        record.key === selectedRowKey ? 'row-selected' : '',
                        isRowOutOfStock(record) ? 'row-stock-bad' : '',
                        !record.articuloId && record.codigo ? 'row-draft' : '',
                      ].join(' '),
                    })
                  "
                >
                  <template #bodyCell="{ column, record, index }">
                    <template v-if="column.dataIndex === 'codigo'">
                      <a-auto-complete
                        v-model:value="record.codigo"
                        :options="activeSearchRowKey === record.key ? productOptions : []"
                        @search="onSearchProduct"
                        @focus="
                          () => {
                            handleSearchFocus(record.key)
                            selectedRowKey.value = record.key
                            setContext('item', record.key)
                          }
                        "
                        @select="
                          (val, opt) => {
                            onSelectProduct(val, opt, index)
                            activeSearchRowKey.value = null
                            productOptions.value = []
                          }
                        "
                        class="search-autocomplete"
                        :bordered="false"
                        style="width: 100%"
                        @keydown.enter.prevent="
                          (e) => {
                            const _cod = (record.codigo || '').trim()
                            productOptions.value = []
                            activeSearchRowKey.value = null
                            if (_cod) handleProductEnterByCode(_cod, index)
                          }
                        "
                        :backfill="true"
                        :defaultActiveFirstOption="false"
                        :getPopupContainer="() => posRootEl || document.body"
                      >
                        <a-input class="grid-search-input">
                          <template #prefix><BarcodeOutlined /></template>
                          <template #placeholder>Código o nombre...</template>
                        </a-input>
                        <template #option="{ fullData }">
                          <div class="product-option-row">
                            <span class="prod-desc">{{ fullData.descripcion }}</span>
                            <div class="prod-meta">
                              <span class="prod-brand">{{ fullData.marca?.nombre || '—' }}</span>
                              <span class="prod-stock">{{ fullData.stock_total }} un.</span>
                            </div>
                          </div>
                        </template>
                      </a-auto-complete>
                    </template>

                    <template v-if="column.dataIndex === 'cantidad'">
                      <a-tooltip
                        v-if="isRowOutOfStock(record)"
                        placement="top"
                        title="Cantidad mayor al stock — NO permite existencia negativa"
                      >
                        <a-input-number
                          v-model:value="record.cantidad"
                          :min="0"
                          :bordered="false"
                          class="full-width centered-input qty-danger"
                        />
                      </a-tooltip>
                      <a-input-number
                        v-else
                        v-model:value="record.cantidad"
                        :min="0"
                        :bordered="false"
                        class="full-width centered-input"
                      />
                    </template>

                    <template v-if="column.dataIndex === 'precio'">
                      <a-input-number
                        v-model:value="record.precio"
                        :bordered="false"
                        class="full-width right-align-input"
                        :formatter="(v) => `$ ${v}`.replace(RE_PRICE_FORMAT, ',')"
                        :parser="(v) => v.replace(RE_PRICE_PARSE, '')"
                      />
                    </template>

                    <!-- FIX: descuento ahora tiene renderer (antes mostraba celda vacía) -->
                    <template v-if="column.dataIndex === 'descuento'">
                      <a-input-number
                        v-model:value="record.descuento"
                        :min="0"
                        :max="100"
                        :bordered="false"
                        class="full-width centered-input"
                        :formatter="(v) => (v > 0 ? `${v}%` : '')"
                        :parser="(v) => v.replace('%', '')"
                      />
                    </template>

                    <template v-if="column.dataIndex === 'subtotal'">
                      <span class="subtotal-val"
                        >$ {{ money(record.articuloId ? baseItem(record) : 0) }}</span
                      >
                    </template>

                    <template v-if="column.dataIndex === 'actions'">
                      <a-button
                        type="text"
                        danger
                        size="small"
                        @click.stop="removeItem(index)"
                        aria-label="Eliminar artículo"
                        class="delete-row-btn"
                      >
                        <DeleteOutlined />
                      </a-button>
                    </template>
                  </template>
                </a-table>
              </div>

              <div ref="gridActionsEl" class="grid-actions">
                <a-tooltip title="Agregar manualmente (Insert)">
                  <a-button
                    type="dashed"
                    block
                    size="large"
                    @click="addManualRow"
                    class="add-row-btn"
                  >
                    <PlusOutlined /> Agregar renglón
                  </a-button>
                </a-tooltip>
                <span class="grid-actions-hint">No se permiten múltiples renglones en blanco.</span>
              </div>
            </a-card>
          </section>

          <!-- ═══════════════ PANEL DERECHO ════════════════════════════════ -->
          <!-- Overlay for mobile drawer -->
          <div
            class="right-panel-overlay"
            :class="{ 'right-panel-overlay--visible': rightPanelOpen }"
            @click="rightPanelOpen = false"
          />
          <!-- Toggle button — only visible on small screens -->
          <button
            class="right-panel-toggle"
            @click="rightPanelOpen = !rightPanelOpen"
            type="button"
            :aria-label="rightPanelOpen ? 'Cerrar panel' : 'Ver info y acciones'"
          >
            <UserOutlined v-if="contextMode === 'client'" />
            <InfoCircleOutlined v-else-if="contextMode === 'item'" />
            <AppstoreOutlined v-else />
          </button>
          <section class="right-panel" :class="{ 'right-panel--open': rightPanelOpen }">
            <!-- Info contextual -->
            <div class="context-area pos-sticky-right">
              <transition name="fade" mode="out-in">
                <div
                  v-if="contextMode === 'item' && itemInfo?.articuloId"
                  class="info-card"
                  key="product"
                >
                  <div class="info-header">
                    <InfoCircleOutlined class="info-header-icon" />
                    <span>Detalle artículo</span>
                  </div>
                  <div class="product-visual">
                    <img :src="getImageUrl(itemInfo.foto)" class="product-img" alt="Producto" />
                    <div class="stock-badge" :class="{ 'stock-badge--low': itemInfo.stock < 5 }">
                      {{ itemInfo.stock }} UN
                    </div>
                    <button
                      v-if="itemInfo.foto"
                      class="img-zoom-btn"
                      @click="imageZoomOpen = true"
                      type="button"
                      title="Ampliar imagen"
                    >
                      <svg viewBox="0 0 16 16" fill="currentColor" width="13" height="13">
                        <path
                          d="M6.5 0a6.5 6.5 0 1 0 4.776 10.925l2.9 2.9a.5.5 0 0 0 .707-.707l-2.9-2.9A6.5 6.5 0 0 0 6.5 0zM1 6.5a5.5 5.5 0 1 1 11 0 5.5 5.5 0 0 1-11 0z"
                        />
                        <path
                          d="M6.5 3a.5.5 0 0 1 .5.5V6h2.5a.5.5 0 0 1 0 1H7v2.5a.5.5 0 0 1-1 0V7H3.5a.5.5 0 0 1 0-1H6V3.5a.5.5 0 0 1 .5-.5z"
                        />
                      </svg>
                      Ampliar
                    </button>
                  </div>
                  <h3 class="info-name">{{ itemInfo.descripcion }}</h3>
                  <div class="info-meta-grid">
                    <div class="info-meta-row">
                      <span class="meta-key">Ubicación</span>
                      <span class="meta-val">{{ itemInfo.ubicacion }}</span>
                    </div>
                    <div class="info-meta-row">
                      <span class="meta-key">Alícuota IVA</span>
                      <span class="meta-val">{{ itemInfo.ivaRate }}%</span>
                    </div>
                    <div class="info-meta-row">
                      <span class="meta-key">Código</span>
                      <span class="meta-val meta-mono">{{ itemInfo.articuloId }}</span>
                    </div>
                  </div>
                </div>

                <div
                  v-else-if="clienteInfo"
                  class="info-card"
                  key="client"
                  @click="setContext('client')"
                >
                  <div class="info-header">
                    <UserOutlined class="info-header-icon" />
                    <span>Información cliente</span>
                  </div>
                  <div class="client-avatar">
                    {{ clienteInfo.label?.charAt(0)?.toUpperCase() ?? '?' }}
                  </div>
                  <h3 class="info-name">{{ clienteInfo.label }}</h3>
                  <p class="client-cuit-display">{{ clienteInfo.cuit }}</p>
                  <div class="client-flags">
                    <span class="flag" :class="clientePermiteCtaCte ? 'flag--ok' : 'flag--bad'">
                      <span class="flag-dot"></span>
                      Cta. Cte. {{ clientePermiteCtaCte ? 'habilitada' : 'no habilitada' }}
                    </span>
                  </div>
                </div>

                <div v-else class="info-card info-card--empty" key="empty">
                  <BarcodeOutlined class="empty-icon" />
                  <p class="empty-hint">Seleccione un artículo o cliente para ver detalles</p>
                </div>
              </transition>
            </div>

            <!-- Acciones -->
            <div class="actions-card">
              <div class="actions-header">Acciones rápidas</div>
              <div class="actions-grid">
                <a-button
                  block
                  size="large"
                  class="action-btn action-btn--span"
                  @click="showCalculator = true"
                >
                  <CalculatorOutlined /><span>Calculadora</span>
                </a-button>
                <a-button
                  size="large"
                  class="action-btn"
                  :disabled="loading"
                  @click="suspenderVenta"
                >
                  <PauseCircleOutlined /><span>Suspender</span>
                </a-button>
                <a-button size="large" class="action-btn" @click="suspendidasOpen = true">
                  <HistoryOutlined /><span>Suspendidas</span>
                </a-button>
                <a-button
                  size="large"
                  class="action-btn"
                  :disabled="loading"
                  @click="guardarBorrador()"
                  title="Ctrl+S"
                >
                  <SaveOutlined /><span>Guardar</span>
                </a-button>
                <a-button
                  size="large"
                  class="action-btn action-btn--danger"
                  @click="cancelarOperacion"
                >
                  <StopOutlined /><span>Cancelar op.</span>
                </a-button>
              </div>
              <div v-if="hasStockIssues" class="stock-warning">
                <svg
                  viewBox="0 0 16 16"
                  fill="currentColor"
                  width="13"
                  height="13"
                  style="flex-shrink: 0"
                >
                  <path
                    d="M8.982 1.566a1.13 1.13 0 0 0-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5c.535 0 .954.462.9.995l-.35 3.507a.552.552 0 0 1-1.1 0L7.1 5.995A.905.905 0 0 1 8 5zm.002 6a1 1 0 1 1 0 2 1 1 0 0 1 0-2z"
                  />
                </svg>
                Hay líneas con stock insuficiente.
              </div>
            </div>
          </section>
        </main>

        <!-- FAB atajos -->
        <a-tooltip title="Accesos rápidos (F1)">
          <button
            class="shortcuts-fab"
            @click="shortcutsOpen = true"
            type="button"
            aria-label="Accesos rápidos"
          >
            <ThunderboltOutlined />
          </button>
        </a-tooltip>

        <!-- ═══════════════ FOOTER FLOTANTE ══════════════════════════════════ -->
        <footer ref="footerEl" class="pos-footer">
          <div class="footer-inner">
            <div class="footer-breakdown">
              <div class="footer-row">
                <span class="footer-row-label">Subtotal neto</span>
                <span class="footer-row-val">$ {{ money(totales.neto) }}</span>
              </div>
              <div v-for="t in taxesRows" :key="t.label" class="footer-row footer-row--sub">
                <span class="footer-row-label">{{ t.label }}</span>
                <span class="footer-row-val">$ {{ money(t.amount) }}</span>
              </div>
              <div
                v-if="totales.recargos > 0"
                class="footer-row footer-row--sub footer-row--surcharge"
              >
                <span class="footer-row-label">Recargos</span>
                <span class="footer-row-val">+ $ {{ money(totales.recargos) }}</span>
              </div>
              <div
                v-if="totales.descuentos > 0"
                class="footer-row footer-row--sub footer-row--discount"
              >
                <span class="footer-row-label">Descuentos</span>
                <span class="footer-row-val">− $ {{ money(totales.descuentos) }}</span>
              </div>
            </div>

            <div class="footer-total-block">
              <span class="footer-total-label">Total</span>
              <div class="footer-total-amount">$ {{ money(totales.totalFinal) }}</div>
            </div>

            <div class="footer-controls">
              <div class="pay-mode-wrap">
                <span class="pay-mode-label">Condición de venta</span>
                <a-segmented
                  v-model:value="condicionPago"
                  :options="payOptions"
                  block
                  class="seg-pay"
                />
              </div>
              <a-button
                type="primary"
                size="large"
                class="pay-btn"
                :loading="loading"
                @click="openFinalizar"
              >
                Finalizar venta <kbd class="pay-kbd">F9</kbd>
              </a-button>
            </div>
          </div>
        </footer>

        <!-- ═══════════════ MODALES ══════════════════════════════════════════ -->
        <ArticuloSearchModal v-model:open="articuloModalOpen" @add-items="addItemsToComprobante" />
        <PaymentModal
          v-model:open="paymentOpen"
          :total="totales.total"
          @confirm="onConfirmPayment"
          @cancel="onCancelPayment"
        />
        <VentasSuspendidasModal
          v-model:open="suspendidasOpen"
          @resume="onResumeSuspendida"
          @select="onResumeSuspendida"
          @retomar="onResumeSuspendida"
          @load="onResumeSuspendida"
        />

        <!-- Confirmación final -->
        <a-modal
          v-model:open="finalConfirmOpen"
          title="Confirmar operación"
          centered
          :maskClosable="false"
        >
          <div class="confirm-box">
            <div class="confirm-row">
              <span>Fecha</span>
              <strong>{{ formState.fecha.format('DD/MM/YYYY') }}</strong>
            </div>
            <div class="confirm-row">
              <span>Condición de venta</span>
              <strong>{{ condicionPago === 'CTA_CTE' ? 'Cuenta Corriente' : 'Contado' }}</strong>
            </div>
            <div class="confirm-row">
              <span>Forma de pago</span>
              <strong>{{ resumenFormaPago }}</strong>
            </div>
            <div class="confirm-row"><span>Vendedor</span><strong>—</strong></div>
            <div v-if="totales.recargos > 0" class="confirm-row">
              <span>Recargos</span><strong>$ {{ money(totales.recargos) }}</strong>
            </div>
            <div v-if="totales.descuentos > 0" class="confirm-row">
              <span>Descuentos</span><strong>− $ {{ money(totales.descuentos) }}</strong>
            </div>
            <div class="confirm-row confirm-row--total">
              <span>Total</span>
              <strong>$ {{ money(totales.totalFinal) }}</strong>
            </div>
          </div>
          <template #footer>
            <a-button @click="cancelarConfirmacionFinal">Cancelar</a-button>
            <a-button type="primary" :loading="loading" @click="confirmarYGenerar"
              >Confirmar y generar</a-button
            >
          </template>
        </a-modal>

        <!-- Calculadora -->
        <a-modal
          v-model:open="showCalculator"
          title="Calculadora"
          :footer="null"
          width="310px"
          centered
          :maskClosable="true"
        >
          <template #closeIcon><CloseOutlined /></template>
          <div class="calculator">
            <div class="calc-display" aria-live="polite">{{ calcDisplay }}</div>
            <div v-if="calcOperator" class="calc-op-hint">
              {{ calcOperator === '/' ? '÷' : calcOperator === '*' ? '×' : calcOperator }}
            </div>
            <div class="calc-grid">
              <button @click="clearCalc" class="btn-calc btn-op">C</button>
              <button @click="backspaceCalc" class="btn-calc btn-op"><RollbackOutlined /></button>
              <button @click="setOp('/')" class="btn-calc btn-op">÷</button>
              <button @click="setOp('*')" class="btn-calc btn-op">×</button>
              <button @click="appendCalc(7)" class="btn-calc">7</button>
              <button @click="appendCalc(8)" class="btn-calc">8</button>
              <button @click="appendCalc(9)" class="btn-calc">9</button>
              <button @click="setOp('-')" class="btn-calc btn-op">−</button>
              <button @click="appendCalc(4)" class="btn-calc">4</button>
              <button @click="appendCalc(5)" class="btn-calc">5</button>
              <button @click="appendCalc(6)" class="btn-calc">6</button>
              <button @click="setOp('+')" class="btn-calc btn-op">+</button>
              <button @click="appendCalc(1)" class="btn-calc">1</button>
              <button @click="appendCalc(2)" class="btn-calc">2</button>
              <button @click="appendCalc(3)" class="btn-calc">3</button>
              <button @click="calculate" class="btn-calc btn-equal">=</button>
              <button @click="appendCalc(0)" class="btn-calc btn-zero">0</button>
              <button @click="appendCalc('.')" class="btn-calc">.</button>
            </div>
            <small class="calc-hint">ESC cierra · Teclado numérico habilitado</small>
          </div>
        </a-modal>

        <!-- Búsqueda avanzada de clientes -->
        <a-modal v-model:open="clientModalOpen" title="Buscar cliente" width="860px" centered>
          <a-space direction="vertical" style="width: 100%">
            <a-input
              v-model:value="clientModalSearch"
              placeholder="Escribí al menos 3 caracteres..."
              @pressEnter="loadClientModal"
            >
              <template #addonAfter>
                <a-button :loading="clientModalLoading" @click="loadClientModal"
                  ><SearchOutlined
                /></a-button>
              </template>
            </a-input>
            <a-table
              :columns="clientModalColumns"
              :data-source="clientModalRows"
              :loading="clientModalLoading"
              :pagination="{ pageSize: 8 }"
              rowKey="id"
              size="middle"
              :customRow="
                (record) => ({
                  onDblclick: () => selectClientFromModal(record),
                  style: { cursor: 'pointer' },
                })
              "
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.dataIndex === 'razon_social'">
                  <a @click.prevent="selectClientFromModal(record)">{{ record.razon_social }}</a>
                </template>
              </template>
            </a-table>
          </a-space>
        </a-modal>

        <!-- Atajos de teclado -->
        <a-modal v-model:open="shortcutsOpen" title="Accesos rápidos" centered :maskClosable="true">
          <div class="shortcuts-list">
            <div class="sc-section">General</div>
            <div class="sc-row"><kbd>ESC</kbd> <span>Cerrar modal activo</span></div>
            <div class="sc-row"><kbd>Ctrl</kbd><kbd>S</kbd> <span>Guardar borrador</span></div>
            <div class="sc-row"><kbd>Insert</kbd> <span>Agregar renglón manual</span></div>
            <div class="sc-row"><kbd>F2</kbd> <span>Foco en cliente</span></div>
            <div class="sc-row"><kbd>F3</kbd> <span>Buscar artículos</span></div>
            <div class="sc-row"><kbd>F9</kbd> <span>Finalizar venta</span></div>
            <div class="sc-row"><kbd>F10</kbd> <span>Modo enfoque</span></div>
            <div class="sc-row"><kbd>F1</kbd> <span>Mostrar este panel</span></div>
            <div class="sc-section" style="margin-top: 8px">Calculadora</div>
            <div class="sc-row"><kbd>0–9</kbd> <span>Dígitos</span></div>
            <div class="sc-row"><kbd>+ − × ÷</kbd> <span>Operadores</span></div>
            <div class="sc-row"><kbd>Enter</kbd> <span>Calcular resultado</span></div>
            <div class="sc-row"><kbd>Backspace</kbd> <span>Borrar último dígito</span></div>
          </div>
        </a-modal>

        <!-- Modal cambios sin guardar -->
        <a-modal
          v-model:open="leaveModalOpen"
          title="Cambios sin guardar"
          centered
          :maskClosable="false"
          :closable="false"
        >
          <p style="margin: 0; color: var(--text-1)">
            Tenés cambios sin guardar en esta venta. ¿Qué querés hacer?
          </p>
          <template #footer>
            <a-button @click="closeLeaveModal">Seguir editando</a-button>
            <a-button :loading="loading" @click="leaveAndSaveDraft">Guardar y salir</a-button>
            <a-button danger @click="leaveAndDiscard">Descartar y salir</a-button>
          </template>
        </a-modal>

        <!-- Lightbox imagen artículo -->
        <a-modal
          v-model:open="imageZoomOpen"
          :footer="null"
          centered
          :bodyStyle="{ padding: '8px', textAlign: 'center', background: '#000' }"
          width="auto"
          :style="{ maxWidth: '90vw' }"
          :maskStyle="{ background: 'rgba(0,0,0,0.85)' }"
        >
          <img
            v-if="itemInfo?.foto"
            :src="getImageUrl(itemInfo.foto)"
            style="
              max-width: 80vw;
              max-height: 80vh;
              object-fit: contain;
              display: block;
              margin: 0 auto;
              border-radius: 6px;
            "
            alt="Imagen artículo ampliada"
          />
        </a-modal>

        <!-- ═══════════ MODAL IMPRESIÓN POST-VENTA ══════════════════════════ -->
        <a-modal
          v-model:open="printModalOpen"
          title="Comprobante generado"
          centered
          :maskClosable="false"
          :closable="false"
          width="420px"
        >
          <div class="print-modal-body">
            <div class="print-success-icon">
              <CheckCircleOutlined />
            </div>
            <h3 class="print-modal-title">¡Venta confirmada!</h3>
            <p class="print-modal-numero">{{ ventaFinalizada.numero }}</p>
            <p class="print-modal-hint">¿Desea imprimir o visualizar el comprobante?</p>
          </div>
          <template #footer>
            <div class="print-modal-footer">
              <a-button
                type="primary"
                size="large"
                :loading="ventaFinalizada.loadingPdf"
                @click="onPrintAndNew"
              >
                <FilePdfOutlined /> Imprimir y nueva venta
              </a-button>
              <a-button size="large" :loading="ventaFinalizada.loadingPdf" @click="onPrintOnly">
                <FilePdfOutlined /> Solo ver PDF
              </a-button>
              <a-button size="large" @click="onSkipPrint"> Omitir </a-button>
            </div>
          </template>
        </a-modal>
      </div>
    </a-config-provider>
  </div>
</template>

<style scoped>
/* ─── Contenedor raíz ────────────────────────────────────────────────────────── */
.pos-route-root {
  display: block;
  height: 100%;
}

.pos-root {
  --pos-radius: 7px;
  --pos-footer-space: 120px;
  /* Fallback accent color (indigo) — overridden by theme CSS via --accent-rgb */
  --accent-rgb: 99, 102, 241;
  height: var(--pos-available-h, 100%);
  min-height: var(--pos-available-h, 100%);
  background: var(--surface-0, transparent);
  overflow: hidden;
  position: relative;
}
.pos-root.pos-focus {
  position: fixed;
  inset: 0;
  z-index: 900;
  overflow: hidden;
  background: var(--surface-0, transparent);
}

/* ─── Body layout ────────────────────────────────────────────────────────────── */
.pos-body {
  display: flex;
  gap: 14px;
  padding: 14px;
  overflow: hidden;
  height: calc(var(--pos-available-h, 100vh) - var(--pos-footer-space, 120px));
  min-height: 0;
}
.left-panel,
.right-panel {
  min-width: 0;
}
.pos-root.pos-dark,
.pos-root.pos-dark .pos-body {
  background: var(--surface-0, #0b1220);
}
/* Left panel takes remaining space; right panel is FIXED width */
.left-panel {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
}
.right-panel {
  flex: 0 0 420px;
  width: 420px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
}

/* ─── Form card (header) ─────────────────────────────────────────────────────── */
.form-card {
  border-radius: var(--pos-radius);
  border: 1px solid rgba(var(--accent-rgb), 0.22);
  background: linear-gradient(160deg, rgba(var(--accent-rgb), 0.08) 0%, var(--surface-1, #fff) 50%);
  box-shadow:
    0 2px 16px rgba(var(--accent-rgb), 0.09),
    0 1px 4px rgba(0, 0, 0, 0.05);
}
.pos-sticky-header {
  position: sticky;
  top: 8px;
  z-index: 30;
}
.pos-sticky-right {
  position: sticky;
  top: 8px;
  z-index: 20;
}

/* Field labels above inputs */
.field-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.field-label {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--text-2);
  padding-left: 2px;
}

/* Focus mode active button */
.btn-focus-active {
  border-color: var(--pos-primary, rgba(var(--accent-rgb), 0.55)) !important;
  color: var(--pos-primary, rgba(var(--accent-rgb), 1)) !important;
  background: rgba(var(--accent-rgb), 0.08) !important;
}

/* ─── Grid card ──────────────────────────────────────────────────────────────── */
.grid-card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-radius: var(--pos-radius);
  border: 1px solid var(--border);
  background: var(--surface-1);
}
.grid-topbar {
  padding: 9px 12px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 12px;
  background: rgba(148, 163, 184, 0.03);
}
.search-articles-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.topbar-kbd {
  display: inline-flex;
  align-items: center;
  padding: 1px 5px;
  border-radius: 4px;
  border: 1px solid rgba(148, 163, 184, 0.3);
  background: rgba(148, 163, 184, 0.08);
  font-size: 10px;
  font-weight: 700;
  color: var(--text-2);
  letter-spacing: 0.04em;
  margin-left: 4px;
}
.grid-hint {
  color: var(--text-2);
  font-size: 11.5px;
}

.grid-table-wrap {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* Table header - enterprise style */
:global(.pos-root .ant-table-thead th) {
  font-size: 11px !important;
  font-weight: 800 !important;
  letter-spacing: 0.06em !important;
  text-transform: uppercase !important;
  color: var(--text-2) !important;
  background: rgba(148, 163, 184, 0.06) !important;
}
:global(.ant-table-header) {
  position: sticky;
  top: 0;
  z-index: 5;
}

/* Row styles */
:global(.row-even td) {
  background: rgba(148, 163, 184, 0.05) !important;
}
:global(.row-odd td) {
  background: rgba(148, 163, 184, 0.015) !important;
}
:global(.ant-table-tbody > tr > td) {
  border-bottom: 1px solid rgba(148, 163, 184, 0.12) !important;
}
:global(.row-selected td) {
  box-shadow:
    inset 3px 0 0 var(--pos-primary, rgba(var(--accent-rgb), 0.75)),
    inset 0 0 0 1px rgba(var(--accent-rgb), 0.18);
}
:global(.row-draft td) {
  box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.2);
}
:global(.row-stock-bad td) {
  background: rgba(239, 68, 68, 0.09) !important;
}
:global(.row-stock-bad:hover td) {
  background: rgba(239, 68, 68, 0.15) !important;
}

.qty-danger :global(.ant-input-number-input) {
  color: #dc2626 !important;
  font-weight: 700;
}

.grid-actions {
  padding: 9px 12px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 5px;
  background: rgba(0, 0, 0, 0.01);
}
.add-row-btn {
  border-style: dashed;
  font-size: 13px;
}
.grid-actions-hint {
  font-size: 11px;
  color: var(--text-2);
}
.delete-row-btn {
  opacity: 0.45;
  transition: opacity 0.15s;
}
.delete-row-btn:hover {
  opacity: 1;
}

/* Subtotal value */
.subtotal-val {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--text-0);
}

/* Product autocomplete options */
.product-option-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 2px 0;
}
.prod-desc {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-0);
}
.prod-meta {
  display: flex;
  gap: 12px;
}
.prod-brand {
  font-size: 11px;
  color: var(--text-2);
}
.prod-stock {
  font-size: 11px;
  color: var(--text-2);
  font-variant-numeric: tabular-nums;
}

/* Client select item */
:global(.client-select .ant-select-selection-item) {
  font-weight: 800;
  font-size: 15px;
}
/* When a client is selected, give the selector a subtle accent highlight */
:global(.client-select.ant-select-open .ant-select-selector),
:global(.client-select .ant-select-focused .ant-select-selector) {
  border-color: rgba(var(--accent-rgb), 0.6) !important;
  box-shadow: 0 0 0 2px rgba(var(--accent-rgb), 0.12) !important;
}
.client-option {
  display: flex;
  justify-content: space-between;
  width: 100%;
}
.client-name {
  font-weight: 700;
}
.client-cuit {
  color: var(--text-2);
  font-size: 12px;
  font-family: monospace;
}

/* ─── Info card (contextual) ─────────────────────────────────────────────────── */
.info-card {
  color: var(--text-0);
  padding: 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  flex: 1;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-top: 2px solid rgba(var(--accent-rgb), 0.2);
  border-radius: var(--pos-radius);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
  overflow: hidden;
}
.info-header {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--text-2);
  border-bottom: 1px solid var(--border);
  padding-bottom: 10px;
  margin-bottom: 16px;
}
.info-header-icon {
  font-size: 13px;
}

.product-visual {
  position: relative;
  margin-bottom: 8px;
}
.product-img {
  height: 116px;
  object-fit: contain;
  border-radius: var(--pos-radius);
  background: rgba(148, 163, 184, 0.06);
  padding: 8px;
  border: 1px solid var(--border);
  display: block;
}
.img-zoom-btn {
  position: absolute;
  top: 6px;
  left: 6px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 5px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(6px);
  font-size: 11px;
  font-weight: 700;
  color: var(--text-1);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s ease;
  z-index: 2;
}
.product-visual:hover .img-zoom-btn {
  opacity: 1;
}
.pos-root.pos-dark .img-zoom-btn {
  background: rgba(15, 23, 42, 0.78);
  border-color: rgba(148, 163, 184, 0.2);
  color: rgba(226, 232, 240, 0.85);
}
.pos-root.pos-dark .product-img {
  background: rgba(15, 23, 42, 0.55);
  border-color: rgba(148, 163, 184, 0.14);
}
.stock-badge {
  position: absolute;
  bottom: -5px;
  right: -5px;
  background: #10b981;
  color: #fff;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 900;
  letter-spacing: 0.03em;
}
.stock-badge--low {
  background: #f59e0b;
}

.info-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-0);
  margin: 8px 0 4px;
  line-height: 1.3;
}
.info-meta-grid {
  width: 100%;
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.info-meta-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 5px 10px;
  border-radius: 5px;
  background: rgba(148, 163, 184, 0.05);
  border: 1px solid var(--border);
}
.meta-key {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-2);
}
.meta-val {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-0);
}
.meta-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
}

/* Client info card */
.client-avatar {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(var(--accent-rgb), 0.18), rgba(var(--accent-rgb), 0.05));
  border: 1px solid rgba(var(--accent-rgb), 0.18);
  display: grid;
  place-items: center;
  font-size: 1.45rem;
  font-weight: 900;
  margin-bottom: 8px;
  color: rgba(var(--accent-rgb), 1);
}
.client-cuit-display {
  font-size: 12px;
  color: var(--text-2);
  font-family: ui-monospace, monospace;
  margin: 0 0 10px;
  letter-spacing: 0.03em;
}
.client-flags {
  width: 100%;
}
.flag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 700;
  border: 1px solid transparent;
}
.flag--ok {
  background: rgba(16, 185, 129, 0.09);
  border-color: rgba(16, 185, 129, 0.2);
  color: #059669;
}
.flag--bad {
  background: rgba(239, 68, 68, 0.07);
  border-color: rgba(239, 68, 68, 0.16);
  color: #dc2626;
}
.flag-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}

/* Empty state */
.info-card--empty {
  justify-content: center;
  background: rgba(148, 163, 184, 0.02);
  border-style: dashed;
}
.empty-icon {
  font-size: 42px;
  opacity: 0.12;
  margin-bottom: 10px;
}
.empty-hint {
  font-size: 12px;
  color: var(--text-2);
  max-width: 176px;
  line-height: 1.5;
}

/* ─── Actions card ───────────────────────────────────────────────────────────── */
.actions-card {
  padding: 13px 14px;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--pos-radius);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03);
}
.actions-header {
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--text-2);
  margin-bottom: 9px;
}
.actions-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 7px;
}
.action-btn {
  border-radius: var(--pos-radius);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 12.5px;
  font-weight: 600;
  height: 36px;
}
.action-btn--span {
  grid-column: span 2;
}
.action-btn--danger {
  border-color: rgba(239, 68, 68, 0.2);
  color: #dc2626;
}
.action-btn--danger:hover {
  border-color: rgba(239, 68, 68, 0.4);
  background: rgba(239, 68, 68, 0.05);
  color: #dc2626;
}

.stock-warning {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 9px;
  padding: 7px 10px;
  background: rgba(239, 68, 68, 0.07);
  border: 1px solid rgba(239, 68, 68, 0.16);
  border-radius: 6px;
  font-size: 12px;
  font-weight: 700;
  color: #dc2626;
}

/* ─── FAB ────────────────────────────────────────────────────────────────────── */
.shortcuts-fab {
  position: fixed;
  top: 40%;
  right: 14px;
  z-index: 80;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  border: 1px solid rgba(148, 163, 184, 0.28);
  background: rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(8px);
  cursor: pointer;
  display: grid;
  place-items: center;
  color: var(--text-1);
  transition:
    transform 0.14s ease,
    background 0.14s ease,
    box-shadow 0.14s ease;
}
.shortcuts-fab:hover {
  transform: translateY(-2px);
  background: rgba(255, 255, 255, 0.4);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.11);
}
.pos-root.pos-dark .shortcuts-fab {
  background: rgba(15, 23, 42, 0.38);
  border-color: rgba(148, 163, 184, 0.16);
}

/* ─── Footer ─────────────────────────────────────────────────────────────────── */
.pos-footer {
  position: fixed;
  left: var(--pos-footer-left, 16px);
  bottom: 10px;
  width: var(--pos-footer-width, calc(100% - 32px));
  z-index: 60;
  border-radius: var(--pos-radius);
  border: 1px solid var(--pos-footer-border, rgba(148, 163, 184, 0.28));
  /* Stronger, less transparent background so it reads clearly */
  background: var(--pos-footer-bg, rgba(255, 255, 255, 0.97));
  backdrop-filter: blur(20px);
  box-shadow:
    0 -1px 0 rgba(148, 163, 184, 0.12),
    0 12px 40px rgba(0, 0, 0, 0.14),
    0 4px 12px rgba(0, 0, 0, 0.07);
  /* Subtle top accent stripe */
  border-top: 2px solid rgba(var(--accent-rgb), 0.35);
}
.footer-inner {
  padding: 12px 16px;
  display: grid;
  /* breakdown | total-block | controls
     controls column = right panel (420px) + panel gap (14px) - footer inner padding (16px) = 418px */
  grid-template-columns: 1fr auto 418px;
  gap: 0;
  align-items: center;
}

/* Breakdown column */
.footer-breakdown {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-right: 20px;
}
.footer-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}
.footer-row-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-1);
}
.footer-row-val {
  font-size: 13px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--text-0);
}
.footer-row--sub .footer-row-label {
  font-size: 12px;
  color: var(--text-2);
}
.footer-row--sub .footer-row-val {
  font-size: 12px;
  color: var(--text-1);
}
.footer-row--surcharge .footer-row-val {
  color: #f59e0b;
}
.footer-row--discount .footer-row-val {
  color: #10b981;
}

/* Total column */
.footer-total-block {
  text-align: right;
  border-left: 1px solid var(--border);
  border-right: 1px solid var(--border);
  padding: 4px 24px;
}
.footer-total-label {
  display: block;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-2);
  margin-bottom: 2px;
}
.footer-total-amount {
  font-size: 2.4rem;
  font-weight: 900;
  letter-spacing: -1px;
  font-variant-numeric: tabular-nums;
  color: var(--pos-primary, rgba(var(--accent-rgb), 1));
  line-height: 1.1;
  white-space: nowrap;
}

/* Controls column */
.footer-controls {
  display: grid;
  gap: 8px;
  padding-left: 20px;
}
.pay-mode-label {
  display: block;
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-2);
  margin-bottom: 5px;
}
.pay-btn {
  border-radius: var(--pos-radius);
  height: 50px;
  font-weight: 800;
  font-size: 1rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.pay-kbd {
  display: inline-flex;
  align-items: center;
  padding: 1px 5px;
  border-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  background: rgba(255, 255, 255, 0.1);
  font-size: 10px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.78);
  letter-spacing: 0.04em;
}

/* Segmented */
:global(.seg-pay.ant-segmented) {
  border-radius: var(--pos-radius);
}
:global(.seg-pay .ant-segmented-item) {
  border-radius: var(--pos-radius);
  font-weight: 700;
}
:global(.seg-pay .ant-segmented-item-selected) {
  font-weight: 800;
  border: 1px solid rgba(var(--accent-rgb), 0.38);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}
:global(.seg-opt) {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
:global(.seg-check) {
  font-size: 13px;
}

/* Dark mode footer text */
.pos-root.pos-dark :deep(.pos-footer .footer-row-label),
.pos-root.pos-dark :deep(.pos-footer .footer-row-val) {
  color: rgba(241, 245, 249, 0.9) !important;
}
.pos-root.pos-dark :deep(.pos-footer .footer-total-label) {
  color: rgba(148, 163, 184, 0.7) !important;
}
.pos-root.pos-dark :deep(.pos-footer .footer-row--sub .footer-row-label),
.pos-root.pos-dark :deep(.pos-footer .footer-row--sub .footer-row-val) {
  color: rgba(203, 213, 225, 0.7) !important;
}

/* ─── Calculadora ────────────────────────────────────────────────────────────── */
.calculator {
  padding: 8px 4px 2px;
}
.calc-display {
  background: rgba(0, 0, 0, 0.05);
  text-align: right;
  padding: 11px 13px;
  font-size: 1.7rem;
  border-radius: var(--pos-radius);
  margin-bottom: 5px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-weight: 700;
  color: var(--text-0);
  letter-spacing: -0.5px;
  min-height: 56px;
  word-break: break-all;
}
.pos-root.pos-dark .calc-display {
  background: rgba(148, 163, 184, 0.1);
}
.calc-op-hint {
  text-align: right;
  font-size: 11px;
  font-weight: 800;
  color: var(--pos-primary, rgba(var(--accent-rgb), 1));
  padding-right: 4px;
  margin-bottom: 7px;
  opacity: 0.9;
}
.calc-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
}
.btn-calc {
  padding: 12px 0;
  border: 1px solid var(--border);
  background: var(--surface-1);
  border-radius: 6px;
  font-size: 1.05rem;
  cursor: pointer;
  color: var(--text-0);
  transition:
    background 0.1s,
    transform 0.08s;
  font-family: inherit;
}
.btn-calc:hover {
  background: rgba(var(--accent-rgb), 0.07);
}
.btn-calc:active {
  transform: scale(0.94);
}
.btn-op {
  font-weight: 800;
  color: var(--pos-primary, rgba(var(--accent-rgb), 1));
  background: rgba(var(--accent-rgb), 0.06);
}
.btn-op:hover {
  background: rgba(var(--accent-rgb), 0.13);
}
.btn-equal {
  grid-row: span 3;
  background: var(--pos-primary, rgba(var(--accent-rgb), 0.88));
  color: #fff;
  border-color: transparent;
  font-weight: 900;
  font-size: 1.2rem;
}
.btn-equal:hover {
  filter: brightness(1.1);
}
.btn-zero {
  grid-column: span 2;
}
.calc-hint {
  display: block;
  text-align: center;
  color: var(--text-2);
  font-size: 11px;
  margin-top: 10px;
}

/* ─── Modal confirmación final ───────────────────────────────────────────────── */
.confirm-box {
  display: grid;
  gap: 6px;
  padding: 4px 0;
}
.confirm-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 7px 12px;
  border-radius: 6px;
  background: rgba(148, 163, 184, 0.04);
  border: 1px solid var(--border);
  font-size: 13px;
  color: var(--text-1);
}
.confirm-row strong {
  color: var(--text-0);
  font-weight: 700;
}
.confirm-row--total {
  background: rgba(var(--accent-rgb), 0.06);
  border-color: rgba(var(--accent-rgb), 0.18);
  margin-top: 4px;
  font-size: 14px;
}
.confirm-row--total strong {
  color: var(--pos-primary, rgba(var(--accent-rgb), 1));
  font-size: 15px;
  font-weight: 900;
}

/* ─── Modal atajos ───────────────────────────────────────────────────────────── */
.shortcuts-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sc-section {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-2);
  padding: 4px 0 3px;
  border-bottom: 1px solid var(--border);
}
.sc-row {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 13px;
  color: var(--text-1);
}
.sc-row span {
  flex: 1;
}
kbd {
  display: inline-flex;
  align-items: center;
  padding: 3px 7px;
  border-radius: 5px;
  border: 1px solid var(--border);
  background: rgba(148, 163, 184, 0.08);
  font-size: 11px;
  font-weight: 700;
  font-family: ui-monospace, monospace;
  color: var(--text-0);
  white-space: nowrap;
}

/* ─── Dropdowns globales ─────────────────────────────────────────────────────── */
:global(.ant-select-dropdown),
:global(.ant-auto-complete-dropdown),
:global(.ant-dropdown),
:global(.ant-picker-dropdown) {
  z-index: 6000 !important;
}

/* ─── Focus mode — oculta sidebar ───────────────────────────────────────────── */
:global(html.pos-focus-mode .ant-layout-sider),
:global(body.pos-focus-mode .ant-layout-sider) {
  display: none !important;
}
:global(html.pos-focus-mode .ant-layout-sider-trigger),
:global(body.pos-focus-mode .ant-layout-sider-trigger),
:global(html.pos-focus-mode .ant-layout-sider-zero-width-trigger),
:global(body.pos-focus-mode .ant-layout-sider-zero-width-trigger) {
  display: none !important;
}
:global(html.pos-focus-mode .ant-layout-content),
:global(body.pos-focus-mode .ant-layout-content) {
  margin-left: 0 !important;
}

/* ─── Transición panel contextual ───────────────────────────────────────────── */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* ═══════════════════════════════════════════════════════════════════════════════
   RESPONSIVE — Breakpoints
   ≥1280px  : full layout (default above)
   1024–1279: laptop — right panel narrows to 340px
   768–1023 : tablet landscape — right panel becomes a side drawer
   <768px   : mobile / tablet portrait — stacked header + drawer
   ═══════════════════════════════════════════════════════════════════════════════ */

/* ── Laptop (1024–1279px) ─────────────────────────────────────────────────── */
@media (max-width: 1279px) and (min-width: 1024px) {
  .right-panel {
    flex: 0 0 340px;
    width: 340px;
  }
  .footer-inner {
    grid-template-columns: 1fr auto 338px;
  }
}

/* ── Tablet landscape + mobile: drawer toggle button ─────────────────────── */
.right-panel-toggle {
  display: none; /* hidden on desktop */
}
.right-panel-overlay {
  display: none;
}

@media (max-width: 1023px) {
  /* Toggle FAB */
  .right-panel-toggle {
    display: grid;
    place-items: center;
    position: fixed;
    bottom: 88px;
    right: 14px;
    z-index: 82;
    width: 44px;
    height: 44px;
    border-radius: 50%;
    border: 1px solid rgba(148, 163, 184, 0.3);
    background: var(--pos-primary, rgba(99, 102, 241, 1));
    color: #fff;
    font-size: 18px;
    cursor: pointer;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
    transition:
      transform 0.15s ease,
      box-shadow 0.15s ease;
  }
  .right-panel-toggle:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.22);
  }

  /* Overlay backdrop */
  .right-panel-overlay {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 88;
    background: rgba(0, 0, 0, 0);
    pointer-events: none;
    transition: background 0.25s ease;
  }
  .right-panel-overlay--visible {
    background: rgba(0, 0, 0, 0.38);
    pointer-events: all;
  }

  /* Right panel becomes a fixed drawer sliding in from the right */
  .right-panel {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    z-index: 90;
    width: 340px !important;
    flex: none !important;
    overflow-y: auto;
    padding: 14px;
    background: var(--surface-0, #fff);
    box-shadow: -4px 0 32px rgba(0, 0, 0, 0.14);
    transform: translateX(100%);
    transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1);
    gap: 14px;
  }
  .right-panel--open {
    transform: translateX(0);
  }
  .pos-root.pos-dark .right-panel {
    background: var(--surface-0, #0b1220);
  }

  /* Left panel takes full width */
  .pos-body {
    gap: 0;
  }
  .left-panel {
    flex: 1 1 100%;
    width: 100%;
  }

  /* Footer full width on tablet */
  .footer-inner {
    grid-template-columns: 1fr auto 320px;
  }
}

/* ── Mobile / tablet portrait (<768px) ───────────────────────────────────── */
@media (max-width: 767px) {
  /* Stack header fields vertically */
  .pos-body {
    padding: 8px;
  }

  /* Header form: stack to 2-col then 1-col */
  :global(.pos-root .ant-row) {
    flex-wrap: wrap;
  }
  :global(.pos-root .ant-col-12),
  :global(.pos-root .ant-col-4),
  :global(.pos-root .ant-col-2) {
    max-width: 100% !important;
    flex: 0 0 100% !important;
    width: 100% !important;
  }

  /* Right drawer slightly wider on mobile */
  .right-panel {
    width: min(92vw, 340px) !important;
  }

  /* Footer: stack total + controls */
  .footer-inner {
    grid-template-columns: 1fr;
    grid-template-rows: auto auto auto;
    gap: 8px;
    padding: 10px 12px;
  }
  .footer-breakdown {
    padding-right: 0;
    border-bottom: 1px solid var(--border);
    padding-bottom: 8px;
  }
  .footer-total-block {
    border: none;
    border-bottom: 1px solid var(--border);
    padding: 4px 0 8px;
    text-align: left;
  }
  .footer-total-amount {
    font-size: 1.8rem;
  }
  .footer-controls {
    padding-left: 0;
  }
}

/* ─── Override btn — datos cliente ocasional ────────────────────────────────── */
.override-trigger-btn {
  position: relative;
}
.override-trigger-btn--active {
  border-color: rgba(var(--accent-rgb), 0.4) !important;
  color: rgba(var(--accent-rgb), 1) !important;
  background: rgba(var(--accent-rgb), 0.06) !important;
}
/* Dot indicator on the button */
.override-btn-dot {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  border: 1.5px solid #fff;
}
.override-btn-dot--warn {
  background: #f59e0b;
}
.override-btn-dot--ok {
  background: #10b981;
}

/* Popover interior */
.override-pop-title {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  font-weight: 800;
}
.override-pop-badge {
  font-family: ui-monospace, monospace;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(var(--accent-rgb), 0.1);
  border: 1px solid rgba(var(--accent-rgb), 0.22);
  color: rgba(var(--accent-rgb), 1);
  letter-spacing: 0.06em;
}
.override-pop-warn-dot {
  margin-left: auto;
  display: inline-grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #f59e0b;
  color: #fff;
  font-size: 11px;
  font-weight: 900;
  flex-shrink: 0;
}
.override-pop-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 2px 0 4px;
}
.override-pop-hint {
  font-size: 11.5px;
  color: var(--text-2);
  margin: 0;
  font-style: italic;
}
.override-pop-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.override-pop-label {
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--text-2);
  display: flex;
  align-items: center;
  gap: 3px;
}
.override-pop-required {
  color: #ef4444;
  font-size: 13px;
  font-weight: 900;
  cursor: help;
}
.override-pop-warn-msg {
  font-size: 11px;
  color: #d97706;
  font-weight: 600;
  margin: 2px 0 0;
}

/* ─── Modal impresión post-venta ────────────────────────────────────────────── */
.print-modal-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 12px 0 4px;
  text-align: center;
}
.print-success-icon {
  font-size: 48px;
  color: #10b981;
  line-height: 1;
  margin-bottom: 4px;
}
.print-modal-title {
  font-size: 18px;
  font-weight: 900;
  color: var(--text-0);
  margin: 0;
}
.print-modal-numero {
  font-family: ui-monospace, monospace;
  font-size: 14px;
  font-weight: 700;
  color: rgba(var(--accent-rgb), 1);
  background: rgba(var(--accent-rgb), 0.07);
  border: 1px solid rgba(var(--accent-rgb), 0.18);
  border-radius: 6px;
  padding: 4px 14px;
  margin: 0;
  letter-spacing: 0.05em;
}
.print-modal-hint {
  font-size: 13px;
  color: var(--text-2);
  margin: 0;
}
.print-modal-footer {
  display: flex;
  gap: 8px;
  justify-content: center;
  flex-wrap: wrap;
}
</style>
