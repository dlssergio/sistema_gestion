<template>
  <div class="dash">
    <!-- ── Error banner ─────────────────────────────────────────────────── -->
    <transition name="fade-slide">
      <div v-if="hasError && !loading" class="error-banner" role="alert">
        <svg class="error-icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path
            fill-rule="evenodd"
            d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z"
            clip-rule="evenodd"
          />
        </svg>
        <span>No se pudieron cargar algunas métricas.</span>
        <button class="retry-btn" @click="loadData" :disabled="loading">Reintentar</button>
      </div>
    </transition>

    <!-- ── KPIs ──────────────────────────────────────────────────────────── -->
    <div class="kpis">
      <div
        v-for="kpi in kpiCards"
        :key="kpi.id"
        class="kpi-card"
        :class="{ 'kpi-card--featured': kpi.featured }"
      >
        <div class="kpi-header">
          <span class="kpi-label">{{ kpi.label }}</span>
          <span v-if="!loading" class="kpi-pill" :class="kpi.pillKind">{{ kpi.pill }}</span>
          <span v-else class="skeleton skeleton--pill"></span>
        </div>
        <div v-if="!loading" class="kpi-value">{{ kpi.value }}</div>
        <div v-else class="skeleton skeleton--value"></div>
        <div class="kpi-footer">
          <span v-if="!loading" class="kpi-sub">{{ kpi.sub }}</span>
          <span v-else class="skeleton skeleton--sub"></span>
          <span
            v-if="!loading && kpi.trend !== undefined"
            class="kpi-trend"
            :class="kpi.trend >= 0 ? 'up' : 'down'"
          >
            <svg viewBox="0 0 10 10" aria-hidden="true">
              <path :d="kpi.trend >= 0 ? 'M5 2l4 6H1z' : 'M5 8L1 2h8z'" />
            </svg>
          </span>
        </div>
      </div>
    </div>

    <!-- ── Grid ─────────────────────────────────────────────────────────── -->
    <div class="grid">
      <!-- Chart ─────────────────────────────────────────────────────────── -->
      <AppCard class="chart-card">
        <template #header>
          <div class="card-head">
            <div class="card-head-left">
              <span class="card-title">Actividad de ventas</span>
              <span class="card-sub">Últimos {{ chartDays }} períodos registrados</span>
            </div>
            <div class="legend">
              <span class="legend-dot"></span>
              <span class="legend-label">Facturación</span>
            </div>
          </div>
        </template>

        <div class="chart-wrap">
          <div v-if="loading" class="skeleton skeleton--chart"></div>
          <template v-else>
            <svg
              :viewBox="`0 0 ${CW} ${CH}`"
              class="chart-svg"
              aria-hidden="true"
              @mousemove="onChartHover"
              @mouseleave="chartHoverX = null"
            >
              <defs>
                <linearGradient :id="gradAreaId" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="var(--chart-area-top)" />
                  <stop offset="100%" stop-color="var(--chart-area-bottom)" />
                </linearGradient>
                <linearGradient :id="gradShimmerId" x1="-40%" y1="0%" x2="0%" y2="0%">
                  <stop offset="0%" stop-color="var(--chart-shimmer-0)" />
                  <stop offset="55%" stop-color="var(--chart-shimmer-1)" />
                  <stop offset="100%" stop-color="var(--chart-shimmer-2)" />
                  <animate
                    attributeName="x1"
                    from="-40%"
                    to="60%"
                    dur="6s"
                    repeatCount="indefinite"
                  />
                  <animate
                    attributeName="x2"
                    from="0%"
                    to="100%"
                    dur="6s"
                    repeatCount="indefinite"
                  />
                </linearGradient>
                <filter :id="`glow-${_uid}`" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur in="SourceGraphic" stdDeviation="3" result="blur" />
                  <feColorMatrix
                    in="blur"
                    type="matrix"
                    values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 0.6 0"
                    result="glow"
                  />
                  <feMerge>
                    <feMergeNode in="glow" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>

              <!-- Grid lines -->
              <g class="chart-grid">
                <line v-for="y in GRID_Y" :key="y" x1="0" :y1="y" :x2="CW" :y2="y" />
              </g>

              <!-- Area fill -->
              <path
                :d="chartPaths.area"
                class="chart-area"
                :style="{ fill: `url(#${gradAreaId})` }"
              />

              <!-- Base stroke (shadow) -->
              <path :d="chartPaths.line" class="chart-line-base" />

              <!-- Main line -->
              <path
                :d="chartPaths.line"
                class="chart-line"
                :style="{ filter: `url(#glow-${_uid})` }"
              />

              <!-- Shimmer overlay -->
              <path :d="chartPaths.line" class="chart-shimmer" :stroke="`url(#${gradShimmerId})`" />

              <!-- Data points -->
              <circle
                v-for="(pt, i) in chartPaths.points"
                :key="i"
                :cx="pt.x"
                :cy="pt.y"
                r="4"
                class="chart-dot"
              />

              <!-- Hover crosshair -->
              <line
                v-if="chartHoverX !== null"
                :x1="chartHoverX"
                y1="0"
                :x2="chartHoverX"
                :y2="CH"
                class="chart-crosshair"
              />
            </svg>

            <div v-if="series.labels.length" class="chart-labels">
              <span v-for="(l, i) in series.labels" :key="i">{{ l }}</span>
            </div>
          </template>
        </div>
      </AppCard>

      <!-- Alerts ──────────────────────────────────────────────────────────── -->
      <AppCard class="alerts-card">
        <template #header>
          <div class="card-head">
            <div class="card-head-left">
              <span class="card-title">Alertas</span>
              <span class="card-sub">Requieren atención</span>
            </div>
            <span class="alert-count-badge" v-if="!loading && alerts.length > 0">{{
              alerts.length
            }}</span>
          </div>
        </template>

        <div class="alerts">
          <template v-if="loading">
            <div v-for="n in 3" :key="n" class="skeleton skeleton--alert"></div>
          </template>
          <template v-else>
            <div v-if="alerts.length === 0" class="alert-item alert-item--ok">
              <div class="alert-icon">
                <svg viewBox="0 0 20 20" fill="currentColor">
                  <path
                    fill-rule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z"
                    clip-rule="evenodd"
                  />
                </svg>
              </div>
              <div class="alert-body">
                <div class="alert-title">Sin alertas</div>
                <div class="alert-sub">Todo en orden</div>
              </div>
            </div>
            <div
              v-for="(a, idx) in alerts"
              :key="idx"
              class="alert-item"
              :class="`alert-item--${a.kind}`"
            >
              <div class="alert-icon">
                <!-- warn -->
                <svg v-if="a.kind === 'warn'" viewBox="0 0 20 20" fill="currentColor">
                  <path
                    fill-rule="evenodd"
                    d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z"
                    clip-rule="evenodd"
                  />
                </svg>
                <!-- ok -->
                <svg v-else-if="a.kind === 'ok'" viewBox="0 0 20 20" fill="currentColor">
                  <path
                    fill-rule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z"
                    clip-rule="evenodd"
                  />
                </svg>
                <!-- neutral -->
                <svg v-else viewBox="0 0 20 20" fill="currentColor">
                  <path
                    fill-rule="evenodd"
                    d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z"
                    clip-rule="evenodd"
                  />
                </svg>
              </div>
              <div class="alert-body">
                <div class="alert-title">{{ a.title }}</div>
                <div class="alert-sub">{{ a.subtitle }}</div>
              </div>
            </div>
          </template>
        </div>
      </AppCard>

      <!-- Latest sales ─────────────────────────────────────────────────────── -->
      <AppCard class="span-full movements-card">
        <template #header>
          <div class="card-head">
            <div class="card-head-left">
              <span class="card-title">Últimos movimientos</span>
              <span class="card-sub">Facturas y comprobantes recientes</span>
            </div>
            <button
              class="refresh-btn"
              @click="loadData"
              :disabled="loading"
              :title="loading ? 'Cargando…' : 'Actualizar'"
              :aria-label="loading ? 'Cargando' : 'Actualizar'"
            >
              <svg
                class="refresh-icon"
                :class="{ spinning: loading }"
                viewBox="0 0 20 20"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99"
                />
              </svg>
            </button>
          </div>
        </template>

        <div class="movements-table">
          <div class="mt-head">
            <div class="mt-col col-fecha">Fecha</div>
            <div class="mt-col col-tipo">Tipo</div>
            <div class="mt-col col-ref">Referencia</div>
            <div class="mt-col col-monto">Monto</div>
          </div>

          <template v-if="loading">
            <div class="mt-row" v-for="n in 5" :key="n">
              <div class="skeleton skeleton--line"></div>
              <div class="skeleton skeleton--line skeleton--short"></div>
              <div class="skeleton skeleton--line skeleton--long"></div>
              <div class="skeleton skeleton--line skeleton--short"></div>
            </div>
          </template>

          <template v-else>
            <div class="mt-row" v-for="row in latestSales" :key="row.__key">
              <div class="col-fecha cell-date">{{ row.fecha }}</div>
              <div class="col-tipo">
                <span class="tipo-chip" :class="`tipo-chip--${tipoChipKind(row.tipo)}`">{{
                  row.tipo
                }}</span>
              </div>
              <div class="col-ref cell-ref">{{ row.ref }}</div>
              <div class="col-monto cell-money">{{ fmtMoney(row.total) }}</div>
            </div>
            <div v-if="latestSales.length === 0" class="mt-empty">
              Sin movimientos registrados todavía.
            </div>
          </template>
        </div>
      </AppCard>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onActivated, ref, computed, getCurrentInstance, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppCard from '@/components/ui/AppCard.vue'
import { fetchDashboardMetrics, fetchLatestSales } from '@/services/dashboard'

// ── IDs únicos por instancia (evita colisiones SVG en HMR y multi-instancia) ──
const _uid = getCurrentInstance()?.uid ?? Math.random().toString(36).slice(2)
const gradAreaId = `dg-area-${_uid}`
const gradShimmerId = `dg-shimmer-${_uid}`

// ── Constantes del chart ──────────────────────────────────────────────────────
const CW = 900
const CH = 280
const GRID_Y = [46, 100, 154, 208]

// ── Estado ────────────────────────────────────────────────────────────────────
// loading arranca en false para evitar el bug de "skeletons eternos".
const loading = ref(false)
const fetching = ref(false) // guard de concurrencia (separado del estado visual)
const hasError = ref(false)
const chartHoverX = ref(null) // crosshair hover en el chart

const kpis = ref({
  ventasMes: 0,
  ventasMesOps: null,
  liquidez: 0,
  aCobrar: 0,
  aPagar: 0,
  chequesCartera: 0,
  aCobrarSobreLiquidezPct: null,
  aPagarSobreLiquidezPct: null,
})

const alerts = ref([])
const latestSales = ref([])
const series = ref({ days: 7, labels: [], values: [] })

// ── Computed ──────────────────────────────────────────────────────────────────
const chartPaths = computed(() => buildPaths(series.value.values))
const chartDays = computed(() => series.value.labels.length || series.value.days || 7)

const kpiCards = computed(() => [
  {
    id: 'ventas',
    label: 'Ventas del mes',
    featured: true,
    pill: fmtCount(kpis.value.ventasMesOps),
    pillKind: 'neutral',
    value: fmtMoney(kpis.value.ventasMes),
    sub: 'acumulado en el período',
  },
  {
    id: 'liquidez',
    label: 'Liquidez',
    pill: kpis.value.liquidez > 0 ? 'OK' : '—',
    pillKind: kpis.value.liquidez > 0 ? 'ok' : 'neutral',
    value: fmtMoney(kpis.value.liquidez),
    sub: 'caja y bancos',
  },
  {
    id: 'cobrar',
    label: 'A cobrar',
    pill: fmtPct(kpis.value.aCobrarSobreLiquidezPct),
    pillKind: 'neutral', // FIX: era '' → sin estilo
    value: fmtMoney(kpis.value.aCobrar),
    sub: 'cta. cte. clientes',
  },
  {
    id: 'pagar',
    label: 'A pagar',
    pill: fmtPct(kpis.value.aPagarSobreLiquidezPct),
    pillKind:
      kpis.value.aPagar > kpis.value.liquidez && kpis.value.liquidez > 0 ? 'warn' : 'neutral',
    value: fmtMoney(kpis.value.aPagar),
    sub: 'cta. cte. proveedores',
  },
])

// ── Formatters ────────────────────────────────────────────────────────────────
const fmtMoney = (n) =>
  Number(n || 0).toLocaleString('es-AR', {
    style: 'currency',
    currency: 'ARS',
    maximumFractionDigits: 0,
  })

const fmtCount = (n) => (n === null || n === undefined ? '—' : Number(n).toLocaleString('es-AR'))

const fmtPct = (n) => {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '—'
  const v = Number(n)
  return `${v > 0 ? '+' : ''}${v.toFixed(0)}%`
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function pick(obj, keys, fallback = null) {
  for (const k of keys) {
    if (obj?.[k] !== undefined && obj?.[k] !== null) return obj[k]
  }
  return fallback
}

// FIX: también acepta objetos/arrays directos (no solo strings)
function safeJsonParse(raw, fallback) {
  if (raw === null || raw === undefined) return fallback
  if (Array.isArray(raw) || typeof raw === 'object') return raw
  if (typeof raw !== 'string') return fallback
  const s = raw.trim()
  if (!s) return fallback
  try {
    return JSON.parse(s)
  } catch {
    return fallback
  }
}

function fmtDateTime(v) {
  if (!v) return '—'
  const s = String(v).trim()
  if (!s) return '—'
  try {
    // El backend envía timestamps UTC sin marcador de offset (sin Z ni ±HH:MM).
    // Agregamos 'Z' para que Date() los interprete como UTC en todos los navegadores.
    const hasOffset = /[Zz]$|[+-]\d{2}:\d{2}$/.test(s)
    const iso = /^\d{4}-\d{2}-\d{2}$/.test(s)
      ? `${s}T00:00:00Z` // solo fecha → medianoche UTC
      : hasOffset
        ? s
        : `${s}Z` // sin offset → asumir UTC
    const d = new Date(iso)
    if (isNaN(d.getTime())) return s
    return new Intl.DateTimeFormat('es-AR', {
      timeZone: 'America/Argentina/Buenos_Aires',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(d)
  } catch {
    return s
  }
}

function buildPaths(values) {
  const PAD_TOP = 20
  const PAD_BOT = 30
  const USABLE = CH - PAD_TOP - PAD_BOT

  const raw = (values || []).map((x) => Number(x || 0)).filter(Number.isFinite)
  // Mínimo 2 puntos: stepX nunca Infinity, coords nunca NaN
  const v = raw.length >= 2 ? raw : raw.length === 1 ? [raw[0], raw[0]] : [0, 0]
  const n = v.length
  const max = Math.max(...v, 1)

  const pts = v.map((val, i) => ({
    x: i === n - 1 ? CW : (CW / (n - 1)) * i,
    y: PAD_TOP + (1 - val / max) * USABLE,
  }))

  let d = `M${pts[0].x.toFixed(2)} ${pts[0].y.toFixed(2)}`
  for (let i = 0; i < n - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)]
    const p1 = pts[i]
    const p2 = pts[i + 1]
    const p3 = pts[Math.min(n - 1, i + 2)]
    const c1x = p1.x + (p2.x - p0.x) / 6
    const c1y = p1.y + (p2.y - p0.y) / 6
    const c2x = p2.x - (p3.x - p1.x) / 6
    const c2y = p2.y - (p3.y - p1.y) / 6
    d += ` C${c1x.toFixed(2)} ${c1y.toFixed(2)},${c2x.toFixed(2)} ${c2y.toFixed(2)},${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`
  }

  return {
    line: d,
    area: `${d} L${CW} ${CH} L0 ${CH} Z`,
    points: pts, // expuestos para los dots
  }
}

function normalizeLatestSales(rows) {
  return (rows || []).map((r, idx) => {
    const fecha = fmtDateTime(pick(r, ['fecha', 'created', 'fecha_emision', 'date'], ''))
    const total = Number(pick(r, ['total', 'importe_total', 'monto_total', 'importe'], 0) || 0)
    const tipo = String(
      r?.tipo_comprobante?.nombre || pick(r, ['tipo', 'kind'], 'Comprobante') || '',
    )
    const num = String(pick(r, ['numero_completo'], '') || '')
      .replace(/\s+/g, ' ')
      .trim()
    const cliente =
      String(r?.cliente?.entidad?.razon_social || '').trim() ||
      String(r?.cliente?.razon_social || '').trim()
    const ref = [tipo, num, cliente].filter(Boolean).join(' · ') || '—'
    return {
      __key: pick(r, ['id'], `${idx}-${num || 'row'}`),
      fecha,
      tipo: tipo || '—',
      ref,
      total,
    }
  })
}

function buildAlerts(m) {
  const liquidez = Number(pick(m, ['liquidez'], 0) || 0)
  const aCobrar = Number(pick(m, ['a_cobrar', 'aCobrar'], 0) || 0)
  const aPagar = Number(pick(m, ['a_pagar', 'aPagar'], 0) || 0)
  const cheques = Number(pick(m, ['cheques_cartera', 'chequesCartera'], 0) || 0)
  const out = []

  // FIX: también alerta cuando hay compromisos pero liquidez = 0
  if (aPagar > 0 && liquidez === 0)
    out.push({
      kind: 'warn',
      title: 'Sin liquidez disponible',
      subtitle: `Hay compromisos por ${fmtMoney(aPagar)} sin fondos en caja/bancos.`,
    })
  else if (aPagar > liquidez && liquidez > 0)
    out.push({
      kind: 'warn',
      title: 'Compromisos superan liquidez',
      subtitle: `A pagar ${fmtMoney(aPagar)} vs. liquidez ${fmtMoney(liquidez)}.`,
    })

  if (aCobrar > 0)
    out.push({
      kind: 'neutral',
      title: 'Cuentas a cobrar',
      subtitle: `Saldo pendiente de clientes: ${fmtMoney(aCobrar)}.`,
    })
  if (cheques > 0)
    out.push({
      kind: 'ok',
      title: 'Cheques en cartera',
      subtitle: `Disponibles: ${fmtMoney(cheques)}.`,
    })

  return out.slice(0, 6)
}

// ── Interacción chart ─────────────────────────────────────────────────────────
function onChartHover(e) {
  const svg = e.currentTarget
  const rect = svg.getBoundingClientRect()
  const ratio = (e.clientX - rect.left) / rect.width
  chartHoverX.value = Math.max(0, Math.min(CW, ratio * CW))
}

// ── Clasificación chips de tipo ───────────────────────────────────────────────
function tipoChipKind(tipo) {
  const t = String(tipo).toLowerCase()
  if (t.includes('factura a')) return 'a'
  if (t.includes('factura b')) return 'b'
  if (t.includes('factura c')) return 'c'
  if (t.includes('nota de crédito') || t.includes('nc')) return 'nc'
  if (t.includes('nota de débito') || t.includes('nd')) return 'nd'
  if (t.includes('remito')) return 'remito'
  if (t.includes('presupuesto')) return 'presupuesto'
  return 'default'
}

// ── Carga de datos ────────────────────────────────────────────────────────────
async function loadData() {
  if (fetching.value) return
  fetching.value = true
  loading.value = true
  hasError.value = false

  try {
    const metrics = await fetchDashboardMetrics()

    // Chart
    const labels = safeJsonParse(pick(metrics, ['chart_labels', 'labels'], '[]'), [])
    const data = safeJsonParse(pick(metrics, ['chart_data', 'data'], '[]'), [])
    series.value = {
      // FIX: data.length || 7 → si data=[] devolvía 0; ahora siempre fallback a 7
      days: Array.isArray(data) ? data.length || 7 : 7,
      labels: Array.isArray(labels) ? labels.map(String) : [],
      values: Array.isArray(data) ? data.map((x) => Number(x || 0)) : [],
    }

    // KPIs
    const liquidez = Number(pick(metrics, ['liquidez'], 0) || 0)
    const aCobrar = Number(pick(metrics, ['a_cobrar', 'aCobrar'], 0) || 0)
    const aPagar = Number(pick(metrics, ['a_pagar', 'aPagar'], 0) || 0)
    const ventasMes = Number(pick(metrics, ['ventas_mes', 'ventasMes'], 0) || 0)
    const cheques = Number(pick(metrics, ['cheques_cartera', 'chequesCartera'], 0) || 0)
    const pct = (num, den) => (Number(den || 0) ? (Number(num || 0) / Number(den)) * 100 : null)

    kpis.value = {
      ventasMes,
      ventasMesOps: pick(metrics, ['ventas_mes_ops', 'ventasMesOps', 'ventas_mes_count'], null),
      liquidez,
      aCobrar,
      aPagar,
      chequesCartera: cheques,
      aCobrarSobreLiquidezPct: pct(aCobrar, liquidez),
      aPagarSobreLiquidezPct: pct(aPagar, liquidez),
    }

    alerts.value = buildAlerts(metrics)

    // Latest sales: fallo silencioso para no romper los KPIs
    try {
      latestSales.value = normalizeLatestSales(await fetchLatestSales({ limit: 5 }))
    } catch (e) {
      console.warn('[Dashboard] latestSales falló:', e)
      latestSales.value = []
    }
  } catch (e) {
    console.error('[Dashboard] error cargando métricas:', e)
    hasError.value = true
    kpis.value = {
      ventasMes: 0,
      ventasMesOps: null,
      liquidez: 0,
      aCobrar: 0,
      aPagar: 0,
      chequesCartera: 0,
      aCobrarSobreLiquidezPct: null,
      aPagarSobreLiquidezPct: null,
    }
    alerts.value = []
    latestSales.value = []
    series.value = { days: 7, labels: [], values: [0, 0] }
  } finally {
    loading.value = false
    fetching.value = false
  }
}

// ── Defensa contra CSS global contaminado por el POS ─────────────────────────
const cleanupPollutedGlobalCSS = () => {
  const root = document.documentElement
  ;[
    '--pos-footer-space',
    '--pos-footer-left',
    '--pos-footer-width',
    '--pos-footer-bg',
    '--pos-footer-border',
    '--pos-available-h',
  ].forEach((v) => root.style.removeProperty(v))
  root.classList.remove('pos-focus-mode')
  document.body.classList.remove('pos-focus-mode')
}

onMounted(() => {
  cleanupPollutedGlobalCSS()
  loadData()
})

// Keep-alive: onMounted no se re-ejecuta al volver; onActivated sí.
onActivated(() => {
  cleanupPollutedGlobalCSS()
  loadData()
})

// FIX: condición tautológica eliminada — `newName === route.name` siempre era true.
// Ahora solo limpiamos CSS contaminado cuando la ruta activa ES esta vista (home).
const route = useRoute()
watch(
  () => route.name,
  (newName) => {
    if (newName === 'home') cleanupPollutedGlobalCSS()
  },
)
</script>

<style scoped>
/* ─────────────────────────────────────────────────────────────────────────────
   LAYOUT PRINCIPAL
   ───────────────────────────────────────────────────────────────────────────── */
.dash {
  display: grid;
  gap: 20px;
  padding-bottom: 12px;
}

/* ─────────────────────────────────────────────────────────────────────────────
   ERROR BANNER
   ───────────────────────────────────────────────────────────────────────────── */
.error-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 16px;
  border-radius: var(--radius-md, 8px);
  background: rgba(239, 68, 68, 0.06);
  border: 1px solid rgba(239, 68, 68, 0.2);
  color: var(--text-0);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.01em;
}
.error-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  color: #ef4444;
}
.retry-btn {
  margin-left: auto;
  padding: 5px 14px;
  border-radius: 6px;
  border: 1px solid rgba(239, 68, 68, 0.3);
  background: transparent;
  color: #dc2626;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  cursor: pointer;
  transition:
    background 0.15s,
    border-color 0.15s;
}
.retry-btn:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.45);
}
.retry-btn:disabled {
  opacity: 0.45;
  cursor: default;
}

/* ─────────────────────────────────────────────────────────────────────────────
   KPI CARDS
   ───────────────────────────────────────────────────────────────────────────── */
.kpis {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.kpi-card {
  background: var(--surface-1, #fff);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg, 10px);
  box-shadow: var(--card-shadow, 0 4px 16px rgba(2, 6, 23, 0.07));
  padding: 18px 20px 16px;
  position: relative;
  overflow: hidden;
  transition:
    box-shadow 0.2s ease,
    transform 0.2s ease;
}
.kpi-card:hover {
  box-shadow: 0 8px 28px rgba(2, 6, 23, 0.12);
  transform: translateY(-2px);
}
/* Accent bar top — solo en featured */
.kpi-card--featured::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: rgba(var(--accent-rgb), 1);
  border-radius: 2px 2px 0 0;
}
/* Subtle background tint en featured */
.kpi-card--featured::after {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(
    ellipse at top left,
    rgba(var(--accent-rgb), 0.04) 0%,
    transparent 70%
  );
  pointer-events: none;
}

.kpi-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
.kpi-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-2);
}
.kpi-value {
  font-size: 30px;
  font-weight: 800;
  letter-spacing: -0.5px;
  color: var(--text-0);
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}
.kpi-card--featured .kpi-value {
  font-size: 34px;
}
.kpi-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
}
.kpi-sub {
  font-size: 12px;
  color: var(--text-2);
  letter-spacing: 0.01em;
}
.kpi-trend {
  width: 14px;
  height: 14px;
  display: grid;
  place-items: center;
}
.kpi-trend.up {
  color: #16a34a;
}
.kpi-trend.down {
  color: #dc2626;
}
.kpi-trend svg {
  width: 10px;
  height: 10px;
  fill: currentColor;
}

/* Pills */
.kpi-pill {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.04em;
  padding: 4px 10px;
  border-radius: 5px;
  line-height: 1;
  border: 1px solid transparent;
  transition: all 0.15s ease;
}
.kpi-pill.neutral {
  background: rgba(148, 163, 184, 0.1);
  border-color: rgba(148, 163, 184, 0.2);
  color: var(--text-2);
}
.kpi-pill.warn {
  background: rgba(245, 158, 11, 0.1);
  border-color: rgba(245, 158, 11, 0.25);
  color: #92400e;
}
.kpi-pill.ok {
  background: rgba(34, 197, 94, 0.1);
  border-color: rgba(34, 197, 94, 0.25);
  color: #15803d;
}

/* ─────────────────────────────────────────────────────────────────────────────
   GRID
   ───────────────────────────────────────────────────────────────────────────── */
.grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
}
.span-full {
  grid-column: 1 / -1;
}

/* ─────────────────────────────────────────────────────────────────────────────
   CARD HEAD (compartido por todos los cards)
   ───────────────────────────────────────────────────────────────────────────── */
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.card-head-left {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.card-title {
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 0.02em;
  color: var(--text-0);
}
.card-sub {
  font-size: 11px;
  color: var(--text-2);
  letter-spacing: 0.01em;
}

/* ─────────────────────────────────────────────────────────────────────────────
   CHART
   ───────────────────────────────────────────────────────────────────────────── */
.chart-wrap {
  padding: 4px 0 0;
  position: relative;
}
.chart-svg {
  width: 100%;
  height: 260px;
  display: block;
  cursor: crosshair;
}

.chart-grid line {
  stroke: var(--chart-grid);
  stroke-width: 1;
  shape-rendering: crispEdges;
}
.chart-area {
  opacity: 0.85;
}
.chart-line-base {
  fill: none;
  stroke: var(--chart-line-base);
  stroke-width: 3;
}
.chart-line {
  fill: none;
  stroke: var(--chart-line);
  stroke-width: 2.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.chart-shimmer {
  fill: none;
  stroke-width: 3;
  opacity: 0.85;
}
.chart-dot {
  fill: var(--surface-1, #fff);
  stroke: rgba(var(--accent-rgb), 0.85);
  stroke-width: 2;
  transition: r 0.15s ease;
}
.chart-dot:hover {
  r: 6;
}
.chart-crosshair {
  stroke: rgba(var(--accent-rgb), 0.3);
  stroke-width: 1;
  stroke-dasharray: 4 3;
  pointer-events: none;
}

.chart-labels {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(56px, 1fr));
  gap: 6px;
  margin-top: 10px;
  padding: 0 2px;
  font-size: 10.5px;
  letter-spacing: 0.02em;
  color: var(--text-2);
  user-select: none;
  opacity: 0.85;
}

.legend {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--text-2);
}
.legend-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: rgba(var(--accent-rgb), 1);
  box-shadow: 0 0 6px rgba(var(--accent-rgb), 0.6);
}
.legend-label {
  text-transform: uppercase;
  font-size: 10px;
}

/* ─────────────────────────────────────────────────────────────────────────────
   ALERTAS
   ───────────────────────────────────────────────────────────────────────────── */
.alert-count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 800;
  background: rgba(245, 158, 11, 0.15);
  border: 1px solid rgba(245, 158, 11, 0.3);
  color: #92400e;
}

.alerts {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.alert-item {
  display: flex;
  align-items: flex-start;
  gap: 11px;
  padding: 12px 14px;
  border-radius: var(--radius-md, 8px);
  border: 1px solid transparent;
  transition: transform 0.15s ease;
}
.alert-item:hover {
  transform: translateX(2px);
}

.alert-item--warn {
  background: rgba(245, 158, 11, 0.07);
  border-color: rgba(245, 158, 11, 0.18);
}
.alert-item--ok {
  background: rgba(34, 197, 94, 0.07);
  border-color: rgba(34, 197, 94, 0.18);
}
.alert-item--neutral {
  background: rgba(148, 163, 184, 0.06);
  border-color: var(--border);
}

.alert-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  margin-top: 1px;
}
.alert-item--warn .alert-icon {
  color: #d97706;
}
.alert-item--ok .alert-icon {
  color: #16a34a;
}
.alert-item--neutral .alert-icon {
  color: var(--text-2);
}
.alert-icon svg {
  width: 100%;
  height: 100%;
}

.alert-body {
  flex: 1;
  min-width: 0;
}
.alert-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-0);
  line-height: 1.3;
}
.alert-sub {
  margin-top: 3px;
  font-size: 12px;
  color: var(--text-2);
  line-height: 1.4;
}

/* ─────────────────────────────────────────────────────────────────────────────
   TABLA DE MOVIMIENTOS
   ───────────────────────────────────────────────────────────────────────────── */
.refresh-btn {
  width: 30px;
  height: 30px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: transparent;
  cursor: pointer;
  display: grid;
  place-items: center;
  color: var(--text-2);
  transition:
    background 0.15s,
    color 0.15s,
    border-color 0.15s;
  flex-shrink: 0;
}
.refresh-btn:hover:not(:disabled) {
  background: rgba(var(--accent-rgb), 0.07);
  border-color: rgba(var(--accent-rgb), 0.25);
  color: rgba(var(--accent-rgb), 1);
}
.refresh-btn:disabled {
  opacity: 0.4;
  cursor: default;
}
.refresh-icon {
  width: 14px;
  height: 14px;
  transition: transform 0.3s ease;
}
.refresh-icon.spinning {
  animation: spin 0.9s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.movements-table {
  border-radius: var(--radius-md, 8px);
  overflow: hidden;
  border: 1px solid var(--border);
}

.mt-head {
  display: grid;
  grid-template-columns: 172px 120px 1fr 160px;
  gap: 0;
  padding: 0;
  background: rgba(148, 163, 184, 0.06);
  border-bottom: 1px solid var(--border);
}
.mt-row {
  display: grid;
  grid-template-columns: 172px 120px 1fr 160px;
  gap: 0;
  border-bottom: 1px solid var(--border);
  transition: background 0.12s ease;
}
.mt-row:last-child {
  border-bottom: none;
}
.mt-row:hover {
  background: rgba(var(--accent-rgb), 0.04);
}

.mt-col,
.mt-row > div {
  padding: 11px 16px;
  font-size: 13px;
  display: flex;
  align-items: center;
}
/* separadores verticales entre columnas */
.mt-col + .mt-col,
.mt-row > div + div {
  border-left: 1px solid var(--border);
}

.mt-col {
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--text-2);
  padding-top: 9px;
  padding-bottom: 9px;
}

.col-monto,
.mt-head .col-monto {
  justify-content: flex-end;
}

.cell-date {
  color: var(--text-2);
  font-variant-numeric: tabular-nums;
  font-size: 12px;
  letter-spacing: 0.02em;
}
.cell-ref {
  color: var(--text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
}
.cell-money {
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  color: var(--text-0);
  letter-spacing: -0.2px;
  justify-content: flex-end;
}

/* Tipo chips */
.tipo-chip {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border-radius: 5px;
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 0.04em;
  line-height: 1;
  border: 1px solid transparent;
}
.tipo-chip--a {
  background: rgba(37, 99, 235, 0.1);
  border-color: rgba(37, 99, 235, 0.22);
  color: #1d4ed8;
}
.tipo-chip--b {
  background: rgba(34, 197, 94, 0.1);
  border-color: rgba(34, 197, 94, 0.22);
  color: #15803d;
}
.tipo-chip--c {
  background: rgba(245, 158, 11, 0.1);
  border-color: rgba(245, 158, 11, 0.22);
  color: #92400e;
}
.tipo-chip--nc {
  background: rgba(168, 85, 247, 0.1);
  border-color: rgba(168, 85, 247, 0.22);
  color: #7e22ce;
}
.tipo-chip--nd {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.22);
  color: #b91c1c;
}
.tipo-chip--remito {
  background: rgba(148, 163, 184, 0.1);
  border-color: rgba(148, 163, 184, 0.22);
  color: var(--text-2);
}
.tipo-chip--presupuesto {
  background: rgba(20, 184, 166, 0.1);
  border-color: rgba(20, 184, 166, 0.22);
  color: #0f766e;
}
.tipo-chip--default {
  background: rgba(148, 163, 184, 0.1);
  border-color: rgba(148, 163, 184, 0.18);
  color: var(--text-2);
}

.mt-empty {
  padding: 24px 16px;
  font-size: 13px;
  color: var(--text-2);
  font-style: italic;
  text-align: center;
}

/* ─────────────────────────────────────────────────────────────────────────────
   SKELETONS
   ───────────────────────────────────────────────────────────────────────────── */
@keyframes shimmer {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}

.skeleton {
  position: relative;
  overflow: hidden;
  border-radius: 6px;
  background: rgba(148, 163, 184, 0.12);
}
.skeleton::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.2) 50%,
    transparent 100%
  );
  animation: shimmer 1.4s ease-in-out infinite;
}
.skeleton--pill {
  height: 24px;
  width: 56px;
  border-radius: 5px;
}
.skeleton--value {
  height: 34px;
  width: 64%;
  border-radius: 6px;
  margin: 4px 0;
}
.skeleton--sub {
  height: 12px;
  width: 48%;
  border-radius: 5px;
}
.skeleton--line {
  height: 13px;
  width: 100%;
  border-radius: 5px;
}
.skeleton--short {
  width: 50%;
}
.skeleton--long {
  width: 85%;
}
.skeleton--chart {
  height: 260px;
  border-radius: 8px;
}
.skeleton--alert {
  height: 56px;
  border-radius: var(--radius-md, 8px);
}

/* ─────────────────────────────────────────────────────────────────────────────
   TRANSICIONES
   ───────────────────────────────────────────────────────────────────────────── */
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition:
    opacity 0.22s ease,
    transform 0.22s ease;
}
.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* ─────────────────────────────────────────────────────────────────────────────
   RESPONSIVE
   ───────────────────────────────────────────────────────────────────────────── */
@media (max-width: 1280px) {
  .kpis {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 1024px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 640px) {
  .kpis {
    grid-template-columns: 1fr 1fr;
  }
  .kpi-value {
    font-size: 22px;
  }
  .kpi-card--featured .kpi-value {
    font-size: 26px;
  }
  .mt-head,
  .mt-row {
    grid-template-columns: 1fr 1fr;
  }
  .col-ref {
    display: none;
  }
  .col-fecha,
  .col-monto,
  .col-tipo {
    display: flex;
  }
}
</style>
