<script setup>
import { computed, ref, watch, nextTick } from 'vue'
import { message } from 'ant-design-vue'
import {
  PictureOutlined,
  SearchOutlined,
  CloseOutlined,
  AppstoreOutlined,
  CheckOutlined,
  PlusOutlined,
} from '@ant-design/icons-vue'
import api from '@/services/api'

// ── Props / Emits ─────────────────────────────────────────────────────────────
const props = defineProps({
  open: { type: Boolean, default: false },
})
const emit = defineEmits(['update:open', 'add-items'])

const internalOpen = computed({
  get: () => props.open,
  set: (v) => emit('update:open', v),
})

// ── Search state ──────────────────────────────────────────────────────────────
const searchText = ref('')
const searchMode = ref('contains') // 'contains' | 'starts' | 'ends' | 'exact'
const loading = ref(false)
const rows = ref([])
const hasSearched = ref(false) // true once user performed at least one search

const searchModeOptions = [
  { value: 'contains', label: 'Contiene' },
  { value: 'starts', label: 'Comienza con' },
  { value: 'ends', label: 'Termina en' },
  { value: 'exact', label: 'Exacto' },
]

// Which field to search against
const searchField = ref('all')
const searchFieldOptions = [
  { value: 'all', label: 'Todos los campos' },
  { value: 'cod_articulo', label: 'Código' },
  { value: 'descripcion', label: 'Descripción' },
  { value: 'ean', label: 'Cód. de barras' },
  { value: 'marca', label: 'Marca' },
]

// ── Pagination ────────────────────────────────────────────────────────────────
const pageSize = ref(10)
const offset = ref(0)
const total = ref(0)
const currentPage = computed(() => Math.floor(offset.value / pageSize.value) + 1)

// ── Selection ─────────────────────────────────────────────────────────────────
const selectedRowKeys = ref([])
const qtyById = ref({}) // { [cod_articulo]: number }

// ── Image preview ─────────────────────────────────────────────────────────────
const previewOpen = ref(false)
const previewItem = ref(null)

// ── Debounce timer ────────────────────────────────────────────────────────────
let searchTimer = null

// ── Columns ───────────────────────────────────────────────────────────────────
const columns = [
  { title: 'Código', dataIndex: 'cod_articulo', width: 130 },
  { title: 'Descripción', dataIndex: 'descripcion' },
  { title: 'Marca', dataIndex: 'marca', width: 140 },
  { title: 'Stock', dataIndex: 'stock_total', width: 80, align: 'right' },
  { title: 'Precio', dataIndex: 'precio', width: 120, align: 'right' },
  { title: 'Cant.', dataIndex: 'cantidad', width: 100, align: 'center' },
  { title: '', dataIndex: 'img', width: 44, align: 'center' },
]

// ── Reset ─────────────────────────────────────────────────────────────────────
const resetState = () => {
  searchText.value = ''
  searchMode.value = 'contains'
  searchField.value = 'all'
  rows.value = []
  selectedRowKeys.value = []
  qtyById.value = {}
  offset.value = 0
  total.value = 0
  hasSearched.value = false
  previewOpen.value = false
  previewItem.value = null
  if (searchTimer) {
    clearTimeout(searchTimer)
    searchTimer = null
  }
}

watch(
  () => props.open,
  (v) => {
    if (v) resetState()
  },
)

// ── Utilities ─────────────────────────────────────────────────────────────────
const moneyAR = (n) =>
  (Number(n) || 0).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const parsePrice = (p) => {
  const raw = p?.precio_venta
  if (!raw) return 0
  const n = parseFloat(typeof raw === 'object' ? raw.amount : raw)
  return isNaN(n) ? 0 : n
}

const getImageUrl = (path) => {
  if (!path) return null
  if (path.startsWith('http')) return path
  return `${api?.defaults?.baseURL || ''}${path}`
}

/**
 * Build the search query string based on mode.
 * The backend `search` param is a DRF SearchFilter — it uses icontains by default.
 * For starts/ends/exact, we pass the query as-is and add a `search_mode` param
 * so a custom backend filter can handle it. If the backend doesn't support it,
 * it gracefully falls back to icontains.
 */
/**
 * Build query params for the backend.
 *
 * search_field: tells the backend WHICH field to filter on.
 *   'all'          → standard DRF SearchFilter across all configured fields
 *   'cod_articulo' → filter only on code (exact prefix/suffix as requested)
 *   'descripcion'  → filter only on description
 *   'ean'          → filter only on barcode
 *   'marca'        → filter only on brand name
 *
 * search_mode: tells the backend HOW to match.
 *   'contains'  → icontains (default)
 *   'starts'    → istartswith
 *   'ends'      → iendswith
 *   'exact'     → iexact
 *
 * If the backend doesn't implement these params yet, it falls back to icontains
 * on all configured search fields — which is better than no search at all.
 */
const buildSearchParams = (q) => {
  const params = {
    search: q,
    limit: pageSize.value,
    offset: offset.value,
  }
  if (searchField.value !== 'all') {
    params.search_field = searchField.value
  }
  if (searchMode.value !== 'contains') {
    params.search_mode = searchMode.value
  }
  return params
}

// ── Fetch ─────────────────────────────────────────────────────────────────────
const fetchArticulos = async () => {
  const q = (searchText.value || '').trim()

  // Allow any non-empty search — no minimum length restriction
  if (!q) {
    rows.value = []
    total.value = 0
    hasSearched.value = false
    return
  }

  loading.value = true
  hasSearched.value = true

  try {
    const { data } = await api.get('/api/articulos/', { params: buildSearchParams(q) })

    const list = data?.results ?? data
    const count = data?.count ?? (Array.isArray(list) ? list.length : 0)

    // If backend returns ALL results without filtering (no match scenario),
    // it should return count=0 for a genuinely empty search.
    // We trust the backend count; if count === 0 we show empty state.
    total.value = count

    rows.value = (list || []).map((p) => ({
      id: p.cod_articulo,
      cod_articulo: p.cod_articulo,
      descripcion: p.descripcion,
      marca: p.marca?.nombre || '—',
      stock_total: Number(p.stock_total) || 0,
      precio: parsePrice(p),
      foto: p.foto || null,
      raw: p,
    }))

    // Preserve existing qty for articles still in results
    // but clear stale qtyById entries from previous searches
    const currentIds = new Set(rows.value.map((r) => r.id))
    for (const key of Object.keys(qtyById.value)) {
      if (!currentIds.has(key) && !selectedRowKeys.value.includes(key)) {
        delete qtyById.value[key]
      }
    }
  } catch (e) {
    console.error(e)
    message.error('Error buscando artículos')
  } finally {
    loading.value = false
  }
}

// ── Search triggers ───────────────────────────────────────────────────────────

/** Immediate search (Enter key or Search button click) */
const onSearch = async () => {
  if (searchTimer) {
    clearTimeout(searchTimer)
    searchTimer = null
  }
  offset.value = 0
  await fetchArticulos()
}

/** Re-search when field or mode changes, but only if a search was already performed */
watch([searchMode, searchField], () => {
  if (hasSearched.value && searchText.value.trim()) {
    offset.value = 0
    fetchArticulos()
  }
})

const onTableChange = async (pagination) => {
  offset.value = ((pagination?.current || 1) - 1) * pageSize.value
  pageSize.value = pagination?.pageSize || pageSize.value
  await fetchArticulos()
}

// ── Selection ─────────────────────────────────────────────────────────────────
const ensureQty = (id) => {
  if (!qtyById.value[id]) qtyById.value[id] = 1
}

const rowSelection = computed(() => ({
  selectedRowKeys: selectedRowKeys.value,
  onChange: (keys) => {
    selectedRowKeys.value = keys
    keys.forEach(ensureQty)
  },
}))

const setQty = (id, v) => {
  const n = Number(v)
  qtyById.value[id] = !n || n <= 0 ? 1 : Math.floor(n)
}

const selectedCount = computed(() => selectedRowKeys.value.length)

const selectedPayload = () =>
  selectedRowKeys.value
    .map((id) => {
      const row = rows.value.find((r) => r.id === id)
      if (!row) return null
      return { producto: row.raw, cantidad: qtyById.value[id] || 1 }
    })
    .filter(Boolean)

// ── Image preview ─────────────────────────────────────────────────────────────
const openPreview = (row) => {
  previewItem.value = row
  previewOpen.value = true
}
const closePreview = () => {
  previewOpen.value = false
  previewItem.value = null
}

// ── Actions ───────────────────────────────────────────────────────────────────
const addAndContinue = () => {
  const items = selectedPayload()
  if (!items.length) {
    message.warning('Seleccioná al menos un artículo')
    return
  }
  emit('add-items', { items, close: false })
  const n = items.reduce((a, i) => a + i.cantidad, 0)
  selectedRowKeys.value = []
  qtyById.value = {}
  message.success(
    `${n} unidad${n !== 1 ? 'es' : ''} agregada${n !== 1 ? 's' : ''}. Podés seguir cargando.`,
  )
}

const addAndFinish = () => {
  const items = selectedPayload()
  if (!items.length) {
    message.warning('Seleccioná al menos un artículo')
    return
  }
  emit('add-items', { items, close: true })
  internalOpen.value = false
}

const cancel = () => {
  internalOpen.value = false
}
</script>

<template>
  <a-modal
    v-model:open="internalOpen"
    title="Buscar artículos"
    width="1100px"
    centered
    :maskClosable="false"
    class="asm-modal"
  >
    <div class="asm-root">
      <!-- ── Search bar ──────────────────────────────────────────────────── -->
      <div class="asm-searchbar">
        <!-- Row 1: field + mode selectors -->
        <div class="asm-filters">
          <div class="filter-group">
            <span class="filter-label">Campo</span>
            <a-select
              v-model:value="searchField"
              :options="searchFieldOptions"
              size="small"
              style="width: 160px"
              class="filter-select"
            />
          </div>
          <div class="filter-sep" />
          <div class="filter-group">
            <span class="filter-label">Modo</span>
            <a-segmented
              v-model:value="searchMode"
              :options="searchModeOptions"
              size="small"
              class="mode-seg"
            />
          </div>
          <!-- Context hint -->
          <span class="filter-hint">
            {{ searchFieldOptions.find((o) => o.value === searchField)?.label }}
            que
            {{ searchModeOptions.find((o) => o.value === searchMode)?.label.toLowerCase() }}…
          </span>
        </div>

        <!-- Row 2: input + button -->
        <div class="asm-input-row">
          <a-input
            v-model:value="searchText"
            :placeholder="`Ej: ${searchField === 'cod_articulo' ? 'AR001' : searchField === 'ean' ? '7790001234567' : searchField === 'marca' ? 'Philips' : 'Pañal'}`"
            allow-clear
            size="large"
            class="asm-input"
            @press-enter="onSearch"
          >
            <template #prefix><SearchOutlined class="asm-input-icon" /></template>
          </a-input>
          <a-button
            type="primary"
            size="large"
            :loading="loading"
            @click="onSearch"
            class="asm-search-btn"
          >
            <SearchOutlined />
            Buscar
          </a-button>
        </div>
      </div>

      <!-- ── Body ───────────────────────────────────────────────────────── -->
      <div class="asm-body" :class="{ 'asm-body--preview': previewOpen }">
        <!-- Table panel -->
        <div class="asm-table-panel">
          <!-- Selection bar -->
          <transition name="slide-down">
            <div class="asm-selection-bar" v-if="selectedCount > 0">
              <CheckOutlined class="sel-icon" />
              <span
                >{{ selectedCount }} artículo{{ selectedCount !== 1 ? 's' : '' }} seleccionado{{
                  selectedCount !== 1 ? 's' : ''
                }}</span
              >
            </div>
          </transition>

          <a-table
            :columns="columns"
            :data-source="rows"
            :loading="loading"
            rowKey="id"
            size="middle"
            :row-selection="rowSelection"
            :pagination="{
              current: currentPage,
              pageSize,
              total,
              showSizeChanger: true,
              pageSizeOptions: ['10', '20', '50'],
              showTotal: (t) => `${t} resultado${t !== 1 ? 's' : ''}`,
            }"
            :scroll="{ y: 400 }"
            @change="onTableChange"
            class="asm-table"
          >
            <!-- Empty state -->
            <template #emptyText>
              <div class="asm-empty">
                <AppstoreOutlined class="empty-icon" />
                <p v-if="!hasSearched">Escribí algo en el buscador para ver artículos.</p>
                <p v-else-if="loading">Buscando…</p>
                <p v-else>
                  Sin resultados para <strong>{{ searchText }}</strong
                  >.
                </p>
              </div>
            </template>

            <template #bodyCell="{ column, record }">
              <template v-if="column.dataIndex === 'descripcion'">
                <span class="cell-desc">{{ record.descripcion }}</span>
              </template>

              <template v-else-if="column.dataIndex === 'stock_total'">
                <span
                  class="cell-stock"
                  :class="{
                    'cell-stock--ok': record.stock_total > 5,
                    'cell-stock--warn': record.stock_total > 0 && record.stock_total <= 5,
                    'cell-stock--bad': record.stock_total <= 0,
                  }"
                  >{{ record.stock_total }}</span
                >
              </template>

              <template v-else-if="column.dataIndex === 'precio'">
                <span class="cell-price">$ {{ moneyAR(record.precio) }}</span>
              </template>

              <template v-else-if="column.dataIndex === 'cantidad'">
                <a-input-number
                  :min="1"
                  :value="qtyById[record.id] || 1"
                  style="width: 80px"
                  size="small"
                  @focus="ensureQty(record.id)"
                  @change="(v) => setQty(record.id, v)"
                  @click.stop
                />
              </template>

              <template v-else-if="column.dataIndex === 'img'">
                <button
                  class="img-btn"
                  :class="{ 'img-btn--active': record.foto }"
                  :title="record.foto ? 'Ver imagen' : 'Sin imagen'"
                  :disabled="!record.foto"
                  @click.stop="record.foto && openPreview(record)"
                  type="button"
                >
                  <PictureOutlined />
                </button>
              </template>
            </template>
          </a-table>

          <p class="asm-hint">
            Tip: marcá varios artículos con el checkbox y ajustá las cantidades antes de cargar.
          </p>
        </div>

        <!-- Image preview panel -->
        <transition name="slide-right">
          <div class="asm-preview-panel" v-if="previewOpen && previewItem">
            <div class="preview-header">
              <span class="preview-header-title">Vista previa</span>
              <button class="preview-close" @click="closePreview" type="button">
                <CloseOutlined />
              </button>
            </div>

            <div class="preview-img-wrap">
              <img
                v-if="getImageUrl(previewItem.foto)"
                :src="getImageUrl(previewItem.foto)"
                alt="Imagen del artículo"
              />
              <div v-else class="preview-no-img">
                <PictureOutlined />
                <span>Sin imagen</span>
              </div>
            </div>

            <div class="preview-meta">
              <span class="preview-code">{{ previewItem.cod_articulo }}</span>
              <p class="preview-desc">{{ previewItem.descripcion }}</p>
              <div class="preview-chips">
                <span class="preview-chip">{{ previewItem.marca }}</span>
                <span class="preview-chip preview-chip--stock">
                  {{ previewItem.stock_total }} un.
                </span>
                <span class="preview-chip preview-chip--price">
                  $ {{ moneyAR(previewItem.precio) }}
                </span>
              </div>
            </div>
          </div>
        </transition>
      </div>
      <!-- /.asm-body -->
    </div>
    <!-- /.asm-root -->

    <!-- ── Footer ─────────────────────────────────────────────────────────── -->
    <template #footer>
      <div class="asm-footer">
        <a-button @click="cancel">Cancelar</a-button>
        <div class="footer-right">
          <a-button @click="addAndContinue" :disabled="selectedCount === 0" class="btn-continue">
            <PlusOutlined /> Cargar y continuar
            <span v-if="selectedCount > 0" class="footer-badge">{{ selectedCount }}</span>
          </a-button>
          <a-button
            type="primary"
            @click="addAndFinish"
            :disabled="selectedCount === 0"
            class="btn-finish"
          >
            <CheckOutlined /> Carga finalizada
            <span v-if="selectedCount > 0" class="footer-badge footer-badge--primary">{{
              selectedCount
            }}</span>
          </a-button>
        </div>
      </div>
    </template>
  </a-modal>
</template>

<style scoped>
/* ── Root ──────────────────────────────────────────────────────────────────── */
.asm-root {
  --accent-rgb: 99, 102, 241;
  --radius: 7px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ── Search bar ────────────────────────────────────────────────────────────── */
.asm-searchbar {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  background: rgba(148, 163, 184, 0.04);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

/* Filter row (field + mode) */
.asm-filters {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.filter-group {
  display: flex;
  align-items: center;
  gap: 6px;
}
.filter-label {
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--text-2);
  white-space: nowrap;
}
.filter-sep {
  width: 1px;
  height: 20px;
  background: var(--border);
}
.filter-hint {
  margin-left: auto;
  font-size: 11.5px;
  color: var(--text-2);
  font-style: italic;
  white-space: nowrap;
}
:global(.mode-seg.ant-segmented) {
  font-size: 12px;
}
:global(.filter-select .ant-select-selector) {
  font-size: 12px !important;
}

/* Input row */
.asm-input-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.asm-input {
  flex: 1;
}
.asm-input-icon {
  color: var(--text-2);
}
.asm-search-btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

/* ── Body layout ───────────────────────────────────────────────────────────── */
.asm-body {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
  transition: grid-template-columns 0.25s ease;
}
.asm-body--preview {
  grid-template-columns: 1fr 280px;
}

/* ── Selection bar ─────────────────────────────────────────────────────────── */
.asm-selection-bar {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 7px 12px;
  background: rgba(var(--accent-rgb), 0.07);
  border: 1px solid rgba(var(--accent-rgb), 0.2);
  border-radius: var(--radius);
  font-size: 13px;
  font-weight: 700;
  color: rgba(var(--accent-rgb), 1);
  margin-bottom: 8px;
}
.sel-icon {
  font-size: 13px;
}

.slide-down-enter-active,
.slide-down-leave-active {
  transition: all 0.18s ease;
}
.slide-down-enter-from,
.slide-down-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* ── Table ─────────────────────────────────────────────────────────────────── */
.asm-table-panel {
  min-width: 0;
}

:global(.asm-table .ant-table-thead th) {
  font-size: 11px !important;
  font-weight: 800 !important;
  letter-spacing: 0.06em !important;
  text-transform: uppercase !important;
  color: var(--text-2) !important;
  background: rgba(148, 163, 184, 0.05) !important;
}

.cell-desc {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-0);
}

.cell-stock {
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}
.cell-stock--ok {
  color: #10b981;
}
.cell-stock--warn {
  color: #f59e0b;
}
.cell-stock--bad {
  color: #ef4444;
}

.cell-price {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: var(--text-0);
}

/* Image button */
.img-btn {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 5px;
  border: 1px solid var(--border);
  background: transparent;
  font-size: 14px;
  cursor: not-allowed;
  color: rgba(148, 163, 184, 0.4);
  transition: all 0.12s;
}
.img-btn--active {
  border-color: rgba(var(--accent-rgb), 0.3);
  background: rgba(var(--accent-rgb), 0.06);
  color: rgba(var(--accent-rgb), 0.8);
  cursor: pointer;
}
.img-btn--active:hover {
  background: rgba(var(--accent-rgb), 0.12);
  color: rgba(var(--accent-rgb), 1);
}

/* Empty state */
.asm-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 40px 20px;
  color: var(--text-2);
}
.empty-icon {
  font-size: 36px;
  opacity: 0.15;
}
.asm-empty p {
  font-size: 13px;
  margin: 0;
}

.asm-hint {
  font-size: 11.5px;
  color: var(--text-2);
  margin-top: 8px;
  padding: 0 2px;
}

/* ── Preview panel ─────────────────────────────────────────────────────────── */
.slide-right-enter-active,
.slide-right-leave-active {
  transition: all 0.22s ease;
}
.slide-right-enter-from,
.slide-right-leave-to {
  opacity: 0;
  transform: translateX(16px);
}

.asm-preview-panel {
  border: 1px solid var(--border);
  border-top: 2px solid rgba(var(--accent-rgb), 0.3);
  border-radius: var(--radius);
  background: var(--surface-1);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  align-self: start;
  position: sticky;
  top: 0;
}

.preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  background: rgba(148, 163, 184, 0.04);
}
.preview-header-title {
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--text-2);
}
.preview-close {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: transparent;
  font-size: 12px;
  cursor: pointer;
  color: var(--text-2);
  transition: background 0.12s;
}
.preview-close:hover {
  background: rgba(239, 68, 68, 0.08);
  border-color: rgba(239, 68, 68, 0.2);
  color: #dc2626;
}

.preview-img-wrap {
  aspect-ratio: 1;
  background: rgba(148, 163, 184, 0.05);
  display: grid;
  place-items: center;
  overflow: hidden;
  padding: 12px;
}
.preview-img-wrap img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.preview-no-img {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  color: var(--text-2);
  font-size: 12px;
  opacity: 0.4;
}
.preview-no-img :first-child {
  font-size: 28px;
}

.preview-meta {
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.preview-code {
  font-size: 11px;
  font-weight: 900;
  font-family: ui-monospace, monospace;
  color: rgba(var(--accent-rgb), 1);
  letter-spacing: 0.04em;
}
.preview-desc {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-0);
  margin: 0;
  line-height: 1.35;
}
.preview-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 2px;
}
.preview-chip {
  display: inline-flex;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  background: rgba(148, 163, 184, 0.1);
  border: 1px solid rgba(148, 163, 184, 0.2);
  color: var(--text-1);
}
.preview-chip--stock {
  background: rgba(16, 185, 129, 0.08);
  border-color: rgba(16, 185, 129, 0.2);
  color: #059669;
}
.preview-chip--price {
  background: rgba(var(--accent-rgb), 0.07);
  border-color: rgba(var(--accent-rgb), 0.18);
  color: rgba(var(--accent-rgb), 1);
  font-variant-numeric: tabular-nums;
}

/* ── Footer ────────────────────────────────────────────────────────────────── */
.asm-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.footer-right {
  display: flex;
  gap: 8px;
}
.btn-continue,
.btn-finish {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  position: relative;
}
.footer-badge {
  display: inline-grid;
  place-items: center;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  border-radius: 9px;
  background: rgba(var(--accent-rgb), 0.15);
  border: 1px solid rgba(var(--accent-rgb), 0.3);
  color: rgba(var(--accent-rgb), 1);
  font-size: 10px;
  font-weight: 900;
}
.footer-badge--primary {
  background: rgba(255, 255, 255, 0.22);
  border-color: rgba(255, 255, 255, 0.3);
  color: #fff;
}
</style>
