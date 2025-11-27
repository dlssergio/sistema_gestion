<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  SaveOutlined,
  PlusOutlined,
  DeleteOutlined,
  InfoCircleOutlined,
  SearchOutlined,
  UserOutlined,
  BgColorsOutlined,
  BarcodeOutlined,
  ArrowLeftOutlined,
} from '@ant-design/icons-vue'
import dayjs from 'dayjs'
import { message, theme, Modal } from 'ant-design-vue'

// --- 1. GESTIÓN DE TEMAS (5 VARIANTES) ---
const currentTheme = ref('light')

const themeConfig = computed(() => {
  if (currentTheme.value === 'dark') {
    // TEMA OSCURO (Industrial)
    return {
      algorithm: theme.darkAlgorithm,
      token: {
        colorPrimary: '#FACC15', // Amarillo
        colorBgContainer: '#141414',
        colorBgLayout: '#000000',
        colorText: '#ffffff',
        colorBorder: '#424242',
      },
      components: {
        Button: { colorPrimaryText: '#000000', fontWeight: 700 },
      },
    }
  } else if (currentTheme.value === 'modern') {
    // TEMA FUTURISTA (Cian + Carbón) - EL QUE YA TENÍAS
    return {
      algorithm: theme.darkAlgorithm,
      token: {
        colorPrimary: '#06b6d4', // Cian Neón
        colorBgLayout: '#13151a', // Carbón Profundo
        colorBgContainer: '#1d2129', // Gris Azulado
        colorBorder: '#2d333b',
        colorText: '#e2e8f0',
        borderRadius: 8,
      },
      components: {
        Button: { colorPrimaryText: '#ffffff', fontWeight: 600 },
        Table: { headerBg: '#181b21', headerColor: '#06b6d4' },
      },
    }
  } else if (currentTheme.value === 'control') {
    // TEMA CONTROL (Nuevo: Ocean Gradient + Naranja)
    return {
      algorithm: theme.darkAlgorithm,
      token: {
        colorPrimary: '#F59E0B', // Naranja Vibrante
        colorBgLayout: '#0f172a', // Azul Base (Fallback del gradiente)
        colorBgContainer: '#1e293b', // Slate 800
        colorBorder: '#334155',
        colorText: '#f8fafc',
        borderRadius: 6,
      },
      components: {
        Button: { colorPrimaryText: '#000000', fontWeight: 700 },
        Table: { headerBg: '#0f172a', headerColor: '#F59E0B' },
      },
    }
  } else if (currentTheme.value === 'colorblind') {
    // TEMA ACCESIBLE
    return {
      algorithm: theme.defaultAlgorithm,
      token: {
        colorPrimary: '#0D9488',
        colorInfo: '#0072b2',
        colorSuccess: '#059669',
        colorWarning: '#d97706',
        colorError: '#dc2626',
        colorBgLayout: '#e5e7eb',
        borderRadius: 6,
        wireframe: true,
      },
    }
  } else {
    // TEMA CLARO
    return {
      algorithm: theme.defaultAlgorithm,
      token: {
        colorPrimary: '#0050b3',
        colorBgLayout: '#f0f2f5',
        borderRadius: 4,
      },
    }
  }
})

const setTheme = (key) => {
  currentTheme.value = key
  const names = {
    light: 'Profesional',
    dark: 'Industrial',
    modern: 'Futurista',
    control: 'Control Central',
    colorblind: 'Accesible',
  }
  message.info(`Tema: ${names[key]}`)
}

// --- 2. LÓGICA DE NEGOCIO (Intacta) ---
const router = useRouter()
const loading = ref(false)
const showSidePanel = ref(true)
const collapsed = ref(false)
const clientSelect = ref(null)

const clientes = ref([
  {
    value: 1,
    label: 'Supermercado El Sol S.A.',
    cuit: '30-11223344-5',
    saldo: -150000,
    estado: 'Deudor',
  },
  { value: 2, label: 'Kiosco La Esquina', cuit: '20-99887766-1', saldo: 0, estado: 'Al día' },
])
const tiposComprobante = ref([
  { value: 1, label: 'Factura A' },
  { value: 2, label: 'Factura B' },
])

const formState = reactive({
  clienteId: null,
  tipoComprobanteId: 1,
  fecha: dayjs(),
  puntoVenta: 1,
  depositoId: 1,
})

const items = ref([])
const selectedRowKey = ref(null)

const columns = [
  { title: '#', dataIndex: 'index', width: 50, align: 'center' },
  { title: 'Código', dataIndex: 'codigo', width: 140 },
  { title: 'Descripción', dataIndex: 'descripcion' },
  { title: 'Cant.', dataIndex: 'cantidad', width: 100 },
  { title: 'Precio', dataIndex: 'precio', width: 140, align: 'right' },
  { title: 'Desc %', dataIndex: 'descuento', width: 90, align: 'right' },
  { title: 'Subtotal', dataIndex: 'subtotal', width: 140, align: 'right' },
  { title: '', dataIndex: 'actions', width: 50, align: 'center' },
]

const createEmptyRow = () => ({
  key: Date.now(),
  articuloId: null,
  codigo: '',
  descripcion: '',
  cantidad: 1,
  precio: 0,
  descuento: 0,
  foto: 'https://via.placeholder.com/150',
})

onMounted(() => {
  items.value.push(createEmptyRow())
  if (clientSelect.value) clientSelect.value.focus()
})

const totales = computed(() => {
  const neto = items.value.reduce(
    (acc, item) => acc + item.cantidad * item.precio * (1 - item.descuento / 100),
    0,
  )
  const iva = neto * 0.21
  return { neto, iva, total: neto + iva }
})

// --- 3. ACCIONES (Intactas) ---
const goHome = () => {
  const hasData = items.value.length > 1 || (items.value[0] && items.value[0].codigo !== '')
  if (hasData) {
    Modal.confirm({
      title: '¿Salir sin guardar?',
      content: 'Se perderán los datos actuales.',
      okText: 'Salir',
      cancelText: 'Quedarse',
      onOk() {
        router.push('/')
      },
    })
  } else {
    router.push('/')
  }
}

const filterOption = (input, option) => option.label.toLowerCase().indexOf(input.toLowerCase()) >= 0

const handleCodigoEnter = (e, index) => {
  const val = e.target.value
  if (!val) return
  loading.value = true
  setTimeout(() => {
    const item = items.value[index]
    item.articuloId = 101
    item.descripcion = 'Pañales Pampers Premium Care G x 36'
    item.precio = 12500.5
    item.foto = 'https://m.media-amazon.com/images/I/61hJ+7q+VUL._AC_SX679_.jpg'
    selectedRowKey.value = item.key
    showSidePanel.value = true
    message.success('Artículo agregado')
    if (index === items.value.length - 1) items.value.push(createEmptyRow())
    loading.value = false
  }, 300)
}

const handleRowClick = (record) => {
  selectedRowKey.value = record.key
  showSidePanel.value = true
}
const removeItem = (index) => {
  items.value.splice(index, 1)
  selectedRowKey.value = null
}
const guardarComprobante = () => {
  loading.value = true
  setTimeout(() => {
    loading.value = false
    message.success('Guardado (ID: 10023)')
  }, 1000)
}
</script>

<template>
  <a-config-provider :theme="themeConfig">
    <a-layout class="venta-layout" :class="`theme-${currentTheme}`">
      <div class="venta-header">
        <div class="header-left">
          <a-button type="text" class="back-btn" @click="goHome">
            <template #icon><ArrowLeftOutlined /></template>
          </a-button>
          <h1 class="app-title">Nueva Venta</h1>
          <a-tag class="status-tag">BORRADOR</a-tag>
        </div>

        <div class="header-right">
          <a-dropdown placement="bottomRight">
            <a-button type="text" class="icon-btn">
              <template #icon><BgColorsOutlined /></template> Tema
            </a-button>
            <template #overlay>
              <a-menu>
                <a-menu-item @click="setTheme('light')">☀️ Profesional</a-menu-item>
                <a-menu-item @click="setTheme('dark')">🌑 Industrial</a-menu-item>
                <a-menu-item @click="setTheme('modern')">✨ Futurista (Cian)</a-menu-item>
                <a-menu-item @click="setTheme('control')">🌊 Control (Ocean)</a-menu-item>
                <a-menu-item @click="setTheme('colorblind')">👁️ Neutro</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>

          <div class="divider"></div>

          <div class="finance-widget">
            <div class="finance-details">
              <div class="finance-row">
                <span>Neto:</span>
                <strong
                  >$
                  {{ totales.neto.toLocaleString('es-AR', { minimumFractionDigits: 2 }) }}</strong
                >
              </div>
              <div class="finance-row">
                <span>IVA:</span>
                <strong
                  >$ {{ totales.iva.toLocaleString('es-AR', { minimumFractionDigits: 2 }) }}</strong
                >
              </div>
            </div>
            <div class="finance-total">
              <small>TOTAL</small>
              <div class="amount">
                $ {{ totales.total.toLocaleString('es-AR', { minimumFractionDigits: 2 }) }}
              </div>
            </div>
          </div>

          <div class="divider"></div>

          <div class="action-buttons">
            <a-button @click="goHome">Salir</a-button>
            <a-button type="primary" size="large" :loading="loading" @click="guardarComprobante">
              <template #icon><SaveOutlined /></template> Guardar (F9)
            </a-button>
          </div>
        </div>
      </div>

      <a-layout class="layout-body">
        <a-layout-content class="venta-content">
          <div class="form-section card-elevation">
            <a-row :gutter="16" align="middle">
              <a-col :xs="24" :sm="10" :lg="8">
                <label>Cliente (F2)</label>
                <a-select
                  ref="clientSelect"
                  v-model:value="formState.clienteId"
                  show-search
                  :options="clientes"
                  :filter-option="filterOption"
                  placeholder="Buscar..."
                  style="width: 100%"
                />
              </a-col>
              <a-col :xs="12" :sm="5" :lg="4">
                <label>Fecha</label>
                <a-date-picker
                  v-model:value="formState.fecha"
                  format="DD/MM/YYYY"
                  style="width: 100%"
                />
              </a-col>
              <a-col :xs="12" :sm="5" :lg="4">
                <label>Tipo</label>
                <a-select
                  v-model:value="formState.tipoComprobanteId"
                  :options="tiposComprobante"
                  style="width: 100%"
                />
              </a-col>
              <a-col :xs="24" :sm="4" :lg="4">
                <label>Depósito</label>
                <a-select value="Central" disabled style="width: 100%" />
              </a-col>
            </a-row>
          </div>

          <div class="grid-section card-elevation">
            <a-table
              :columns="columns"
              :data-source="items"
              :pagination="false"
              size="small"
              :scroll="{ y: 'calc(100vh - 360px)' }"
              row-class-name="item-row"
              :customRow="
                (record) => ({
                  onClick: () => handleRowClick(record),
                  class: record.key === selectedRowKey ? 'row-selected' : '',
                })
              "
            >
              <template #bodyCell="{ column, record, index }">
                <template v-if="column.dataIndex === 'index'"
                  ><span class="index-cell">{{ index + 1 }}</span></template
                >

                <template v-if="column.dataIndex === 'codigo'">
                  <a-input
                    v-model:value="record.codigo"
                    placeholder="Código"
                    @pressEnter="(e) => handleCodigoEnter(e, index)"
                    class="grid-input"
                    :bordered="false"
                  >
                    <template #prefix><BarcodeOutlined style="opacity: 0.5" /></template>
                  </a-input>
                </template>

                <template v-if="column.dataIndex === 'cantidad'">
                  <a-input-number
                    v-model:value="record.cantidad"
                    :min="0.1"
                    class="grid-input-number"
                    :bordered="false"
                    style="width: 100%"
                  />
                </template>

                <template v-if="column.dataIndex === 'precio'">
                  <a-input-number
                    v-model:value="record.precio"
                    :min="0"
                    :formatter="(v) => `$ ${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')"
                    :parser="(v) => v.replace(/\$\s?|(,*)/g, '')"
                    class="grid-input-number"
                    :bordered="false"
                    style="width: 100%"
                  />
                </template>

                <template v-if="column.dataIndex === 'subtotal'">
                  <span class="subtotal-text"
                    >$
                    {{
                      (record.cantidad * record.precio * (1 - record.descuento / 100)).toFixed(2)
                    }}</span
                  >
                </template>

                <template v-if="column.dataIndex === 'actions'">
                  <a-button type="text" danger size="small" @click.stop="removeItem(index)"
                    ><DeleteOutlined
                  /></a-button>
                </template>
              </template>
            </a-table>

            <div class="grid-footer">
              <a-button type="dashed" block @click="items.push(createEmptyRow())"
                ><PlusOutlined /> Agregar Línea (Insert)</a-button
              >
            </div>
          </div>
        </a-layout-content>

        <a-layout-sider
          v-if="showSidePanel"
          width="320"
          class="inspector-panel"
          collapsible
          v-model:collapsed="collapsed"
          trigger="null"
          :theme="currentTheme !== 'light' ? 'dark' : 'light'"
        >
          <div class="inspector-header">
            <h3>Información</h3>
            <a-button type="text" size="small" @click="showSidePanel = false">✕</a-button>
          </div>

          <div
            class="inspector-body"
            v-if="items.find((i) => i.key === selectedRowKey)?.articuloId"
          >
            <div class="product-card">
              <img :src="items.find((i) => i.key === selectedRowKey).foto" />
              <h4>{{ items.find((i) => i.key === selectedRowKey).descripcion }}</h4>
              <a-tag color="green">Stock: 150 UN</a-tag>
            </div>
            <div class="info-list">
              <div class="info-row"><span>Último precio:</span> <strong>$ 12,100.00</strong></div>
              <div class="info-row"><span>Fecha:</span> <span>15/10/2025</span></div>
              <div class="info-row"><span>Ubicación:</span> <span>Pasillo 4 - B</span></div>
            </div>
          </div>

          <div class="inspector-body" v-else-if="formState.clienteId">
            <div class="client-card">
              <UserOutlined class="avatar-large" />
              <h4>{{ clientes.find((c) => c.value === formState.clienteId)?.label }}</h4>
              <a-tag color="blue">Cliente Frecuente</a-tag>
            </div>
            <div class="info-list">
              <div class="info-row alert-text">
                <span>Saldo:</span> <strong>$ -150,000.00</strong>
              </div>
            </div>
          </div>

          <div class="inspector-empty" v-else>
            <InfoCircleOutlined class="empty-icon" />
            <p>Seleccione un ítem</p>
          </div>
        </a-layout-sider>
      </a-layout>
    </a-layout>
  </a-config-provider>
</template>

<style scoped>
/* LAYOUT */
.venta-layout {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--ant-color-bg-layout);
  transition: background 0.3s;
}

/* === ESTILOS TEMA CONTROL (OCEAN) === */
.theme-control.venta-layout {
  background: linear-gradient(135deg, #0f172a 0%, #0e3c45 100%);
}
.theme-control .venta-header {
  background: rgba(15, 23, 42, 0.85);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}
.theme-control .card-elevation {
  background: rgba(30, 41, 59, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(8px);
}
.theme-control .finance-total .amount {
  color: #f59e0b;
}
.theme-control .status-tag {
  background: #f59e0b;
  color: #000;
  border: none;
}
.theme-control .app-title {
  color: #fff;
}
.theme-control .inspector-panel {
  background: #111827;
  border-left: 1px solid #334155;
}

/* HEADER ESTÁNDAR */
.venta-header {
  height: 64px;
  padding: 0 24px;
  background: var(--ant-color-bg-container);
  border-bottom: 1px solid var(--ant-color-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
  z-index: 50;
}
/* Estilos Header por Tema */
.theme-light .venta-header {
  border-top: 3px solid var(--ant-color-primary);
}
.theme-dark .venta-header {
  background-color: #1f1f1f;
  border-bottom: 1px solid #333;
  border-top: none;
}
.theme-modern .venta-header {
  background-color: #181b21;
  border-bottom: 1px solid #2d333b;
}
.theme-colorblind .venta-header {
  border-top: 4px solid #0d9488;
}

.header-left,
.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.app-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--ant-color-text);
}

/* TAGS */
.status-tag {
  font-weight: 600;
}
.theme-dark .status-tag {
  background: #333;
  color: #facc15;
  border-color: #facc15;
}
.theme-modern .status-tag {
  background: #13151a;
  color: #06b6d4;
  border-color: #06b6d4;
}
.theme-colorblind .status-tag {
  background: #fff;
  color: #000;
  border: 2px solid #000;
}

.finance-widget {
  display: flex;
  align-items: center;
  gap: 16px;
  text-align: right;
}
.finance-details {
  display: flex;
  flex-direction: column;
  font-size: 11px;
  color: var(--ant-color-text-secondary);
}
.finance-total .amount {
  font-size: 20px;
  font-weight: 800;
  color: var(--ant-color-primary);
  line-height: 1;
}

/* Finance Colors */
.theme-dark .finance-total .amount {
  color: #facc15;
}
.theme-modern .finance-total .amount {
  color: #06b6d4;
}
.theme-colorblind .finance-total .amount {
  color: #000;
  text-decoration: underline;
}

.divider {
  width: 1px;
  height: 24px;
  background: var(--ant-color-border);
}
.back-btn {
  color: var(--ant-color-text-secondary);
  margin-right: 8px;
}
.back-btn:hover {
  color: var(--ant-color-primary);
  background: rgba(0, 0, 0, 0.05);
}

/* CONTENIDO */
.venta-content {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow: hidden;
}

/* CARDS */
.card-elevation {
  background: var(--ant-color-bg-container);
  border-radius: 6px;
  border: 1px solid var(--ant-color-border);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}
.theme-dark .card-elevation {
  border: 1px solid #333;
  background: #1f1f1f;
  box-shadow: none;
}
.theme-modern .card-elevation {
  border: 1px solid #2d333b;
  background: #1d2129;
  box-shadow: none;
}
.theme-colorblind .card-elevation {
  border: 2px solid #9ca3af;
  box-shadow: none;
}

.form-section {
  padding: 16px 24px 0 24px;
}
.grid-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
label {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  margin-bottom: 4px;
  display: block;
}

/* TABLA */
:deep(.ant-table-thead > tr > th) {
  background: var(--ant-color-bg-layout);
  font-weight: 600;
  border-bottom: 1px solid var(--ant-color-border);
}
.theme-dark :deep(.ant-table-thead > tr > th) {
  background: #262626;
  color: #facc15;
  border-bottom: 1px solid #333;
}
.theme-modern :deep(.ant-table-thead > tr > th) {
  background: #181b21;
  color: #06b6d4;
  border-bottom: 1px solid #2d333b;
}
.theme-control :deep(.ant-table-thead > tr > th) {
  background: rgba(15, 23, 42, 0.8);
  color: #f59e0b;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}
.theme-colorblind :deep(.ant-table-thead > tr > th) {
  background: #d1d5db;
  color: #000;
  border-bottom: 2px solid #000;
}

.grid-input,
.grid-input-number {
  width: 100%;
}
.theme-dark .grid-input,
.theme-dark .grid-input-number,
.theme-modern .grid-input,
.theme-modern .grid-input-number,
.theme-control .grid-input,
.theme-control .grid-input-number {
  background: transparent;
  color: white;
}

/* ROW SELECTION */
.row-selected {
  background-color: var(--ant-control-item-bg-active) !important;
}
.theme-dark .row-selected {
  background-color: #333 !important;
  border-left: 2px solid #facc15;
}
.theme-modern .row-selected {
  background-color: #2d333b !important;
  border-left: 2px solid #06b6d4;
}
.theme-control .row-selected {
  background-color: rgba(245, 158, 11, 0.15) !important;
  border-left: 3px solid #f59e0b;
}
.theme-colorblind .row-selected {
  background-color: #ffedd5 !important;
  color: #000 !important;
  border: 1px solid #000;
}

.grid-footer {
  padding: 10px;
  border-top: 1px solid var(--ant-color-border);
}

/* INSPECTOR */
.inspector-panel {
  border-left: 1px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
  z-index: 40;
}
.theme-dark .inspector-panel {
  border-left: 1px solid #333;
}
.theme-modern .inspector-panel {
  border-left: 1px solid #2d333b;
}
.theme-colorblind .inspector-panel {
  border-left: 2px solid #000;
}

.inspector-header {
  height: 48px;
  padding: 0 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--ant-color-border);
}
.inspector-body {
  padding: 20px;
}
.product-card,
.client-card {
  text-align: center;
  margin-bottom: 20px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--ant-color-border);
}
.product-card img {
  height: 120px;
  object-fit: contain;
  margin-bottom: 10px;
  border-radius: 4px;
  background: #fff;
  padding: 5px;
  border: 1px solid #eee;
}

.info-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.info-row {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
}
.info-row span:first-child {
  color: var(--ant-color-text-secondary);
}

.inspector-empty {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--ant-color-text-secondary);
}
.empty-icon {
  font-size: 40px;
  margin-bottom: 10px;
  opacity: 0.3;
}
.avatar-large {
  font-size: 48px;
  margin-bottom: 10px;
  color: var(--ant-color-primary);
}
.theme-dark .avatar-large {
  color: #facc15;
}
.theme-modern .avatar-large {
  color: #06b6d4;
}
.theme-control .avatar-large {
  color: #f59e0b;
}
.theme-colorblind .avatar-large {
  color: #000;
}

.alert-text {
  color: #ff4d4f;
  font-weight: bold;
}
.subtotal-text {
  font-weight: 600;
}
</style>
