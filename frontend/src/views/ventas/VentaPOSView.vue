<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import {
  SaveOutlined,
  PlusOutlined,
  DeleteOutlined,
  BarcodeOutlined,
  ArrowLeftOutlined,
  CalculatorOutlined,
  UserOutlined,
  InfoCircleOutlined,
  SettingOutlined,
  SkinOutlined,
  SearchOutlined,
  RollbackOutlined,
  CloseOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons-vue'
import dayjs from 'dayjs'
import { message, theme, Modal } from 'ant-design-vue'
import axios from 'axios'
import { useConfigStore } from '@/stores/config'
import { watch } from 'vue'

const configStore = useConfigStore()
const router = useRouter()

// --- 1. CONFIGURACIÓN VISUAL (Solo 2 Temas) ---
const themeConfig = computed(() => {
  const mode = configStore.currentTheme || 'light'
  const isDark = mode === 'dark'

  let algorithm = isDark ? theme.darkAlgorithm : theme.defaultAlgorithm
  let token = { borderRadius: 6, wireframe: false }

  if (isDark) {
    token.colorPrimary = '#3b82f6' // Azul brillante para contrastar con negro
    token.colorBgBase = '#0f172a' // Slate 900 (Fondo base oscuro)
  } else {
    token.colorPrimary = '#1e40af' // Azul corporativo fuerte
  }

  return { algorithm, token }
})

const cambiarTema = (t) => {
  configStore.setTheme(t)
  message.success(`Tema cambiado a: ${t === 'light' ? 'Profesional' : 'Oscuro'}`)
}

// --- 2. LÓGICA DE NEGOCIO ---
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
  { title: 'Cant.', dataIndex: 'cantidad', width: 80, align: 'center' },
  { title: 'Precio', dataIndex: 'precio', width: 120, align: 'right' },
  { title: 'Desc %', dataIndex: 'descuento', width: 70, align: 'right' },
  { title: 'Subtotal', dataIndex: 'subtotal', width: 120, align: 'right' },
  { title: '', dataIndex: 'actions', width: 40, align: 'center' },
]

// --- BÚSQUEDA DE CLIENTES ---
const buscarClientes = async (busqueda = '') => {
  if (!busqueda || busqueda.trim().length < 3) {
    clientes.value = []
    return
  }
  cargandoClientes.value = true
  try {
    const response = await axios.get(
      `http://tenant1.localhost:8000/api/clientes/?search=${busqueda}`,
    )
    const datos = response.data.results ? response.data.results : response.data
    clientes.value = datos.map((c) => ({
      value: c.entidad.id,
      label: c.entidad.razon_social,
      cuit: c.entidad.cuit,
      condicion: c.entidad.situacion_iva?.nombre || '',
      saldo: -150000.0,
    }))
  } catch (e) {
    console.error(e)
  } finally {
    cargandoClientes.value = false
  }
}

// --- BÚSQUEDA DE ARTÍCULOS ---
const productOptions = ref([])

const handleSearchFocus = () => {
  productOptions.value = []
}

const onSearchProduct = async (searchText) => {
  if (!searchText || searchText.length < 3) {
    productOptions.value = []
    return
  }
  try {
    const response = await axios.get(
      `http://tenant1.localhost:8000/api/articulos/?search=${searchText}`,
    )
    const resultados = response.data.results ? response.data.results : response.data
    productOptions.value = resultados.map((p) => ({
      value: p.cod_articulo,
      label: p.descripcion,
      fullData: p,
    }))
  } catch (e) {
    console.error(e)
  }
}

const onSelectProduct = (value, option, index) => {
  agregarProductoFila(option.fullData, index)
}

const handleProductEnter = async (e, index) => {
  const val = items.value[index].codigo
  if (!val) return
  if (items.value[index].articuloId === val) return // Ya seleccionado

  try {
    const response = await axios.get(`http://tenant1.localhost:8000/api/articulos/?search=${val}`)
    const resultados = response.data.results ? response.data.results : response.data

    const exactMatch = resultados.find((p) => p.cod_articulo === val || p.ean === val)

    if (exactMatch) {
      agregarProductoFila(exactMatch, index)
    } else if (resultados.length > 0) {
      if (resultados.length === 1) agregarProductoFila(resultados[0], index)
      else message.info('Múltiples coincidencias. Seleccione de la lista.')
    } else {
      message.warning('Producto no encontrado')
    }
  } catch (e) {
    console.error(e)
  }
}

const agregarProductoFila = (producto, index) => {
  const item = items.value[index]
  item.articuloId = producto.cod_articulo
  item.codigo = producto.cod_articulo
  item.descripcion = producto.descripcion

  let precioVal = 0
  if (producto.precio_venta) {
    if (typeof producto.precio_venta === 'object')
      precioVal = parseFloat(producto.precio_venta.amount)
    else precioVal = parseFloat(producto.precio_venta)
  }
  item.precio = isNaN(precioVal) ? 0 : precioVal

  item.foto = producto.foto
  item.stock = parseFloat(producto.stock_total) || 0
  item.ubicacion = producto.ubicacion || 'Sin ubicación' // Usando campo real

  selectedRowKey.value = item.key
  message.success('Agregado')

  productOptions.value = []

  if (index === items.value.length - 1) {
    items.value.push(createEmptyRow())
  }
}

const createEmptyRow = () => ({
  key: Date.now() + Math.random(),
  articuloId: null,
  codigo: '',
  descripcion: '',
  cantidad: 1,
  precio: 0,
  descuento: 0,
  foto: null,
  stock: 0,
  ubicacion: '',
})

// --- CALCULADORA ---
const showCalculator = ref(false)
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
  let res = 0
  const prev = calcPrevValue.value
  if (calcOperator.value === '+') res = prev + curr
  if (calcOperator.value === '-') res = prev - curr
  if (calcOperator.value === '*') res = prev * curr
  if (calcOperator.value === '/') res = prev / curr
  calcDisplay.value = String(parseFloat(res.toFixed(4)))
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
  if (calcDisplay.value.length <= 1) calcDisplay.value = '0'
  else calcDisplay.value = calcDisplay.value.slice(0, -1)
}

const handleKeyboard = (e) => {
  if (!showCalculator.value) return
  const key = e.key
  if (key >= '0' && key <= '9') appendCalc(Number(key))
  if (key === '.' || key === ',') appendCalc('.')
  if (key === '+') setOp('+')
  if (key === '-') setOp('-')
  if (key === '*') setOp('*')
  if (key === '/') setOp('/')
  if (key === 'Enter' || key === '=') calculate()
  if (key === 'Backspace') backspaceCalc()
  if (key === 'Escape') showCalculator.value = false
  if (key.toLowerCase() === 'c') clearCalc()
}

// --- IMPRESIÓN ---
const imprimirTicket = async (idComprobante) => {
  try {
    message.loading({ content: 'Generando PDF...', key: 'print' })
    const response = await axios.get(
      `http://tenant1.localhost:8000/api/comprobantes-venta/${idComprobante}/pdf/`,
      { responseType: 'blob' },
    )
    const pdfUrl = URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }))
    window.open(pdfUrl, '_blank')
    message.success({ content: 'Ticket abierto', key: 'print' })
  } catch (e) {
    console.error(e)
    message.error({ content: 'Error ticket', key: 'print' })
  }
}

// --- GUARDAR ---
const guardarComprobante = async () => {
  if (!formState.clienteId) {
    message.warning('Seleccione Cliente')
    return
  }
  const itemsValidos = items.value.filter((i) => i.articuloId)
  if (itemsValidos.length === 0) {
    message.warning('Agregue artículos')
    return
  }

  loading.value = true
  try {
    const payload = {
      cliente: formState.clienteId,
      tipo_comprobante: formState.tipoComprobanteId,
      fecha: formState.fecha.format('YYYY-MM-DD'),
      punto_venta: formState.puntoVenta,
      estado: 'CN',
      items: itemsValidos.map((item) => ({
        articulo: item.articuloId,
        cantidad: item.cantidad,
        precio_unitario_original: item.precio,
      })),
    }
    const response = await axios.post(
      'http://tenant1.localhost:8000/api/comprobantes-venta/',
      payload,
    )
    const nro = response.data.numero_completo
    const id = response.data.id

    Modal.confirm({
      title: 'Venta Exitosa',
      content: `Comprobante ${nro} generado.`,
      icon: null, // Icono default
      okText: 'Imprimir Ticket',
      cancelText: 'Nueva Venta',
      onOk() {
        imprimirTicket(id)
        limpiar()
      },
      onCancel() {
        limpiar()
      },
    })
  } catch (error) {
    const errorMsg = error.response?.data?.detail || 'Error al procesar'
    message.error(errorMsg)
  } finally {
    loading.value = false
  }
}

const limpiar = () => {
  items.value = [createEmptyRow()]
  formState.clienteId = null
  clientes.value = []
}

// --- CICLO DE VIDA ---
onMounted(() => {
  if (!configStore.currentTheme) configStore.setTheme('light')
  items.value = [createEmptyRow()]
  setTimeout(() => clientSelect.value?.focus(), 100)
  window.addEventListener('keydown', handleKeyboard)
})
onUnmounted(() => window.removeEventListener('keydown', handleKeyboard))

const getImageUrl = (path) => {
  if (!path) return 'https://via.placeholder.com/150?text=Sin+Imagen'

  // Si la URL ya empieza con http (viene de MinIO), la usamos tal cual
  if (path.startsWith('http')) return path

  // Solo si viene relativa (caso raro), le pegamos el dominio local
  return `http://tenant1.localhost:8000${path}`
}
// --- COMPUTADAS AUX ---
const clienteInfo = computed(() => {
  if (!formState.clienteId) return null
  return clientes.value.find((c) => c.value === formState.clienteId) || null
})
// --- AUTOMATIZACIÓN FISCAL AFIP ---
watch(clienteInfo, (nuevoCliente) => {
  if (nuevoCliente) {
    // Lógica de negocio: Determinación automática del comprobante
    const condicion = nuevoCliente.condicion.toLowerCase()

    // Si es Responsable Inscripto -> Factura A (ID 1)
    // Si es Consumidor Final / Monotributo / Exento -> Factura B (ID 2)
    // NOTA: Ajusta los IDs (1 y 2) según como los tengas en tu base de datos
    if (condicion.includes('inscripto')) {
      formState.tipoComprobanteId = 1
    } else {
      formState.tipoComprobanteId = 2
    }
  }
})
const itemInfo = computed(() => {
  if (!selectedRowKey.value) return null
  return items.value.find((i) => i.key === selectedRowKey.value) || null
})
const totales = computed(() => {
  const neto = items.value.reduce(
    (acc, item) => acc + item.cantidad * item.precio * (1 - item.descuento / 100),
    0,
  )
  const iva = neto * 0.21
  return { neto, iva, total: neto + iva }
})
const handleRowClick = (record) => {
  selectedRowKey.value = record.key
}
const removeItem = (index) => {
  if (items.value.length > 1) {
    if (items.value[index].key === selectedRowKey.value) selectedRowKey.value = null
    items.value.splice(index, 1)
  }
}
const goHome = () => router.push('/')
</script>

<template>
  <a-config-provider :theme="themeConfig">
    <div
      class="pos-container"
      :class="configStore.currentTheme === 'dark' ? 'theme-dark' : 'theme-light'"
    >
      <header class="pos-header">
        <div class="brand-area">
          <a-button type="text" class="header-btn" @click="goHome"><ArrowLeftOutlined /></a-button>

          <div class="logo-wrapper">
            <img v-if="configStore.logoUrl" :src="configStore.logoUrl" class="pos-logo" />
            <h2 v-else>{{ configStore.nombreFantasia }}</h2>
          </div>

          <a-tag class="status-tag">PUNTO DE VENTA</a-tag>
        </div>

        <div class="header-actions">
          <a-tooltip title="Calculadora (F12)">
            <a-button @click="showCalculator = true" shape="circle" size="large" class="action-btn">
              <template #icon><CalculatorOutlined /></template>
            </a-button>
          </a-tooltip>

          <a-dropdown placement="bottomRight" :trigger="['click']">
            <a-button shape="circle" size="large" class="action-btn">
              <template #icon><SettingOutlined /></template>
            </a-button>
            <template #overlay>
              <a-menu>
                <a-menu-item key="t-light" @click="cambiarTema('light')">
                  <CheckCircleOutlined
                    v-if="configStore.currentTheme !== 'dark'"
                    style="color: #1890ff"
                  />
                  ☀️ Profesional (Claro)
                </a-menu-item>
                <a-menu-item key="t-dark" @click="cambiarTema('dark')">
                  <CheckCircleOutlined
                    v-if="configStore.currentTheme === 'dark'"
                    style="color: #1890ff"
                  />
                  🌑 Nocturno (Oscuro)
                </a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>

          <div class="user-pill"><UserOutlined /> <span>Admin</span></div>
        </div>
      </header>

      <main class="pos-body">
        <section class="left-panel">
          <a-card class="form-card" :bordered="false" :bodyStyle="{ padding: '16px' }">
            <a-row :gutter="16" align="middle">
              <a-col :span="14">
                <a-select
                  ref="clientSelect"
                  v-model:value="formState.clienteId"
                  show-search
                  :options="clientes"
                  :loading="cargandoClientes"
                  :filter-option="false"
                  @search="buscarClientes"
                  placeholder="Buscar Cliente (min 3 letras)..."
                  style="width: 100%"
                  size="large"
                  class="custom-select"
                >
                  <template #option="{ label, cuit }">
                    <div class="client-option">
                      <span class="client-name">{{ label }}</span>
                      <span class="client-cuit">{{ cuit }}</span>
                    </div>
                  </template>
                </a-select>
              </a-col>
              <a-col :span="5">
                <a-select
                  v-model:value="formState.tipoComprobanteId"
                  :options="tiposComprobante"
                  style="width: 100%"
                  size="large"
                />
              </a-col>
              <a-col :span="5">
                <a-date-picker
                  v-model:value="formState.fecha"
                  style="width: 100%"
                  size="large"
                  format="DD/MM/YYYY"
                />
              </a-col>
            </a-row>
          </a-card>

          <a-card
            class="grid-card"
            :bordered="false"
            :bodyStyle="{ padding: 0, display: 'flex', flexDirection: 'column', height: '100%' }"
          >
            <a-table
              :columns="columns"
              :data-source="items"
              :pagination="false"
              size="middle"
              :scroll="{ y: 'flex' }"
              :customRow="
                (record) => ({
                  onClick: () => handleRowClick(record),
                  class: record.key === selectedRowKey ? 'row-selected' : '',
                })
              "
            >
              <template #bodyCell="{ column, record, index }">
                <template v-if="column.dataIndex === 'codigo'">
                  <a-auto-complete
                    v-model:value="record.codigo"
                    :options="productOptions"
                    @search="onSearchProduct"
                    @focus="handleSearchFocus"
                    @select="(val, opt) => onSelectProduct(val, opt, index)"
                    class="search-autocomplete"
                    :bordered="false"
                    style="width: 100%"
                    @keydown.enter="(e) => handleProductEnter(e, index)"
                    :backfill="true"
                    :defaultActiveFirstOption="false"
                  >
                    <a-input placeholder="🔍 Código, Nombre..." class="grid-search-input" />
                    <template #option="{ fullData }">
                      <div class="product-option-row">
                        <span class="prod-desc">{{ fullData.descripcion }}</span>
                        <div class="prod-meta">
                          <span class="prod-brand">{{ fullData.marca?.nombre || '-' }}</span>
                          <span class="prod-stock">{{ fullData.stock_total }} un.</span>
                        </div>
                      </div>
                    </template>
                  </a-auto-complete>
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
                    v-model:value="record.precio"
                    :bordered="false"
                    class="full-width right-align-input"
                    :formatter="(v) => `$ ${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')"
                    :parser="(v) => v.replace(/\$\s?|(,*)/g, '')"
                  />
                </template>
                <template v-if="column.dataIndex === 'subtotal'">
                  <span class="subtotal-val"
                    >$
                    {{
                      (record.cantidad * record.precio).toLocaleString('es-AR', {
                        minimumFractionDigits: 2,
                      })
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
            <div class="grid-actions">
              <a-button type="dashed" block size="large" @click="items.push(createEmptyRow())">
                <PlusOutlined /> Agregar Manualmente
              </a-button>
            </div>
          </a-card>
        </section>

        <section class="right-panel">
          <div class="context-area">
            <transition name="fade" mode="out-in">
              <div
                v-if="itemInfo && itemInfo.articuloId"
                class="info-card product-mode"
                key="product"
              >
                <div class="card-header"><InfoCircleOutlined /> Detalle Artículo</div>
                <div class="product-visual">
                  <img
                    :src="getImageUrl(itemInfo.foto)"
                    class="product-img"
                    alt="Foto del producto"
                  />
                  <div class="stock-badge">{{ itemInfo.stock }} UN</div>
                </div>
                <h3>{{ itemInfo.descripcion }}</h3>
                <div class="meta-row">
                  <span>Ubicación:</span> <strong>{{ itemInfo.ubicacion }}</strong>
                </div>
              </div>

              <div v-else-if="clienteInfo" class="info-card client-mode" key="client">
                <div class="card-header"><UserOutlined /> Info Cliente</div>
                <div class="client-avatar">{{ clienteInfo.label.charAt(0) }}</div>
                <h3>{{ clienteInfo.label }}</h3>
                <p class="cuit">{{ clienteInfo.cuit }}</p>
                <div class="meta-row alert">
                  <span>Saldo:</span> <strong>$ {{ clienteInfo.saldo?.toLocaleString() }}</strong>
                </div>
              </div>

              <div v-else class="info-card empty-mode" key="empty">
                <BarcodeOutlined style="font-size: 48px; opacity: 0.2" />
                <p>Seleccione un ítem para ver detalles</p>
              </div>
            </transition>
          </div>

          <div class="totals-widget">
            <div class="row">
              <span>Subtotal</span>
              <span
                >$ {{ totales.neto.toLocaleString('es-AR', { minimumFractionDigits: 2 }) }}</span
              >
            </div>
            <div class="row">
              <span>Impuestos</span>
              <span>$ {{ totales.iva.toLocaleString('es-AR', { minimumFractionDigits: 2 }) }}</span>
            </div>

            <div class="divider-line"></div>

            <div class="total-big">
              <small>A PAGAR</small>
              <div class="amount-display">
                $ {{ totales.total.toLocaleString('es-AR', { minimumFractionDigits: 2 }) }}
              </div>
            </div>

            <a-button
              type="primary"
              block
              size="large"
              class="pay-btn"
              :loading="loading"
              @click="guardarComprobante"
            >
              <SaveOutlined /> COBRAR
            </a-button>
          </div>
        </section>
      </main>

      <a-modal
        v-model:open="showCalculator"
        title="Calculadora"
        :footer="null"
        width="300px"
        centered
        :maskClosable="true"
      >
        <template #closeIcon><CloseOutlined /></template>
        <div class="calculator">
          <div class="calc-display">{{ calcDisplay }}</div>
          <div class="calc-grid">
            <button @click="clearCalc" class="btn-calc op">C</button>
            <button @click="backspaceCalc" class="btn-calc op"><RollbackOutlined /></button>
            <button @click="setOp('/')" class="btn-calc op">÷</button>
            <button @click="setOp('*')" class="btn-calc op">×</button>
            <button @click="appendCalc(7)" class="btn-calc">7</button>
            <button @click="appendCalc(8)" class="btn-calc">8</button>
            <button @click="appendCalc(9)" class="btn-calc">9</button>
            <button @click="setOp('-')" class="btn-calc op">-</button>
            <button @click="appendCalc(4)" class="btn-calc">4</button>
            <button @click="appendCalc(5)" class="btn-calc">5</button>
            <button @click="appendCalc(6)" class="btn-calc">6</button>
            <button @click="setOp('+')" class="btn-calc op">+</button>
            <button @click="appendCalc(1)" class="btn-calc">1</button>
            <button @click="appendCalc(2)" class="btn-calc">2</button>
            <button @click="appendCalc(3)" class="btn-calc">3</button>
            <button @click="calculate" class="btn-calc equal">=</button>
            <button @click="appendCalc(0)" class="btn-calc zero">0</button>
            <button @click="appendCalc('.')" class="btn-calc">.</button>
          </div>
          <small style="text-align: center; color: #888; display: block; margin-top: 10px"
            >Teclado numérico habilitado</small
          >
        </div>
      </a-modal>
    </div>
  </a-config-provider>
</template>

<style scoped>
/* =========================================================
   VARIABLES Y TEMAS (SOLO 2: Light y Dark con Degradados)
   ========================================================= */

/* TEMA LIGHT (Profesional) - Header Azul Degradado */
.theme-light {
  --bg-app: #f1f5f9; /* Gris muy claro */
  --bg-header-gradient: linear-gradient(
    135deg,
    #1e3a8a 0%,
    #3b82f6 100%
  ); /* Azul profundo a azul real */
  --text-header: #ffffff; /* Texto blanco sobre azul */
  --text-header-muted: rgba(255, 255, 255, 0.7);
  --bg-panel-right: #ffffff;
  --text-panel-right: #1e293b;
  --bg-totals: #1e293b; /* Widget Totales Oscuro */
  --text-totals: #ffffff;
  --color-primary: #2563eb;
  --dropdown-bg: #ffffff;
  --dropdown-text: #333333;
}

/* TEMA DARK (Nocturno) - Header Oscuro Degradado */
.theme-dark {
  --bg-app: #020617; /* Slate 950 */
  --bg-header-gradient: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); /* Slate oscuro */
  --text-header: #f8fafc;
  --text-header-muted: #94a3b8;
  --bg-panel-right: #1e293b;
  --text-panel-right: #f8fafc;
  --bg-totals: #0f172a; /* Aún más oscuro */
  --text-totals: #f8fafc;
  --color-primary: #3b82f6; /* Azul más brillante */
  --dropdown-bg: #1e293b;
  --dropdown-text: #f1f5f9;
}

/* =========================================================
   ESTILOS GENERALES
   ========================================================= */

.pos-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: var(--bg-app);
  font-family:
    'Inter',
    -apple-system,
    BlinkMacSystemFont,
    'Segoe UI',
    Roboto,
    sans-serif;
  transition:
    background 0.3s,
    color 0.3s;
}

/* --- HEADER --- */
.pos-header {
  background: var(--bg-header-gradient);
  height: 60px;
  padding: 0 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
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
}
.header-btn:hover {
  color: var(--text-header);
  background: rgba(255, 255, 255, 0.1);
}

.pos-logo {
  height: 32px;
  filter: brightness(0) invert(1);
} /* Logo blanco */
.brand-area h2 {
  color: var(--text-header);
  margin: 0;
  font-size: 1.25rem;
  font-weight: 700;
  letter-spacing: -0.5px;
}

.status-tag {
  background: rgba(255, 255, 255, 0.15);
  color: var(--text-header);
  border: 1px solid rgba(255, 255, 255, 0.3);
  font-weight: 600;
  border-radius: 4px;
}

.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.action-btn {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: var(--text-header);
  transition: all 0.2s;
}
.action-btn:hover {
  background: rgba(255, 255, 255, 0.2);
  color: white;
  transform: translateY(-1px);
}

.user-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(255, 255, 255, 0.1);
  padding: 6px 12px;
  border-radius: 20px;
  font-size: 0.9rem;
  font-weight: 500;
}

/* --- BODY LAYOUT --- */
.pos-body {
  flex: 1;
  display: flex;
  padding: 16px;
  gap: 16px;
  overflow: hidden;
}
.left-panel {
  flex: 7;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.right-panel {
  flex: 3;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 300px;
}

/* --- CARDS & GRID --- */
.form-card,
.grid-card {
  border-radius: 12px;
  box-shadow:
    0 4px 6px -1px rgba(0, 0, 0, 0.05),
    0 2px 4px -1px rgba(0, 0, 0, 0.03);
  border: none;
}

/* Dropdown Fix para Dark Mode */
:deep(.ant-select-dropdown) {
  background-color: var(--dropdown-bg) !important;
}
:deep(.ant-select-item) {
  color: var(--dropdown-text) !important;
}
:deep(.ant-select-item-option-active) {
  background-color: rgba(var(--color-primary), 0.15) !important;
}

/* Grid Actions */
.grid-actions {
  padding: 12px;
  border-top: 1px solid rgba(0, 0, 0, 0.05);
  background: rgba(0, 0, 0, 0.01);
}

/* --- PANEL DERECHO (INFO & TOTALES) --- */
.info-card {
  background: var(--bg-panel-right);
  color: var(--text-panel-right);
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  border: 1px solid rgba(0, 0, 0, 0.05);
  flex: 1;
}

.card-header {
  width: 100%;
  text-align: left;
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 1px;
  font-weight: 600;
  opacity: 0.6;
  border-bottom: 1px solid rgba(0, 0, 0, 0.1);
  padding-bottom: 8px;
  margin-bottom: 15px;
}

.product-visual {
  position: relative;
  margin-bottom: 15px;
}
.product-img {
  height: 140px;
  object-fit: contain;
  border-radius: 8px;
  background: white;
  padding: 5px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}
.stock-badge {
  position: absolute;
  bottom: -5px;
  right: -5px;
  background: #10b981;
  color: white;
  padding: 4px 8px;
  border-radius: 6px;
  font-weight: 700;
  font-size: 0.8rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

.info-card h3 {
  margin: 0;
  font-size: 1.1rem;
  color: inherit;
  font-weight: 700;
}
.meta-row {
  width: 100%;
  display: flex;
  justify-content: space-between;
  margin-top: 15px;
  padding-top: 10px;
  border-top: 1px dashed rgba(0, 0, 0, 0.1);
}

/* --- WIDGET TOTALES (Estilo Azul/Enterprise) --- */
.totals-widget {
  background: var(--bg-totals); /* Dark Blue / Slate */
  color: var(--text-totals);
  border-radius: 12px;
  padding: 24px;
  box-shadow:
    0 10px 15px -3px rgba(0, 0, 0, 0.1),
    0 4px 6px -2px rgba(0, 0, 0, 0.05);
}

.totals-widget .row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 0.95rem;
  opacity: 0.9;
}

.divider-line {
  height: 1px;
  background: rgba(255, 255, 255, 0.15);
  margin: 15px 0;
}

.total-big {
  text-align: right;
}
.total-big small {
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 1px;
  opacity: 0.7;
}
.amount-display {
  font-size: 2.5rem;
  font-weight: 800;
  line-height: 1.1;
  color: #60a5fa; /* Azul claro para resaltar sobre fondo oscuro */
}
/* En tema light, queremos que el numero resalte sobre el fondo oscuro del widget */
.theme-light .amount-display {
  color: #93c5fd;
}

.pay-btn {
  margin-top: 20px;
  background: #3b82f6 !important; /* Azul vibrante */
  border: none;
  font-weight: 700;
  color: white !important;
  height: 55px;
  font-size: 1.25rem;
  box-shadow: 0 4px 6px rgba(37, 99, 235, 0.3);
  transition: transform 0.1s;
}
.pay-btn:active {
  transform: scale(0.98);
}

/* --- CALCULADORA --- */
.calculator {
  padding: 15px;
  background: var(--bg-panel-right);
  border-radius: 8px;
}
.calc-display {
  background: rgba(0, 0, 0, 0.05);
  text-align: right;
  padding: 12px;
  font-size: 1.8rem;
  border-radius: 6px;
  margin-bottom: 12px;
  font-family: 'Courier New', monospace;
  font-weight: bold;
  color: inherit;
}
.calc-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}
.btn-calc {
  padding: 15px 0;
  border: 1px solid rgba(0, 0, 0, 0.1);
  background: white;
  border-radius: 6px;
  font-size: 1.2rem;
  cursor: pointer;
  color: #333;
  transition: background 0.2s;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}
.theme-dark .btn-calc {
  background: #334155;
  color: white;
  border: none;
}
.btn-calc:hover {
  filter: brightness(0.95);
}

.btn-calc.op {
  background: #e0f2fe;
  color: #0284c7;
  font-weight: bold;
} /* Azul suave */
.theme-dark .btn-calc.op {
  background: #1e293b;
  color: #38bdf8;
}

.btn-calc.equal {
  grid-row: span 3;
  background: #2563eb;
  color: white;
  border: none;
}
.btn-calc.zero {
  grid-column: span 2;
}

/* Utilidades */
.client-option {
  display: flex;
  justify-content: space-between;
  width: 100%;
}
.client-name {
  font-weight: 600;
}
.client-cuit {
  color: #999;
  font-size: 0.85rem;
}

:deep(.right-align-input input) {
  text-align: right !important;
}
:deep(.centered-input input) {
  text-align: center !important;
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
