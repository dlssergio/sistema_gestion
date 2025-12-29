<script setup>
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { message, theme, Modal } from 'ant-design-vue'
import dayjs from 'dayjs'
import { useConfigStore } from '@/stores/config' // Store para el tema
import {
  SaveOutlined,
  ArrowLeftOutlined,
  PlusOutlined,
  DeleteOutlined,
  ShopOutlined,
} from '@ant-design/icons-vue'

// --- 1. CONFIGURACIÓN DEL COMPONENTE Y PROPS ---
const props = defineProps({
  modo: {
    type: String,
    default: 'financiero', // 'financiero' (Factura) | 'logistico' (Remito)
  },
})

const router = useRouter()
const configStore = useConfigStore()
const loading = ref(false)

// --- 2. CONFIGURACIÓN VISUAL (Temas Ant Design - IGUAL AL POS) ---
const themeConfig = computed(() => {
  const mode = configStore.currentTheme || 'light'
  const isDark = mode === 'dark'

  let algorithm = isDark ? theme.darkAlgorithm : theme.defaultAlgorithm
  let token = {
    borderRadius: 6,
    wireframe: false,
    fontFamily: "'Inter', sans-serif",
  }

  if (isDark) {
    token.colorPrimary = '#3b82f6'
    token.colorBgBase = '#0f172a' // Slate 900
    token.colorBgContainer = '#1e293b' // Slate 800
    token.colorBorder = '#334155' // Slate 700
  } else {
    token.colorPrimary = '#1e40af'
  }

  return { algorithm, token }
})

// --- 3. ESTADO DEL FORMULARIO ---
const formState = reactive({
  proveedor: null,
  tipo_comprobante: null,
  punto_venta: 1,
  numero: '',
  fecha: dayjs(),
  estado: 'CN',
})

const items = ref([])
const proveedores = ref([])
const tiposComprobante = ref([])
const productOptions = ref([])

// --- 4. COLUMNAS DINÁMICAS SEGÚN MODO ---
const columns = computed(() => {
  const cols = [
    {
      title: 'Artículo (Búsqueda)',
      dataIndex: 'articulo',
      width: props.modo === 'logistico' ? '60%' : '40%',
    },
    { title: 'Cant.', dataIndex: 'cantidad', width: '15%', align: 'center' },
  ]

  // Solo si es financiero mostramos plata
  if (props.modo === 'financiero') {
    cols.push(
      { title: 'Costo Unit.', dataIndex: 'precio', width: '20%', align: 'right' },
      { title: 'Subtotal', dataIndex: 'subtotal', width: '20%', align: 'right' },
    )
  }

  cols.push({ title: '', dataIndex: 'actions', width: '5%', align: 'center' })
  return cols
})

// --- 5. CARGA DE DATOS ---
const fetchAuxiliares = async () => {
  try {
    const [provRes, tipoRes] = await Promise.allSettled([
      axios.get('http://tenant1.localhost:8000/api/proveedores/'),
      axios.get('http://tenant1.localhost:8000/api/tipos-comprobante/'),
    ])

    // Proveedores
    if (provRes.status === 'fulfilled') {
      const data = provRes.value.data.results || provRes.value.data
      proveedores.value = data.map((p) => {
        const entidad = p.entidad_data || p.entidad || {}
        return {
          value: p.id,
          label: entidad.razon_social || `Proveedor #${p.id}`,
          cuit: entidad.cuit || 'S/D',
          condicion: 'Resp. Inscripto',
        }
      })
    }

    // Tipos de Comprobante (Filtrado Inteligente)
    if (tipoRes.status === 'fulfilled') {
      const data = tipoRes.value.data.results || tipoRes.value.data

      tiposComprobante.value = data
        .filter((t) => {
          // Siempre debe ser de Compras ('C')
          if (t.clase !== 'C') return false

          // Si hay modo logístico (Remito), filtramos por nombre o lógica futura
          if (props.modo === 'logistico') {
            return t.nombre.toLowerCase().includes('remito')
          } else {
            // Modo financiero: Facturas, Notas Crédito, etc.
            return !t.nombre.toLowerCase().includes('remito')
          }
        })
        .map((t) => ({
          value: t.id,
          label: t.nombre,
          fullData: t,
        }))
    }
  } catch (e) {
    message.error('Error cargando datos auxiliares')
  }
}

// Auto-selección
watch(tiposComprobante, (newVal) => {
  if (newVal && newVal.length > 0 && !formState.tipo_comprobante) {
    formState.tipo_comprobante = newVal[0].value
  }
})

// --- 6. LÓGICA DE COMPORTAMIENTO ---
const tipoSeleccionado = computed(() => {
  if (!formState.tipo_comprobante) return null
  return tiposComprobante.value.find((t) => t.value === formState.tipo_comprobante)
})

const esNumeracionManual = computed(() => {
  if (!tipoSeleccionado.value) return true
  // Si la API devuelve numeracion_automatica=true, entonces NO es manual
  return !tipoSeleccionado.value.fullData.numeracion_automatica
})

watch(esNumeracionManual, (esManual) => {
  if (!esManual) {
    formState.numero = ''
  }
})

const filterProveedor = (input, option) => {
  return option.label.toLowerCase().includes(input.toLowerCase())
}

// --- 7. BÚSQUEDA Y GRILLA ---
const searchArticulos = async (txt) => {
  if (!txt || txt.length < 3) {
    productOptions.value = []
    return
  }
  try {
    const { data } = await axios.get(`http://tenant1.localhost:8000/api/articulos/?search=${txt}`)
    const list = data.results || data
    productOptions.value = list.map((a) => ({
      value: a.cod_articulo,
      label: a.descripcion,
      fullData: a,
    }))
  } catch (e) {
    console.error(e)
  }
}

const onSelectArticulo = (val, option, index) => {
  const item = items.value[index]
  const art = option.fullData
  if (art) {
    item.articuloId = art.id
    item.codigo = art.cod_articulo
    item.descripcion = art.descripcion
    let costo = 0
    if (art.precio_costo) {
      costo =
        typeof art.precio_costo === 'object'
          ? parseFloat(art.precio_costo.amount)
          : parseFloat(art.precio_costo)
    }
    item.precio_costo_unitario = isNaN(costo) ? 0 : costo
  }
}

const createEmptyRow = () => ({
  key: Date.now() + Math.random(),
  articuloId: null,
  codigo: '',
  descripcion: '',
  cantidad: 1,
  precio_costo_unitario: 0,
})

const addItem = () => items.value.push(createEmptyRow())
const removeItem = (index) => {
  if (items.value.length > 1) items.value.splice(index, 1)
  else message.warning('Debe haber al menos una línea')
}

const totalCompra = computed(() => {
  return items.value.reduce((acc, item) => acc + item.cantidad * item.precio_costo_unitario, 0)
})

const proveedorSeleccionado = computed(() => {
  if (!formState.proveedor) return null
  return proveedores.value.find((p) => p.value === formState.proveedor)
})

// --- 8. GUARDAR ---
const onFinish = async () => {
  if (!formState.proveedor) return message.warning('Falta seleccionar el Proveedor')
  if (!formState.tipo_comprobante) return message.warning('Falta seleccionar el Tipo')

  if (esNumeracionManual.value) {
    if (!formState.numero || formState.numero.toString().trim() === '') {
      return message.warning('Ingrese el Número del comprobante')
    }
  }

  const validItems = items.value.filter((i) => i.articuloId)
  if (validItems.length === 0) return message.warning('Ingrese al menos un artículo válido')

  loading.value = true
  try {
    let numeroEnvio = 0
    if (esNumeracionManual.value) {
      numeroEnvio = parseInt(formState.numero, 10)
      if (isNaN(numeroEnvio)) throw new Error('El número debe ser entero')
    }

    const payload = {
      ...formState,
      numero: numeroEnvio,
      fecha: formState.fecha.format('YYYY-MM-DD'),
      items: validItems.map((i) => ({
        articulo: i.articuloId,
        cantidad: i.cantidad,
        precio_costo_unitario: i.precio_costo_unitario,
      })),
    }

    await axios.post('http://tenant1.localhost:8000/api/comprobantes-compra/', payload)
    message.success('Comprobante registrado correctamente')

    items.value = [createEmptyRow()]
    formState.numero = ''
    formState.proveedor = null
  } catch (e) {
    console.error('Error:', e)
    const errorData = e.response?.data
    let errorMsg = 'Error al guardar'
    if (errorData) {
      if (typeof errorData === 'object') {
        errorMsg = Object.entries(errorData)
          .map(([k, v]) => `${k}: ${v}`)
          .join(' | ')
      } else {
        errorMsg = JSON.stringify(errorData)
      }
    } else if (e.message) {
      errorMsg = e.message
    }
    message.error(errorMsg)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  if (!configStore.currentTheme) configStore.setTheme('light')
  fetchAuxiliares()
  addItem()
})
</script>

<template>
  <a-config-provider :theme="themeConfig">
    <div
      class="pos-layout"
      :class="configStore.currentTheme === 'dark' ? 'theme-dark' : 'theme-light'"
    >
      <header class="pos-header">
        <div class="brand-area">
          <a-button type="text" class="header-btn" @click="router.back()">
            <ArrowLeftOutlined />
          </a-button>
          <h2>{{ props.modo === 'logistico' ? 'Nuevo Remito' : 'Nueva Compra' }}</h2>
          <a-tag class="status-tag">Gestión</a-tag>
        </div>
      </header>

      <a-spin :spinning="loading">
        <main class="pos-body">
          <section class="left-panel">
            <a-card class="form-card mb-3" :bordered="false">
              <a-row :gutter="16">
                <a-col :span="10">
                  <label class="field-label">Proveedor</label>
                  <a-select
                    v-model:value="formState.proveedor"
                    :options="proveedores"
                    show-search
                    placeholder="Buscar proveedor..."
                    :filter-option="filterProveedor"
                    class="full-width custom-select"
                    size="large"
                  >
                    <template #option="{ label, cuit }">
                      <div class="option-row">
                        <b>{{ label }}</b>
                        <span class="muted-text">CUIT: {{ cuit }}</span>
                      </div>
                    </template>
                  </a-select>
                </a-col>
                <a-col :span="5">
                  <label class="field-label">Tipo Comp.</label>
                  <a-select
                    v-model:value="formState.tipo_comprobante"
                    :options="tiposComprobante"
                    size="large"
                    class="full-width"
                  />
                </a-col>
                <a-col :span="3">
                  <label class="field-label">Pto. Venta</label>
                  <a-input-number
                    v-model:value="formState.punto_venta"
                    class="full-width"
                    size="large"
                  />
                </a-col>
                <a-col :span="3">
                  <label class="field-label">Número</label>
                  <a-input
                    v-model:value="formState.numero"
                    size="large"
                    :placeholder="esNumeracionManual ? 'Ej: 1234' : 'Automático'"
                    :disabled="!esNumeracionManual"
                  />
                </a-col>
                <a-col :span="3">
                  <label class="field-label">Fecha</label>
                  <a-date-picker
                    v-model:value="formState.fecha"
                    class="full-width"
                    format="DD/MM/YYYY"
                    size="large"
                  />
                </a-col>
              </a-row>
            </a-card>

            <a-card
              class="grid-card"
              :bordered="false"
              :bodyStyle="{ padding: 0, flex: 1, display: 'flex', flexDirection: 'column' }"
            >
              <a-table
                :columns="columns"
                :data-source="items"
                :pagination="false"
                rowKey="key"
                size="middle"
                :scroll="{ y: 400 }"
              >
                <template #bodyCell="{ column, record, index }">
                  <template v-if="column.dataIndex === 'articulo'">
                    <a-auto-complete
                      v-model:value="record.codigo"
                      :options="productOptions"
                      @search="searchArticulos"
                      @select="(val, opt) => onSelectArticulo(val, opt, index)"
                      class="full-width input-grid"
                      :bordered="false"
                      placeholder="🔍 Código o nombre..."
                    >
                      <template #option="{ fullData }">
                        <div class="prod-option">
                          <span class="prod-name">{{ fullData.descripcion }}</span>
                          <span class="prod-code">{{ fullData.cod_articulo }}</span>
                        </div>
                      </template>
                    </a-auto-complete>
                    <div v-if="record.descripcion" class="prod-desc-sub">
                      {{ record.descripcion }}
                    </div>
                  </template>

                  <template v-if="column.dataIndex === 'cantidad'">
                    <a-input-number
                      v-model:value="record.cantidad"
                      :min="0"
                      :bordered="false"
                      class="full-width centered-input"
                    />
                  </template>

                  <template v-if="column.dataIndex === 'precio'">
                    <a-input-number
                      v-model:value="record.precio_costo_unitario"
                      :min="0"
                      :bordered="false"
                      class="full-width right-align-input"
                      :formatter="(value) => `$ ${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')"
                      :parser="(value) => value.replace(/\$\s?|(,*)/g, '')"
                    />
                  </template>

                  <template v-if="column.dataIndex === 'subtotal'">
                    <span class="subtotal-text">
                      $
                      {{
                        (record.cantidad * record.precio_costo_unitario).toLocaleString('es-AR', {
                          minimumFractionDigits: 2,
                        })
                      }}
                    </span>
                  </template>

                  <template v-if="column.dataIndex === 'actions'">
                    <a-button type="text" danger size="small" @click="removeItem(index)">
                      <DeleteOutlined />
                    </a-button>
                  </template>
                </template>
              </a-table>

              <div class="grid-footer">
                <a-button type="dashed" block @click="addItem" size="large">
                  <PlusOutlined /> Agregar Ítem (F2)
                </a-button>
              </div>
            </a-card>
          </section>

          <section class="right-panel">
            <div class="info-card">
              <div class="card-header"><ShopOutlined /> Proveedor</div>
              <div v-if="proveedorSeleccionado" class="provider-details">
                <h3>{{ proveedorSeleccionado.label }}</h3>
                <p>CUIT: {{ proveedorSeleccionado.cuit }}</p>
                <a-tag color="blue">{{ proveedorSeleccionado.condicion }}</a-tag>
              </div>
              <div v-else class="empty-state">
                <ShopOutlined style="font-size: 30px; opacity: 0.3" />
                <p>Seleccione un proveedor</p>
              </div>
            </div>

            <div v-if="props.modo === 'financiero'" class="totals-widget">
              <div class="row">
                <span>Subtotal</span>
                <span
                  >$ {{ totalCompra.toLocaleString('es-AR', { minimumFractionDigits: 2 }) }}</span
                >
              </div>
              <div class="row text-muted">
                <span>Impuestos (Est.)</span>
                <span>$ 0,00</span>
              </div>
              <div class="divider"></div>
              <div class="total-big">
                <small>TOTAL COMPRA</small>
                <div class="amount">
                  $ {{ totalCompra.toLocaleString('es-AR', { minimumFractionDigits: 2 }) }}
                </div>
              </div>

              <a-button
                type="primary"
                block
                size="large"
                class="save-btn"
                @click="onFinish"
                :loading="loading"
              >
                <SaveOutlined /> GUARDAR COMPRA
              </a-button>
            </div>

            <div v-else class="mt-4">
              <a-button
                type="primary"
                block
                size="large"
                class="save-btn"
                @click="onFinish"
                :loading="loading"
              >
                <SaveOutlined /> GUARDAR REMITO
              </a-button>
            </div>
          </section>
        </main>
      </a-spin>
    </div>
  </a-config-provider>
</template>

<style scoped>
/* ESTILOS ENTERPRISE BLUE & DARK (Unificados con VentaPOS) */
.theme-light {
  --bg-app: #f1f5f9;
  --bg-header-gradient: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
  --text-header: #ffffff;
  --bg-card: #ffffff;
  --text-primary: #1e293b;
  --text-secondary: #64748b;
  --border-color: #e2e8f0;
  --bg-totals: #1e293b;
  --text-totals: #ffffff;
  --dropdown-bg: #ffffff;
  --dropdown-text: #333333;
  --table-header-bg: #f8fafc;
  --table-header-text: #475569;
  --row-hover: #f1f5f9;
}

.theme-dark {
  --bg-app: #020617;
  --bg-header-gradient: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  --text-header: #f8fafc;
  --bg-card: #1e293b;
  --text-primary: #f8fafc;
  --text-secondary: #94a3b8;
  --border-color: #334155;
  --bg-totals: #0f172a;
  --text-totals: #f8fafc;
  --dropdown-bg: #1e293b;
  --dropdown-text: #f1f5f9;
  --table-header-bg: #0f172a;
  --table-header-text: #cbd5e1;
  --row-hover: #334155;
}

.pos-layout {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: var(--bg-app);
  color: var(--text-primary);
  font-family: 'Inter', sans-serif;
  transition:
    background 0.3s,
    color 0.3s;
}

.pos-header {
  background: var(--bg-header-gradient);
  height: 60px;
  padding: 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  color: var(--text-header);
}

.brand-area {
  display: flex;
  align-items: center;
  gap: 12px;
}
.header-btn {
  color: var(--text-header);
  font-size: 1.2rem;
}
.brand-area h2 {
  margin: 0;
  color: var(--text-header);
  font-size: 1.25rem;
  font-weight: 700;
}
.status-tag {
  background: rgba(255, 255, 255, 0.15);
  color: var(--text-header);
  border: 1px solid rgba(255, 255, 255, 0.3);
  font-weight: 600;
}

.pos-body {
  flex: 1;
  display: flex;
  padding: 16px;
  gap: 16px;
  overflow: hidden;
}

.left-panel {
  flex: 3;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
}
.right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 300px;
}

/* Tarjetas */
.form-card,
.grid-card {
  border-radius: 12px;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
  background-color: var(--bg-card);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.field-label {
  display: block;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 4px;
}
.full-width {
  width: 100%;
}
.mb-3 {
  margin-bottom: 12px;
}
.mt-4 {
  margin-top: 16px;
}

/* Tabla */
:deep(.ant-table) {
  background: transparent;
  color: var(--text-primary);
}
:deep(.ant-table-thead > tr > th) {
  background: var(--table-header-bg) !important;
  color: var(--table-header-text) !important;
  border-bottom: 1px solid var(--border-color) !important;
  font-weight: 600;
}
:deep(.ant-table-tbody > tr > td) {
  border-bottom: 1px solid var(--border-color) !important;
  transition: background 0.2s;
}
:deep(.ant-table-tbody > tr:hover > td) {
  background: var(--row-hover) !important;
}
:deep(.ant-empty-description) {
  color: var(--text-secondary);
}

.prod-desc-sub {
  font-size: 0.75rem;
  color: var(--text-secondary);
  margin-top: -5px;
}
.subtotal-text {
  font-weight: 700;
  color: var(--text-primary);
}

:deep(.centered-input input) {
  text-align: center !important;
  color: var(--text-primary) !important;
}
:deep(.right-align-input input) {
  text-align: right !important;
  color: var(--text-primary) !important;
}

/* Fixes Inputs Dark Mode */
.theme-dark :deep(.ant-input),
.theme-dark :deep(.ant-input-number-input),
.theme-dark :deep(.ant-select-selector),
.theme-dark :deep(.ant-picker) {
  background-color: transparent !important;
  color: var(--text-primary) !important;
  border-color: var(--border-color) !important;
}

/* Panel Derecho */
.info-card {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  border: 1px solid var(--border-color);
}
.card-header {
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 1px;
  font-weight: 700;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 10px;
  margin-bottom: 15px;
}
.provider-details h3 {
  margin: 0;
  font-size: 1.1rem;
  color: var(--text-primary);
}
.empty-state {
  text-align: center;
  color: var(--text-secondary);
  padding: 20px;
}

/* Totales Widget */
.totals-widget {
  background: var(--bg-totals);
  color: var(--text-totals);
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
  margin-top: auto;
}
.totals-widget .row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 0.95rem;
}
.text-muted {
  opacity: 0.6;
}
.divider {
  height: 1px;
  background: rgba(255, 255, 255, 0.1);
  margin: 15px 0;
}
.total-big {
  text-align: right;
  margin-bottom: 20px;
}
.total-big small {
  font-size: 0.8rem;
  text-transform: uppercase;
  opacity: 0.7;
}
.total-big .amount {
  font-size: 2rem;
  font-weight: 800;
  color: #60a5fa;
  line-height: 1.1;
}
.theme-light .amount-display {
  color: #93c5fd;
}

.save-btn {
  background: #3b82f6;
  border: none;
  font-weight: 700;
  height: 50px;
  font-size: 1.1rem;
  box-shadow: 0 4px 6px rgba(59, 130, 246, 0.4);
}
.save-btn:hover {
  background: #2563eb;
}

:deep(.ant-select-dropdown) {
  background-color: var(--bg-card) !important;
}
:deep(.ant-select-item) {
  color: var(--text-primary) !important;
}
:deep(.ant-select-item-option-active) {
  background-color: rgba(59, 130, 246, 0.2) !important;
}

/* Autocomplete */
.prod-option {
  display: flex;
  justify-content: space-between;
}
.prod-name {
  font-weight: 600;
  color: var(--text-primary);
}
.prod-code {
  color: var(--text-secondary);
  font-size: 0.8rem;
}
.option-row {
  display: flex;
  justify-content: space-between;
  width: 100%;
  color: var(--text-primary);
}
.muted-text {
  color: var(--text-secondary);
  font-size: 0.8rem;
}
</style>
