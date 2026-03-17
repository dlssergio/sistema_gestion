<script setup>
/**
 * ConsultaComprobantes.vue — Centro de Control de Comprobantes
 * Versión Enterprise — superior a SAP B1, Dynamics 365, Odoo, Calipso
 *
 * [E1]  PDF con auth JWT — blob via Axios (resuelve 401 de window.open)
 * [E2]  Quick-ranges: Hoy / Semana / Mes / Trimestre / Año con 1 click
 * [E3]  Chips de filtros activos — búsqueda facetada visible y removible
 * [E4]  Filtros guardados como favoritos con nombre (localStorage)
 * [E5]  Columnas configurables: mostrar/ocultar + persistencia localStorage
 * [E6]  Selección múltiple + barra de acciones en batch
 * [E7]  Exportar CSV con BOM UTF-8 (compatible Excel Argentina)
 * [E8]  KPIs dinámicos: total período, con/sin CAE, CAE por vencer
 * [E9]  Semáforo CAE: días restantes con color (ok / alerta / crítico / vencido)
 * [E10] Estado de cobro: Cobrado / Parcial / Pendiente (más granular que estado)
 * [E11] Envío de email por comprobante con 1 click
 * [E12] Columnas ordenables server-side
 * [E13] Totales de página en footer de tabla
 * [E14] Atajos de teclado: F5 actualizar, Ctrl+E exportar, Esc cerrar detalle
 * [E15] Loading per-row para PDF (no bloquea toda la tabla)
 * [E16] Panel de detalle deslizante con info completa + acciones
 */

import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import dayjs from 'dayjs'
import { message } from 'ant-design-vue'
import {
  SearchOutlined,
  ReloadOutlined,
  FilePdfOutlined,
  EyeOutlined,
  CloseOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  StopOutlined,
  WarningOutlined,
  FileTextOutlined,
  UserOutlined,
  CalendarOutlined,
  DollarOutlined,
  TagOutlined,
  StarOutlined,
  StarFilled,
  MailOutlined,
  DownloadOutlined,
  SettingOutlined,
  FilterOutlined,
  ThunderboltOutlined,
  ExclamationCircleOutlined,
  CheckOutlined,
} from '@ant-design/icons-vue'
import api from '@/services/api'

// ── Constants ──────────────────────────────────────────────────────────────
const ESTADOS = [
  { value: '', label: 'Todos los estados' },
  { value: 'CN', label: 'Confirmado' },
  { value: 'BR', label: 'Borrador' },
  { value: 'AN', label: 'Anulado' },
]
const CONDICIONES = [
  { value: '', label: 'Todas' },
  { value: 'CO', label: 'Contado' },
  { value: 'CC', label: 'Cuenta Corriente' },
]
const QUICK_RANGES = [
  { label: 'Hoy', from: () => dayjs().startOf('day'), to: () => dayjs().endOf('day') },
  { label: 'Semana', from: () => dayjs().startOf('week'), to: () => dayjs().endOf('week') },
  { label: 'Mes', from: () => dayjs().startOf('month'), to: () => dayjs().endOf('month') },
  {
    label: 'Trimestre',
    from: () => dayjs().startOf('quarter'),
    to: () => dayjs().endOf('quarter'),
  },
  { label: 'Año', from: () => dayjs().startOf('year'), to: () => dayjs().endOf('year') },
]
const PAGE_SIZE_OPTIONS = ['10', '20', '50', '100']
const STORAGE_FAVS_KEY = 'cc_favoritos_v1'
const STORAGE_COLS_KEY = 'cc_columnas_v1'

// ── Column definitions ─────────────────────────────────────────────────────
const ALL_COLUMNS = [
  { key: 'numero_completo', title: 'Comprobante', width: 155, fixedLeft: true },
  { key: 'fecha', title: 'Fecha', width: 108, sortable: true },
  { key: 'cliente', title: 'Cliente', width: 220 },
  { key: 'tipo', title: 'Tipo', width: 110, align: 'center' },
  { key: 'estado', title: 'Estado', width: 112, align: 'center' },
  { key: 'cobro', title: 'Cobro', width: 108, align: 'center' },
  { key: 'condicion_venta', title: 'Condición', width: 108, align: 'center' },
  { key: 'total', title: 'Total', width: 128, align: 'right', sortable: true },
  { key: 'cae', title: 'CAE', width: 98, align: 'center' },
  { key: 'actions', title: '', width: 92, fixedRight: true },
]

// ── State ──────────────────────────────────────────────────────────────────
const loading = ref(false)
const loadingEmail = ref(null)
const rows = ref([])
const total = ref(0)
const tiposComprobante = ref([])

const filters = reactive({
  search: '',
  estado: 'CN',
  tipo_comprobante: '',
  condicion_venta: '',
  fecha_desde: dayjs().startOf('month'),
  fecha_hasta: dayjs(),
  ordering: '-fecha',
})

const pagination = reactive({ current: 1, pageSize: 20 })

// [E15] Per-row PDF loading — no bloquea la tabla completa
const loadingPdfIds = ref(new Set())

// [E6] Bulk selection
const selectedRowKeys = ref([])

// [E4] Favoritos
const favoritos = ref([])
const favNombreInput = ref('')
const showFavPopover = ref(false)

// [E5] Column config
const visibleCols = ref(new Set(ALL_COLUMNS.map((c) => c.key)))
const showColConfig = ref(false)

// [E16] Detail panel
const detailOpen = ref(false)
const detailRecord = ref(null)

// ── Filter chips [E3] ──────────────────────────────────────────────────────
const filterChips = computed(() => {
  const chips = []
  if (filters.estado)
    chips.push({ key: 'estado', label: ESTADOS.find((e) => e.value === filters.estado)?.label })
  if (filters.tipo_comprobante)
    chips.push({
      key: 'tipo_comprobante',
      label: tiposComprobante.value.find((t) => t.value === filters.tipo_comprobante)?.label,
    })
  if (filters.condicion_venta)
    chips.push({
      key: 'condicion_venta',
      label: CONDICIONES.find((c) => c.value === filters.condicion_venta)?.label,
    })
  if (filters.fecha_desde || filters.fecha_hasta)
    chips.push({
      key: 'fechas',
      label: `${filters.fecha_desde?.format('DD/MM') || '…'} → ${filters.fecha_hasta?.format('DD/MM') || '…'}`,
    })
  if (filters.search) chips.push({ key: 'search', label: `"${filters.search}"` })
  return chips
})

const removeChip = (key) => {
  if (key === 'estado') filters.estado = ''
  if (key === 'tipo_comprobante') filters.tipo_comprobante = ''
  if (key === 'condicion_venta') filters.condicion_venta = ''
  if (key === 'search') filters.search = ''
  if (key === 'fechas') {
    filters.fecha_desde = null
    filters.fecha_hasta = null
  }
  onFilterChange()
}

// ── KPIs [E8] ──────────────────────────────────────────────────────────────
const kpis = computed(() => {
  const r = rows.value
  return {
    totalSum: r.reduce((a, c) => a + Number(c.total || 0), 0),
    saldoSum: r.reduce((a, c) => a + Number(c.saldo_pendiente || 0), 0),
    conCae: r.filter((c) => c.cae).length,
    sinCae: r.filter((c) => !c.cae && c.estado === 'CN').length,
    caePorVencer: r.filter((c) => {
      if (!c.vto_cae) return false
      const d = dayjs(c.vto_cae).diff(dayjs(), 'day')
      return d >= 0 && d <= 7
    }).length,
  }
})

// ── Dynamic columns [E5] ───────────────────────────────────────────────────
const columns = computed(() =>
  ALL_COLUMNS.filter((c) => visibleCols.value.has(c.key)).map((c) => ({
    title: c.title,
    dataIndex: c.key,
    key: c.key,
    width: c.width,
    align: c.align,
    fixed: c.fixedLeft ? 'left' : c.fixedRight ? 'right' : undefined,
    sorter: c.sortable || undefined,
  })),
)

// ── Helpers ────────────────────────────────────────────────────────────────
const moneyAR = (n) =>
  (Number(n) || 0).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const fmtFecha = (v) => (v ? dayjs(v).format('DD/MM/YYYY') : '—')
const fmtFechaHora = (v) => (v ? dayjs(v).format('DD/MM/YYYY HH:mm') : '—')

const estadoConfig = {
  CN: { label: 'Confirmado', color: 'success' },
  BR: { label: 'Borrador', color: 'warning' },
  AN: { label: 'Anulado', color: 'error' },
}
const condicionLabel = { CO: 'Contado', CC: 'Cta. Cte.' }

const clienteNombre = (r) => r.cliente_nombre_override || r.cliente?.entidad?.razon_social || '—'
const clienteCuit = (r) => r.cliente_cuit_override || r.cliente?.entidad?.cuit || '—'

// [E10] Estado de cobro granular
const cobroStatus = (r) => {
  if (r.estado === 'AN') return { label: 'Anulado', cls: 'cobro--anulado' }
  if (r.estado === 'BR') return { label: 'Borrador', cls: 'cobro--borrador' }
  const saldo = Number(r.saldo_pendiente ?? r.total ?? 0)
  const tot = Number(r.total || 0)
  if (saldo <= 0) return { label: 'Cobrado', cls: 'cobro--ok' }
  if (saldo < tot) return { label: 'Parcial', cls: 'cobro--parcial' }
  return { label: 'Pendiente', cls: 'cobro--pendiente' }
}

// [E9] Semáforo de vencimiento CAE
const caeVencimiento = (r) => {
  if (!r.cae || !r.vto_cae) return null
  const dias = dayjs(r.vto_cae).diff(dayjs(), 'day')
  if (dias < 0)
    return { dias: Math.abs(dias), label: `Vencido hace ${Math.abs(dias)}d`, cls: 'cae-vencido' }
  if (dias <= 3) return { dias, label: `Vence en ${dias}d`, cls: 'cae-critico' }
  if (dias <= 7) return { dias, label: `Vence en ${dias}d`, cls: 'cae-alerta' }
  return { dias, label: `CAE ok (${dias}d)`, cls: 'cae-ok' }
}

// ── PDF con JWT blob [E1] [E15] ────────────────────────────────────────────
const openPdf = async (record) => {
  if (!record?.id || loadingPdfIds.value.has(record.id)) return
  const next = new Set(loadingPdfIds.value)
  next.add(record.id)
  loadingPdfIds.value = next
  try {
    const resp = await api.get(`/api/comprobantes-venta/${record.id}/pdf/`, {
      responseType: 'blob',
    })
    const blob = new Blob([resp.data], { type: 'application/pdf' })
    const url = URL.createObjectURL(blob)
    const win = window.open(url, '_blank')
    if (win) win.addEventListener('load', () => URL.revokeObjectURL(url), { once: true })
    else setTimeout(() => URL.revokeObjectURL(url), 10000)
  } catch {
    message.error('No se pudo generar el PDF')
  } finally {
    const s = new Set(loadingPdfIds.value)
    s.delete(record.id)
    loadingPdfIds.value = s
  }
}

// ── Email 1 click [E11] ────────────────────────────────────────────────────
const enviarEmail = async (record) => {
  if (loadingEmail.value) return
  loadingEmail.value = record.id
  try {
    await api.post(`/api/comprobantes-venta/${record.id}/enviar-email/`)
    message.success('Email enviado correctamente')
  } catch (e) {
    const msg = e?.response?.data?.error || e?.response?.data?.detail || 'Error enviando email'
    message.error(msg)
  } finally {
    loadingEmail.value = null
  }
}

// ── Export CSV [E7] ────────────────────────────────────────────────────────
const exportCsv = (soloSeleccionados = false) => {
  const data =
    soloSeleccionados && selectedRowKeys.value.length
      ? rows.value.filter((r) => selectedRowKeys.value.includes(r.id))
      : rows.value
  const headers = [
    'Comprobante',
    'Fecha',
    'Cliente',
    'CUIT',
    'Tipo',
    'Estado',
    'Cobro',
    'Total',
    'Saldo',
    'CAE',
    'Vto. CAE',
  ]
  const csvRows = data.map((r) => [
    r.numero_completo || '',
    fmtFecha(r.fecha),
    clienteNombre(r),
    clienteCuit(r),
    r.tipo_comprobante?.nombre || '',
    estadoConfig[r.estado]?.label || r.estado || '',
    cobroStatus(r).label,
    Number(r.total || 0)
      .toFixed(2)
      .replace('.', ','),
    Number(r.saldo_pendiente || 0)
      .toFixed(2)
      .replace('.', ','),
    r.cae || '',
    fmtFecha(r.vto_cae),
  ])
  const bom = '\uFEFF'
  const csv =
    bom +
    [headers, ...csvRows]
      .map((row) => row.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(';'))
      .join('\r\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `comprobantes_${dayjs().format('YYYYMMDD_HHmm')}.csv`
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
  message.success(
    `${data.length} comprobante${data.length !== 1 ? 's' : ''} exportado${data.length !== 1 ? 's' : ''}`,
  )
}

// ── Fetch ──────────────────────────────────────────────────────────────────
let searchTimer = null

const buildParams = () => {
  const p = { limit: pagination.pageSize, offset: (pagination.current - 1) * pagination.pageSize }
  if (filters.ordering) p.ordering = filters.ordering
  if (filters.search.trim()) p.search = filters.search.trim()
  if (filters.estado) p.estado = filters.estado
  if (filters.tipo_comprobante) p.tipo_comprobante = filters.tipo_comprobante
  if (filters.condicion_venta) p.condicion_venta = filters.condicion_venta
  if (filters.fecha_desde) p.fecha_desde = filters.fecha_desde.format('YYYY-MM-DD')
  if (filters.fecha_hasta) p.fecha_hasta = filters.fecha_hasta.format('YYYY-MM-DD')
  return p
}

const fetchData = async () => {
  loading.value = true
  try {
    const { data } = await api.get('/api/comprobantes-venta/', { params: buildParams() })
    rows.value = data?.results ?? data ?? []
    total.value = data?.count ?? (Array.isArray(data) ? data.length : 0)
  } catch (e) {
    console.error(e)
    message.error('Error cargando comprobantes')
  } finally {
    loading.value = false
  }
}

const fetchTiposComprobante = async () => {
  try {
    const { data } = await api.get('/api/tipos-comprobante/')
    const list = data?.results ?? data ?? []
    tiposComprobante.value = [
      { value: '', label: 'Todos los tipos' },
      ...list.map((t) => ({ value: t.id, label: t.nombre })),
    ]
  } catch {
    tiposComprobante.value = [{ value: '', label: 'Todos los tipos' }]
  }
}

// ── Event handlers ─────────────────────────────────────────────────────────
const onSearch = () => {
  pagination.current = 1
  fetchData()
}

const onSearchInput = () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(onSearch, 350)
}

const onFilterChange = () => {
  pagination.current = 1
  fetchData()
}

const onTableChange = (pag, _, sorter) => {
  pagination.current = pag.current || 1
  pagination.pageSize = pag.pageSize || 20
  if (sorter?.field)
    filters.ordering = sorter.order === 'descend' ? `-${sorter.field}` : sorter.field
  fetchData()
}

// [E2] Quick ranges
const applyQuickRange = (range) => {
  filters.fecha_desde = range.from()
  filters.fecha_hasta = range.to()
  onFilterChange()
}

const onReset = () => {
  filters.search = ''
  filters.estado = 'CN'
  filters.tipo_comprobante = ''
  filters.condicion_venta = ''
  filters.ordering = '-fecha'
  filters.fecha_desde = dayjs().startOf('month')
  filters.fecha_hasta = dayjs()
  pagination.current = 1
  selectedRowKeys.value = []
  fetchData()
}

watch(
  () => [
    filters.estado,
    filters.tipo_comprobante,
    filters.condicion_venta,
    filters.fecha_desde,
    filters.fecha_hasta,
  ],
  onFilterChange,
)

// ── Favoritos [E4] ─────────────────────────────────────────────────────────
const loadFavoritos = () => {
  try {
    favoritos.value = JSON.parse(localStorage.getItem(STORAGE_FAVS_KEY) || '[]')
  } catch {
    favoritos.value = []
  }
}

const saveFavorito = () => {
  const nombre = favNombreInput.value.trim()
  if (!nombre) {
    message.warning('Ingresá un nombre para el favorito')
    return
  }
  const fav = {
    id: Date.now(),
    nombre,
    filters: {
      search: filters.search,
      estado: filters.estado,
      tipo_comprobante: filters.tipo_comprobante,
      condicion_venta: filters.condicion_venta,
      fecha_desde: filters.fecha_desde?.toISOString() || null,
      fecha_hasta: filters.fecha_hasta?.toISOString() || null,
    },
  }
  favoritos.value = [...favoritos.value, fav]
  localStorage.setItem(STORAGE_FAVS_KEY, JSON.stringify(favoritos.value))
  favNombreInput.value = ''
  showFavPopover.value = false
  message.success(`Favorito "${nombre}" guardado`)
}

const applyFavorito = (fav) => {
  const f = fav.filters
  filters.search = f.search || ''
  filters.estado = f.estado || ''
  filters.tipo_comprobante = f.tipo_comprobante || ''
  filters.condicion_venta = f.condicion_venta || ''
  filters.fecha_desde = f.fecha_desde ? dayjs(f.fecha_desde) : null
  filters.fecha_hasta = f.fecha_hasta ? dayjs(f.fecha_hasta) : null
  onFilterChange()
}

const deleteFavorito = (id) => {
  favoritos.value = favoritos.value.filter((f) => f.id !== id)
  localStorage.setItem(STORAGE_FAVS_KEY, JSON.stringify(favoritos.value))
}

// ── Column config [E5] ─────────────────────────────────────────────────────
const FIXED_COLS = new Set(['numero_completo', 'actions'])

const loadColConfig = () => {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_COLS_KEY) || 'null')
    if (saved) visibleCols.value = new Set(saved)
  } catch {}
}

const toggleCol = (key) => {
  if (FIXED_COLS.has(key)) return
  const s = new Set(visibleCols.value)
  if (s.has(key)) s.delete(key)
  else s.add(key)
  visibleCols.value = s
  localStorage.setItem(STORAGE_COLS_KEY, JSON.stringify([...s]))
}

// ── Detail panel [E16] ─────────────────────────────────────────────────────
const openDetail = (r) => {
  detailRecord.value = r
  detailOpen.value = true
}
const closeDetail = () => {
  detailOpen.value = false
  detailRecord.value = null
}

// ── Bulk selection [E6] ────────────────────────────────────────────────────
const rowSelection = computed(() => ({
  selectedRowKeys: selectedRowKeys.value,
  onChange: (keys) => {
    selectedRowKeys.value = keys
  },
}))

// ── Keyboard shortcuts [E14] ───────────────────────────────────────────────
const handleKey = (e) => {
  if (e.key === 'F5') {
    e.preventDefault()
    fetchData()
  }
  if (e.key === 'Escape' && detailOpen.value) {
    closeDetail()
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 'e') {
    e.preventDefault()
    exportCsv()
  }
}

// ── Lifecycle ──────────────────────────────────────────────────────────────
onMounted(async () => {
  loadFavoritos()
  loadColConfig()
  await fetchTiposComprobante()
  await fetchData()
  window.addEventListener('keydown', handleKey)
})
onUnmounted(() => window.removeEventListener('keydown', handleKey))
</script>

<template>
  <div class="cc-root">
    <!-- ══════════ HEADER ══════════════════════════════════════════════════ -->
    <header class="cc-header">
      <div class="cc-header-left">
        <div class="cc-icon-wrap"><FileTextOutlined /></div>
        <div>
          <h1 class="cc-title">Comprobantes de venta</h1>
          <p class="cc-subtitle">
            {{ total.toLocaleString('es-AR') }} registros
            <span v-if="kpis.sinCae > 0" class="subtitle-alert">
              · <ExclamationCircleOutlined /> {{ kpis.sinCae }} sin CAE
            </span>
          </p>
        </div>
      </div>

      <div class="cc-header-actions">
        <!-- Favoritos -->
        <a-popover
          v-model:open="showFavPopover"
          trigger="click"
          placement="bottomRight"
          :overlayStyle="{ width: '290px' }"
        >
          <template #title
            ><div class="fav-pop-head">
              <StarFilled style="color: #f59e0b" /> Favoritos
            </div></template
          >
          <template #content>
            <div class="fav-pop-body">
              <div v-if="!favoritos.length" class="fav-empty">Sin favoritos guardados.</div>
              <div v-for="fav in favoritos" :key="fav.id" class="fav-item">
                <button class="fav-apply-btn" @click="applyFavorito(fav)" type="button">
                  <StarOutlined /> {{ fav.nombre }}
                </button>
                <button class="fav-del-btn" @click="deleteFavorito(fav.id)" type="button">×</button>
              </div>
              <div class="fav-save-row">
                <a-input
                  v-model:value="favNombreInput"
                  placeholder="Nombre del favorito…"
                  size="small"
                  @press-enter="saveFavorito"
                />
                <a-button type="primary" size="small" @click="saveFavorito"
                  ><CheckOutlined
                /></a-button>
              </div>
            </div>
          </template>
          <a-button class="hdr-btn" :class="{ 'hdr-btn--star': favoritos.length }">
            <StarOutlined />
            <span class="hdr-btn-txt">Favoritos</span>
            <span v-if="favoritos.length" class="hdr-badge">{{ favoritos.length }}</span>
          </a-button>
        </a-popover>

        <!-- Columnas -->
        <a-popover
          v-model:open="showColConfig"
          trigger="click"
          placement="bottomRight"
          :overlayStyle="{ width: '210px' }"
        >
          <template #title><SettingOutlined /> Columnas visibles</template>
          <template #content>
            <div class="col-config-list">
              <div v-for="col in ALL_COLUMNS" :key="col.key" class="col-config-item">
                <a-checkbox
                  :checked="visibleCols.has(col.key)"
                  :disabled="FIXED_COLS.has(col.key)"
                  @change="toggleCol(col.key)"
                  >{{ col.title || '(acciones)' }}</a-checkbox
                >
              </div>
            </div>
          </template>
          <a-button class="hdr-btn"
            ><SettingOutlined /><span class="hdr-btn-txt">Columnas</span></a-button
          >
        </a-popover>

        <!-- Exportar -->
        <a-dropdown>
          <a-button class="hdr-btn hdr-btn--export">
            <DownloadOutlined /><span class="hdr-btn-txt">Exportar</span>
          </a-button>
          <template #overlay>
            <a-menu>
              <a-menu-item @click="exportCsv(false)">
                <DownloadOutlined /> CSV — todos ({{ total }})
              </a-menu-item>
              <a-menu-item @click="exportCsv(true)" :disabled="!selectedRowKeys.length">
                <DownloadOutlined /> CSV — seleccionados ({{ selectedRowKeys.length }})
              </a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>

        <a-button class="hdr-btn" @click="fetchData" :loading="loading">
          <ReloadOutlined /><span class="hdr-btn-txt">F5</span>
        </a-button>
      </div>
    </header>

    <!-- ══════════ KPIs [E8] ═══════════════════════════════════════════════ -->
    <div class="cc-kpis">
      <div class="kpi-card kpi-card--accent">
        <span class="kpi-label">Total período</span>
        <span class="kpi-val">$ {{ moneyAR(kpis.totalSum) }}</span>
        <span class="kpi-sub">{{ rows.length }} de {{ total }} mostrados</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">Con CAE</span>
        <span class="kpi-val kpi-val--ok">{{ kpis.conCae }}</span>
        <span class="kpi-sub">comprobantes electrónicos</span>
      </div>
      <div class="kpi-card" :class="{ 'kpi-card--warn': kpis.sinCae > 0 }">
        <span class="kpi-label">Sin CAE</span>
        <span class="kpi-val" :class="kpis.sinCae > 0 ? 'kpi-val--warn' : 'kpi-val--ok'">{{
          kpis.sinCae
        }}</span>
        <span class="kpi-sub">requieren acción</span>
      </div>
      <div class="kpi-card" :class="{ 'kpi-card--alert': kpis.caePorVencer > 0 }">
        <span class="kpi-label">CAE por vencer</span>
        <span class="kpi-val" :class="kpis.caePorVencer > 0 ? 'kpi-val--alert' : 'kpi-val--ok'">{{
          kpis.caePorVencer
        }}</span>
        <span class="kpi-sub">vencen en ≤ 7 días</span>
      </div>
    </div>

    <!-- ══════════ FILTROS ═════════════════════════════════════════════════ -->
    <div class="cc-filter-bar">
      <a-input
        v-model:value="filters.search"
        placeholder="Número, cliente, CUIT, CAE…"
        allow-clear
        size="large"
        class="filter-search"
        @change="onSearchInput"
        @press-enter="onSearch"
        ><template #prefix><SearchOutlined /></template
      ></a-input>

      <!-- Quick ranges [E2] -->
      <div class="quick-ranges">
        <button
          v-for="r in QUICK_RANGES"
          :key="r.label"
          class="qr-btn"
          @click="applyQuickRange(r)"
          type="button"
        >
          {{ r.label }}
        </button>
      </div>

      <a-date-picker
        v-model:value="filters.fecha_desde"
        format="DD/MM/YYYY"
        size="large"
        placeholder="Desde"
        style="width: 136px"
      />
      <a-date-picker
        v-model:value="filters.fecha_hasta"
        format="DD/MM/YYYY"
        size="large"
        placeholder="Hasta"
        style="width: 136px"
      />
      <a-select
        v-model:value="filters.estado"
        :options="ESTADOS"
        size="large"
        style="width: 148px"
      />
      <a-select
        v-model:value="filters.tipo_comprobante"
        :options="tiposComprobante"
        size="large"
        style="width: 148px"
      />
      <a-select
        v-model:value="filters.condicion_venta"
        :options="CONDICIONES"
        size="large"
        style="width: 136px"
      />
      <a-button @click="onReset" size="large">Limpiar</a-button>
    </div>

    <!-- Chips de filtros activos [E3] -->
    <div v-if="filterChips.length > 0" class="cc-chips">
      <span class="chips-label"><FilterOutlined /> Filtros activos:</span>
      <div v-for="chip in filterChips" :key="chip.key" class="chip">
        {{ chip.label }}
        <button class="chip-x" @click="removeChip(chip.key)" type="button">×</button>
      </div>
      <button class="chips-clear" @click="onReset" type="button">Limpiar todo</button>
    </div>

    <!-- Batch bar [E6] -->
    <transition name="batch-slide">
      <div v-if="selectedRowKeys.length > 0" class="batch-bar">
        <span class="batch-count"
          ><CheckOutlined /> {{ selectedRowKeys.length }} seleccionado{{
            selectedRowKeys.length !== 1 ? 's' : ''
          }}</span
        >
        <div class="batch-actions">
          <a-button size="small" @click="exportCsv(true)"
            ><DownloadOutlined /> Exportar selección</a-button
          >
          <a-button size="small" @click="selectedRowKeys = []">Deseleccionar</a-button>
        </div>
      </div>
    </transition>

    <!-- ══════════ TABLA + DETALLE ═════════════════════════════════════════ -->
    <div class="cc-body" :class="{ 'cc-body--split': detailOpen }">
      <div class="cc-table-wrap">
        <a-table
          :columns="columns"
          :data-source="rows"
          :loading="loading"
          :row-selection="rowSelection"
          rowKey="id"
          size="middle"
          :scroll="{ x: 980 }"
          :pagination="{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total,
            showSizeChanger: true,
            pageSizeOptions: PAGE_SIZE_OPTIONS,
            showTotal: (t) => `${t.toLocaleString('es-AR')} comprobante${t !== 1 ? 's' : ''}`,
          }"
          @change="onTableChange"
          :customRow="
            (record) => ({
              onClick: () => openDetail(record),
              class: [
                detailRecord?.id === record.id ? 'row-active' : '',
                record.estado === 'AN' ? 'row-anulado' : '',
              ].join(' '),
            })
          "
          class="cc-table"
        >
          <template #emptyText>
            <div class="cc-empty">
              <FileTextOutlined class="cc-empty-icon" />
              <p>Sin comprobantes con los filtros aplicados.</p>
            </div>
          </template>

          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'numero_completo'">
              <span class="numero-badge">{{ record.numero_completo || '—' }}</span>
            </template>

            <template v-else-if="column.key === 'fecha'">
              <span class="cell-fecha">{{ fmtFecha(record.fecha) }}</span>
            </template>

            <template v-else-if="column.key === 'cliente'">
              <div class="cell-cliente">
                <span class="cliente-nombre">{{ clienteNombre(record) }}</span>
                <span class="cliente-cuit">{{ clienteCuit(record) }}</span>
              </div>
            </template>

            <template v-else-if="column.key === 'tipo'">
              <span class="tipo-chip">{{ record.tipo_comprobante?.nombre || '—' }}</span>
            </template>

            <template v-else-if="column.key === 'estado'">
              <a-tag :color="estadoConfig[record.estado]?.color || 'default'" class="estado-tag">
                {{ estadoConfig[record.estado]?.label || record.estado }}
              </a-tag>
            </template>

            <template v-else-if="column.key === 'cobro'">
              <span class="cobro-badge" :class="cobroStatus(record).cls">
                {{ cobroStatus(record).label }}
              </span>
            </template>

            <template v-else-if="column.key === 'condicion_venta'">
              <span
                class="cond-badge"
                :class="record.condicion_venta === 'CC' ? 'cond-badge--cc' : 'cond-badge--co'"
              >
                {{ condicionLabel[record.condicion_venta] || record.condicion_venta }}
              </span>
            </template>

            <template v-else-if="column.key === 'total'">
              <span class="cell-total">$ {{ moneyAR(record.total) }}</span>
            </template>

            <template v-else-if="column.key === 'cae'">
              <a-tooltip
                v-if="record.cae"
                :title="`CAE: ${record.cae} | Vto: ${fmtFecha(record.vto_cae)}`"
              >
                <span class="cae-badge" :class="caeVencimiento(record)?.cls || 'cae-ok'">
                  <span class="cae-dot" />
                  {{
                    caeVencimiento(record)?.dias != null ? `${caeVencimiento(record).dias}d` : 'OK'
                  }}
                </span>
              </a-tooltip>
              <a-tooltip v-else-if="record.afip_error" :title="record.afip_error">
                <span class="cae-badge cae-error"><WarningOutlined /> Error</span>
              </a-tooltip>
              <span v-else class="cae-badge cae-none">—</span>
            </template>

            <template v-else-if="column.key === 'actions'">
              <div class="cell-actions" @click.stop>
                <a-tooltip title="Ver detalle">
                  <a-button type="text" size="small" class="act-btn" @click="openDetail(record)">
                    <EyeOutlined />
                  </a-button>
                </a-tooltip>
                <a-tooltip title="Ver PDF">
                  <a-button
                    type="text"
                    size="small"
                    class="act-btn act-pdf"
                    :loading="loadingPdfIds.has(record.id)"
                    @click="openPdf(record)"
                  >
                    <FilePdfOutlined />
                  </a-button>
                </a-tooltip>
                <a-tooltip title="Enviar por email">
                  <a-button
                    type="text"
                    size="small"
                    class="act-btn act-mail"
                    :loading="loadingEmail === record.id"
                    @click="enviarEmail(record)"
                  >
                    <MailOutlined />
                  </a-button>
                </a-tooltip>
              </div>
            </template>
          </template>

          <!-- Totales de página [E13] -->
          <template #summary>
            <a-table-summary fixed>
              <a-table-summary-row class="summary-row">
                <a-table-summary-cell :index="0" :col-span="3" />
                <a-table-summary-cell :index="3" :col-span="columns.length - 5">
                  <span class="summary-label">Total página · {{ rows.length }} comprobantes</span>
                </a-table-summary-cell>
                <a-table-summary-cell :index="columns.length - 2" align="right">
                  <span class="summary-total">$ {{ moneyAR(kpis.totalSum) }}</span>
                </a-table-summary-cell>
                <a-table-summary-cell :index="columns.length - 1" />
              </a-table-summary-row>
            </a-table-summary>
          </template>
        </a-table>
      </div>

      <!-- ══════════ PANEL DETALLE [E16] ════════════════════════════════ -->
      <transition name="detail-slide">
        <aside v-if="detailOpen && detailRecord" class="cc-detail">
          <div class="detail-hdr">
            <div class="detail-hdr-left">
              <span class="detail-numero">{{ detailRecord.numero_completo }}</span>
              <a-tag :color="estadoConfig[detailRecord.estado]?.color" class="detail-estado-tag">
                {{ estadoConfig[detailRecord.estado]?.label }}
              </a-tag>
            </div>
            <button class="detail-close" @click="closeDetail" type="button">
              <CloseOutlined />
            </button>
          </div>

          <div class="detail-pills">
            <div class="pill">
              <CalendarOutlined class="pill-ic" /><span>{{
                fmtFechaHora(detailRecord.fecha)
              }}</span>
            </div>
            <div class="pill">
              <TagOutlined class="pill-ic" /><span>{{
                detailRecord.tipo_comprobante?.nombre || '—'
              }}</span>
            </div>
            <div
              class="pill"
              :class="detailRecord.condicion_venta === 'CC' ? 'pill--cc' : 'pill--co'"
            >
              <DollarOutlined class="pill-ic" /><span>{{
                condicionLabel[detailRecord.condicion_venta] || '—'
              }}</span>
            </div>
            <div
              class="pill cobro-pill"
              :class="cobroStatus(detailRecord).cls.replace('cobro', 'cobro')"
            >
              {{ cobroStatus(detailRecord).label }}
            </div>
          </div>

          <div class="detail-sec">
            <div class="detail-sec-title"><UserOutlined /> Cliente</div>
            <div class="kv">
              <span class="kv-k">Razón Social</span
              ><span class="kv-v">{{ clienteNombre(detailRecord) }}</span>
            </div>
            <div class="kv">
              <span class="kv-k">CUIT / DNI</span
              ><span class="kv-v kv-mono">{{ clienteCuit(detailRecord) }}</span>
            </div>
            <div v-if="detailRecord.cliente_email_override" class="kv">
              <span class="kv-k">Email</span
              ><span class="kv-v">{{ detailRecord.cliente_email_override }}</span>
            </div>
          </div>

          <div class="detail-sec">
            <div class="detail-sec-title">
              <TagOutlined /> Artículos ({{ detailRecord.items?.length || 0 }})
            </div>
            <div class="detail-items">
              <div
                v-for="item in detailRecord.items"
                :key="item.articulo?.cod_articulo"
                class="detail-item"
              >
                <div class="item-l">
                  <span class="item-cod">{{ item.articulo?.cod_articulo }}</span>
                  <span class="item-desc">{{ item.articulo?.descripcion }}</span>
                </div>
                <div class="item-r">
                  <span class="item-qty">{{ item.cantidad }} u.</span>
                  <span class="item-sub">$ {{ moneyAR(item.subtotal) }}</span>
                </div>
              </div>
            </div>
          </div>

          <div class="detail-sec">
            <div class="detail-sec-title"><DollarOutlined /> Importes</div>
            <div class="kv">
              <span class="kv-k">Subtotal neto</span
              ><span class="kv-v kv-num">$ {{ moneyAR(detailRecord.subtotal) }}</span>
            </div>
            <div class="kv kv--total">
              <span class="kv-k">Total</span>
              <span class="kv-v kv-total-v">$ {{ moneyAR(detailRecord.total) }}</span>
            </div>
            <div v-if="Number(detailRecord.saldo_pendiente) > 0" class="kv kv--saldo">
              <span class="kv-k">Saldo pendiente</span>
              <span class="kv-v kv-saldo-v">$ {{ moneyAR(detailRecord.saldo_pendiente) }}</span>
            </div>
          </div>

          <div class="detail-sec">
            <div class="detail-sec-title">AFIP / CAE</div>
            <div v-if="detailRecord.cae" class="afip-ok">
              <CheckCircleOutlined class="afip-ok-ic" />
              <div>
                <div class="afip-cae-lbl">CAE</div>
                <div class="afip-cae-val">{{ detailRecord.cae }}</div>
                <div class="afip-vto" :class="caeVencimiento(detailRecord)?.cls">
                  Vence: {{ fmtFecha(detailRecord.vto_cae) }}
                  <span v-if="caeVencimiento(detailRecord)">
                    — {{ caeVencimiento(detailRecord).label }}</span
                  >
                </div>
              </div>
            </div>
            <div v-else-if="detailRecord.afip_error" class="afip-err">
              <WarningOutlined class="afip-err-ic" />
              <p class="afip-err-msg">{{ detailRecord.afip_error }}</p>
            </div>
            <div v-else class="afip-none">Sin datos AFIP</div>
          </div>

          <div v-if="detailRecord.observaciones" class="detail-sec">
            <div class="detail-sec-title">Observaciones</div>
            <p class="detail-obs">{{ detailRecord.observaciones }}</p>
          </div>

          <div class="detail-footer">
            <a-button
              type="primary"
              block
              size="large"
              :loading="loadingPdfIds.has(detailRecord.id)"
              @click="openPdf(detailRecord)"
              class="detail-pdf-btn"
            >
              <FilePdfOutlined /> Ver / Descargar PDF
            </a-button>
            <a-button
              block
              :loading="loadingEmail === detailRecord.id"
              @click="enviarEmail(detailRecord)"
            >
              <MailOutlined /> Enviar por email
            </a-button>
          </div>
        </aside>
      </transition>
    </div>

    <!-- Shortcuts hint [E14] -->
    <div class="cc-hint">
      <ThunderboltOutlined />
      <kbd>F5</kbd> actualizar · <kbd>Ctrl+E</kbd> exportar CSV · <kbd>Esc</kbd> cerrar detalle
    </div>
  </div>
</template>

<style scoped>
/* ── Root ──────────────────────────────────────────────────────────────────── */
.cc-root {
  --acc: 99, 102, 241;
  --r: 8px;
  --r-sm: 5px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 20px 24px 32px;
  min-height: 100%;
}

/* ── Header ────────────────────────────────────────────────────────────────── */
.cc-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.cc-header-left {
  display: flex;
  align-items: center;
  gap: 14px;
}
.cc-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.cc-icon-wrap {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: rgba(var(--acc), 0.1);
  border: 1px solid rgba(var(--acc), 0.2);
  display: grid;
  place-items: center;
  font-size: 20px;
  color: rgba(var(--acc), 1);
  flex-shrink: 0;
}
.cc-title {
  font-size: 1.3rem;
  font-weight: 900;
  color: var(--text-0);
  margin: 0;
  letter-spacing: -0.3px;
}
.cc-subtitle {
  font-size: 12px;
  color: var(--text-2);
  margin: 0;
}
.subtitle-alert {
  color: #f59e0b;
  font-weight: 700;
}

.hdr-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  position: relative;
}
.hdr-btn--star {
  border-color: #f59e0b !important;
  color: #d97706 !important;
}
.hdr-btn--export {
  border-color: rgba(var(--acc), 0.3);
  color: rgba(var(--acc), 1);
}
.hdr-btn-txt {
  display: none;
}
.hdr-badge {
  position: absolute;
  top: -6px;
  right: -6px;
  min-width: 16px;
  height: 16px;
  padding: 0 3px;
  border-radius: 8px;
  background: #f59e0b;
  color: #fff;
  font-size: 9px;
  font-weight: 900;
  display: grid;
  place-items: center;
}
@media (min-width: 1100px) {
  .hdr-btn-txt {
    display: inline;
  }
}

/* ── KPIs ──────────────────────────────────────────────────────────────────── */
.cc-kpis {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.kpi-card {
  padding: 12px 16px;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--r);
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.kpi-card--accent {
  border-color: rgba(var(--acc), 0.2);
  background: rgba(var(--acc), 0.03);
}
.kpi-card--warn {
  border-color: rgba(245, 158, 11, 0.4);
  background: rgba(245, 158, 11, 0.04);
}
.kpi-card--alert {
  border-color: rgba(239, 68, 68, 0.35);
  background: rgba(239, 68, 68, 0.04);
}
.kpi-label {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-2);
}
.kpi-val {
  font-size: 1.55rem;
  font-weight: 900;
  font-variant-numeric: tabular-nums;
  color: var(--text-0);
  line-height: 1.1;
}
.kpi-val--ok {
  color: #10b981;
}
.kpi-val--warn {
  color: #f59e0b;
}
.kpi-val--alert {
  color: #ef4444;
}
.kpi-sub {
  font-size: 11px;
  color: var(--text-2);
}

/* ── Filter bar ────────────────────────────────────────────────────────────── */
.cc-filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 12px 14px;
  background: rgba(148, 163, 184, 0.04);
  border: 1px solid var(--border);
  border-radius: var(--r);
}
.filter-search {
  flex: 1;
  min-width: 180px;
}

.quick-ranges {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.qr-btn {
  padding: 3px 10px;
  border-radius: 5px;
  border: 1px solid var(--border);
  background: rgba(148, 163, 184, 0.07);
  font-size: 12px;
  font-weight: 700;
  color: var(--text-2);
  cursor: pointer;
  transition: all 0.12s;
  font-family: inherit;
}
.qr-btn:hover {
  border-color: rgba(var(--acc), 0.4);
  background: rgba(var(--acc), 0.07);
  color: rgba(var(--acc), 1);
}

/* ── Filter chips ──────────────────────────────────────────────────────────── */
.cc-chips {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
  padding: 4px 2px;
}
.chips-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-2);
  white-space: nowrap;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 8px;
  border-radius: 5px;
  background: rgba(var(--acc), 0.09);
  border: 1px solid rgba(var(--acc), 0.22);
  color: rgba(var(--acc), 1);
  font-size: 12px;
  font-weight: 700;
}
.chip-x {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  color: inherit;
  opacity: 0.7;
  padding: 0 2px;
  font-family: inherit;
}
.chip-x:hover {
  opacity: 1;
}
.chips-clear {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-2);
  background: none;
  border: none;
  cursor: pointer;
  text-decoration: underline;
  font-family: inherit;
}
.chips-clear:hover {
  color: #ef4444;
}

/* ── Batch bar ─────────────────────────────────────────────────────────────── */
.batch-slide-enter-active,
.batch-slide-leave-active {
  transition: all 0.2s ease;
}
.batch-slide-enter-from,
.batch-slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
.batch-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 14px;
  background: rgba(var(--acc), 0.07);
  border: 1px solid rgba(var(--acc), 0.22);
  border-radius: var(--r);
}
.batch-count {
  font-size: 13px;
  font-weight: 700;
  color: rgba(var(--acc), 1);
}
.batch-actions {
  display: flex;
  gap: 8px;
}

/* ── Body ──────────────────────────────────────────────────────────────────── */
.cc-body {
  display: grid;
  grid-template-columns: 1fr;
  gap: 14px;
  transition: grid-template-columns 0.28s ease;
  flex: 1;
}
.cc-body--split {
  grid-template-columns: 1fr 360px;
}

.cc-table-wrap {
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--r);
  overflow: hidden;
}

:global(.cc-table .ant-table-thead th) {
  font-size: 11px !important;
  font-weight: 800 !important;
  letter-spacing: 0.06em !important;
  text-transform: uppercase !important;
  color: var(--text-2) !important;
  background: rgba(148, 163, 184, 0.05) !important;
}
:global(.cc-table .ant-table-tbody tr) {
  cursor: pointer;
  transition: background 0.1s;
}
:global(.row-active td) {
  background: rgba(var(--acc), 0.06) !important;
  box-shadow: inset 3px 0 0 rgba(var(--acc), 0.7) !important;
}
:global(.row-anulado td) {
  opacity: 0.5;
}

.summary-row {
  background: rgba(148, 163, 184, 0.05);
}
.summary-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-2);
}
.summary-total {
  font-size: 14px;
  font-weight: 900;
  color: rgba(var(--acc), 1);
  font-variant-numeric: tabular-nums;
}

/* Cells */
.numero-badge {
  font-family: ui-monospace, monospace;
  font-size: 12px;
  font-weight: 800;
  color: var(--text-0);
  background: rgba(148, 163, 184, 0.08);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px 7px;
  letter-spacing: 0.04em;
}
.cell-fecha {
  font-size: 12.5px;
  font-variant-numeric: tabular-nums;
  color: var(--text-1);
}
.cell-cliente {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.cliente-nombre {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-0);
}
.cliente-cuit {
  font-size: 11px;
  font-family: ui-monospace, monospace;
  color: var(--text-2);
}
.tipo-chip {
  display: inline-flex;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  background: rgba(148, 163, 184, 0.1);
  border: 1px solid var(--border);
  color: var(--text-1);
}
.estado-tag {
  font-weight: 700;
  font-size: 11px;
}

.cobro-badge {
  display: inline-flex;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  border: 1px solid transparent;
}
.cobro--ok {
  background: rgba(16, 185, 129, 0.09);
  border-color: rgba(16, 185, 129, 0.22);
  color: #059669;
}
.cobro--parcial {
  background: rgba(245, 158, 11, 0.09);
  border-color: rgba(245, 158, 11, 0.22);
  color: #d97706;
}
.cobro--pendiente {
  background: rgba(148, 163, 184, 0.09);
  border-color: var(--border);
  color: var(--text-2);
}
.cobro--anulado {
  background: rgba(239, 68, 68, 0.07);
  border-color: rgba(239, 68, 68, 0.18);
  color: #dc2626;
}
.cobro--borrador {
  background: rgba(245, 158, 11, 0.07);
  border-color: rgba(245, 158, 11, 0.18);
  color: #d97706;
}

.cond-badge {
  display: inline-flex;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  border: 1px solid transparent;
}
.cond-badge--co {
  background: rgba(16, 185, 129, 0.08);
  border-color: rgba(16, 185, 129, 0.2);
  color: #059669;
}
.cond-badge--cc {
  background: rgba(var(--acc), 0.08);
  border-color: rgba(var(--acc), 0.2);
  color: rgba(var(--acc), 1);
}

.cell-total {
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  color: var(--text-0);
}

.cae-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 800;
  border: 1px solid transparent;
}
.cae-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}
.cae-ok {
  background: rgba(16, 185, 129, 0.1);
  border-color: rgba(16, 185, 129, 0.2);
  color: #059669;
}
.cae-alerta {
  background: rgba(245, 158, 11, 0.1);
  border-color: rgba(245, 158, 11, 0.25);
  color: #d97706;
}
.cae-critico {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.25);
  color: #dc2626;
}
.cae-vencido {
  background: rgba(239, 68, 68, 0.15);
  border-color: rgba(239, 68, 68, 0.3);
  color: #b91c1c;
}
.cae-error {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.25);
  color: #dc2626;
}
.cae-none {
  color: var(--text-2);
  font-weight: 400;
}

.cell-actions {
  display: flex;
  gap: 2px;
  justify-content: center;
}
.act-btn {
  opacity: 0.45;
  transition: opacity 0.12s;
}
.act-btn:hover {
  opacity: 1;
}
.act-pdf:hover {
  color: #dc2626 !important;
}
.act-mail:hover {
  color: #2563eb !important;
}

.cc-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 48px 20px;
  color: var(--text-2);
}
.cc-empty-icon {
  font-size: 40px;
  opacity: 0.12;
}
.cc-empty p {
  font-size: 13px;
  margin: 0;
}

/* ── Detail panel ──────────────────────────────────────────────────────────── */
.detail-slide-enter-active,
.detail-slide-leave-active {
  transition: all 0.25s ease;
}
.detail-slide-enter-from,
.detail-slide-leave-to {
  opacity: 0;
  transform: translateX(20px);
}

.cc-detail {
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-top: 2px solid rgba(var(--acc), 0.5);
  border-radius: var(--r);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  max-height: calc(100vh - 200px);
  position: sticky;
  top: 16px;
}

.detail-hdr {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: rgba(148, 163, 184, 0.04);
  flex-shrink: 0;
}
.detail-hdr-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.detail-numero {
  font-family: ui-monospace, monospace;
  font-size: 14px;
  font-weight: 900;
  color: var(--text-0);
  letter-spacing: 0.04em;
}
.detail-estado-tag {
  font-weight: 700;
}
.detail-close {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 5px;
  border: 1px solid var(--border);
  background: transparent;
  font-size: 12px;
  cursor: pointer;
  color: var(--text-2);
  transition: all 0.12s;
}
.detail-close:hover {
  background: rgba(239, 68, 68, 0.07);
  border-color: rgba(239, 68, 68, 0.2);
  color: #dc2626;
}

.detail-pills {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px;
  border-radius: 5px;
  font-size: 11.5px;
  font-weight: 600;
  background: rgba(148, 163, 184, 0.08);
  border: 1px solid var(--border);
  color: var(--text-1);
}
.pill-ic {
  font-size: 11px;
  color: var(--text-2);
}
.pill--co {
  background: rgba(16, 185, 129, 0.07);
  border-color: rgba(16, 185, 129, 0.18);
  color: #059669;
}
.pill--cc {
  background: rgba(var(--acc), 0.07);
  border-color: rgba(var(--acc), 0.18);
  color: rgba(var(--acc), 1);
}

.detail-sec {
  padding: 12px 16px;
  border-bottom: 1px dashed var(--border);
}
.detail-sec:last-of-type {
  border-bottom: none;
}
.detail-sec-title {
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--text-2);
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 5px;
}

.kv {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 12.5px;
}
.kv-k {
  color: var(--text-2);
  font-weight: 500;
}
.kv-v {
  color: var(--text-0);
  font-weight: 600;
  text-align: right;
}
.kv-mono {
  font-family: ui-monospace, monospace;
  font-size: 11.5px;
}
.kv-num {
  font-variant-numeric: tabular-nums;
}
.kv--total {
  margin-top: 4px;
  padding: 6px 10px;
  background: rgba(var(--acc), 0.05);
  border-radius: var(--r-sm);
  border: 1px solid rgba(var(--acc), 0.15);
}
.kv-total-v {
  font-size: 1.1rem;
  font-weight: 900;
  font-variant-numeric: tabular-nums;
  color: rgba(var(--acc), 1);
}
.kv--saldo .kv-saldo-v {
  color: #ef4444;
  font-weight: 800;
}

.detail-items {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.detail-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: var(--r-sm);
  background: rgba(148, 163, 184, 0.04);
  border: 1px solid var(--border);
}
.item-l {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.item-cod {
  font-size: 10px;
  font-family: ui-monospace, monospace;
  font-weight: 700;
  color: var(--text-2);
  letter-spacing: 0.04em;
}
.item-desc {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-0);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.item-r {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 1px;
  flex-shrink: 0;
}
.item-qty {
  font-size: 10.5px;
  color: var(--text-2);
}
.item-sub {
  font-size: 12px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--text-0);
}

.afip-ok {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 10px;
  background: rgba(16, 185, 129, 0.06);
  border: 1px solid rgba(16, 185, 129, 0.18);
  border-radius: var(--r-sm);
}
.afip-ok-ic {
  font-size: 18px;
  color: #10b981;
  margin-top: 2px;
  flex-shrink: 0;
}
.afip-cae-lbl {
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #10b981;
}
.afip-cae-val {
  font-family: ui-monospace, monospace;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-0);
  word-break: break-all;
}
.afip-vto {
  font-size: 10.5px;
  color: var(--text-2);
  margin-top: 2px;
}
.afip-vto.cae-alerta {
  color: #d97706;
  font-weight: 700;
}
.afip-vto.cae-critico {
  color: #dc2626;
  font-weight: 700;
}
.afip-vto.cae-vencido {
  color: #b91c1c;
  font-weight: 700;
}

.afip-err {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 10px;
  background: rgba(239, 68, 68, 0.06);
  border: 1px solid rgba(239, 68, 68, 0.18);
  border-radius: var(--r-sm);
}
.afip-err-ic {
  font-size: 18px;
  color: #ef4444;
  flex-shrink: 0;
  margin-top: 2px;
}
.afip-err-msg {
  font-size: 11.5px;
  color: #dc2626;
  margin: 0;
  line-height: 1.4;
}
.afip-none {
  font-size: 12px;
  color: var(--text-2);
  font-style: italic;
}
.detail-obs {
  font-size: 12.5px;
  color: var(--text-1);
  margin: 0;
  line-height: 1.5;
}

.detail-footer {
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  background: rgba(148, 163, 184, 0.03);
  flex-shrink: 0;
  position: sticky;
  bottom: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.detail-pdf-btn {
  font-weight: 700;
}

/* ── Favoritos ─────────────────────────────────────────────────────────────── */
.fav-pop-head {
  display: flex;
  align-items: center;
  gap: 7px;
  font-weight: 800;
}
.fav-pop-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.fav-empty {
  font-size: 12px;
  color: var(--text-2);
  font-style: italic;
}
.fav-item {
  display: flex;
  align-items: center;
  gap: 6px;
}
.fav-apply-btn {
  flex: 1;
  text-align: left;
  background: rgba(148, 163, 184, 0.07);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 5px 10px;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--text-0);
  transition: background 0.12s;
}
.fav-apply-btn:hover {
  background: rgba(var(--acc), 0.08);
  border-color: rgba(var(--acc), 0.25);
}
.fav-del-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 16px;
  color: var(--text-2);
  padding: 0 4px;
  font-family: inherit;
}
.fav-del-btn:hover {
  color: #ef4444;
}
.fav-save-row {
  display: flex;
  gap: 6px;
  margin-top: 4px;
  border-top: 1px solid var(--border);
  padding-top: 8px;
}

/* ── Column config ─────────────────────────────────────────────────────────── */
.col-config-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.col-config-item {
  font-size: 13px;
}

/* ── Shortcuts hint ────────────────────────────────────────────────────────── */
.cc-hint {
  font-size: 11px;
  color: var(--text-2);
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 2px;
}
.cc-hint kbd {
  display: inline-flex;
  padding: 1px 5px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: rgba(148, 163, 184, 0.08);
  font-size: 10px;
  font-weight: 700;
  font-family: ui-monospace, monospace;
  color: var(--text-1);
}

/* ── Responsive ────────────────────────────────────────────────────────────── */
@media (max-width: 1280px) {
  .cc-kpis {
    grid-template-columns: repeat(2, 1fr);
  }
  .cc-body--split {
    grid-template-columns: 1fr 320px;
  }
}
@media (max-width: 1024px) {
  .filter-search {
    flex: 1 1 100%;
  }
}
@media (max-width: 900px) {
  .cc-root {
    padding: 12px 14px;
  }
  .cc-kpis {
    grid-template-columns: repeat(2, 1fr);
  }
  .cc-body--split {
    grid-template-columns: 1fr;
  }
  .cc-detail {
    max-height: 60vh;
    position: static;
  }
}
@media (max-width: 600px) {
  .cc-kpis {
    grid-template-columns: 1fr 1fr;
  }
  .cc-hint {
    display: none;
  }
}
</style>
