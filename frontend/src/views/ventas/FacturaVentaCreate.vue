<script setup>
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { message, theme, Modal } from 'ant-design-vue'
import dayjs from 'dayjs'
import { useConfigStore } from '@/stores/config'
import {
  SaveOutlined,
  ArrowLeftOutlined,
  PlusOutlined,
  DeleteOutlined,
  UserOutlined,
  FileTextOutlined,
  SearchOutlined,
  DollarOutlined,
  InfoCircleOutlined,
  BarcodeOutlined,
  NumberOutlined,
} from '@ant-design/icons-vue'

const router = useRouter()
const configStore = useConfigStore()
const loading = ref(false)

// --- 1. CONFIGURACIÓN VISUAL (IGUAL A POS) ---
const themeConfig = computed(() => {
  const mode = configStore.currentTheme || 'light'
  const isDark = mode === 'dark'
  let algorithm = isDark ? theme.darkAlgorithm : theme.defaultAlgorithm
  let token = { borderRadius: 6, wireframe: false, fontFamily: "'Inter', sans-serif" }

  if (isDark) {
    token.colorPrimary = '#3b82f6'
    token.colorBgBase = '#0f172a'
  } else {
    token.colorPrimary = '#1e40af'
  }
  return { algorithm, token }
})

// --- 2. ESTADO ---
const formState = reactive({
  tipo_comprobante: null,
  punto_venta: 1,
  numero: '',
  fecha: dayjs(),
  fecha_vencimiento: dayjs().add(30, 'day'),
  cliente: null,
  vendedor: null,
  condicion_venta: 'contado',
  descuento_global: 0,
  observaciones: '',
})

const pagos = ref([{ metodo: 'EFECTIVO', monto: 0 }])
const items = ref([])
const clientes = ref([])
const vendedores = ref([])
const tiposComprobante = ref([])
const productOptions = ref([])
const selectedRowKey = ref(null)

const columns = ref([
  { title: 'Artículo / Descripción', dataIndex: 'articulo', width: '40%', align: 'left' },
  { title: 'Cant.', dataIndex: 'cantidad', width: '10%', align: 'center' },
  { title: 'Precio', dataIndex: 'precio', width: '15%', align: 'right' },
  { title: '% Desc.', dataIndex: 'descuento', width: '10%', align: 'center' },
  { title: 'Subtotal', dataIndex: 'subtotal', width: '20%', align: 'right' },
  { title: '', dataIndex: 'actions', width: '5%', align: 'center' },
])

// --- 3. CARGA DATOS ---
const fetchAuxiliares = async () => {
  try {
    const [tipoRes, userRes] = await Promise.allSettled([
      axios.get('http://tenant1.localhost:8000/api/tipos-comprobante/'),
      axios.get('http://tenant1.localhost:8000/api/usuarios/'),
    ])

    if (tipoRes.status === 'fulfilled') {
      const data = tipoRes.value.data.results || tipoRes.value.data
      tiposComprobante.value = data
        .filter(
          (t) =>
            t.clase === 'V' &&
            !t.nombre.toLowerCase().includes('remito') &&
            !t.nombre.toLowerCase().includes('presupuesto'),
        )
        .map((t) => ({ value: t.id, label: t.nombre, fullData: t }))
      if (tiposComprobante.value.length > 0)
        formState.tipo_comprobante = tiposComprobante.value[0].value
    }

    if (userRes.status === 'fulfilled') {
      const users = userRes.value.data.results || userRes.value.data
      vendedores.value = users.map((u) => ({ value: u.id, label: u.username }))
    }
  } catch (e) {
    console.error(e)
  }
}

// --- 4. BÚSQUEDA CLIENTES (LÓGICA CORREGIDA IDÉNTICA A POS) ---
const searchClientes = async (txt) => {
  if (!txt || txt.length < 3) {
    clientes.value = []
    return
  }
  try {
    const { data } = await axios.get(`http://tenant1.localhost:8000/api/clientes/?search=${txt}`)
    const lista = data.results || data

    // ESTO ES LO QUE ESTABA FALLANDO: El mapeo debe ser igual al POS
    clientes.value = lista.map((c) => ({
      value: c.entidad.id,
      label: c.entidad.razon_social, // Nombre correcto
      cuit: c.entidad.cuit,
      // Accedemos correctamente al nombre de la situación IVA
      condicion: c.entidad.situacion_iva?.nombre || 'Consumidor Final',
      saldo: -150000.0, // Mockup (igual que POS)
      // Lógica para detectar si es Responsable Inscripto (Cta Cte) o Final
      es_cta_cte: !c.entidad.situacion_iva?.nombre?.toLowerCase().includes('final'),
    }))
  } catch (e) {
    console.error('Error clientes', e)
  }
}

const clienteSeleccionado = computed(() =>
  !formState.cliente ? null : clientes.value.find((c) => c.value === formState.cliente),
)

// Automatización Condición de Venta
watch(clienteSeleccionado, (val) => {
  if (val) {
    formState.condicion_venta = val.es_cta_cte ? 'cta_cte' : 'contado'
  }
})

watch(
  () => formState.condicion_venta,
  (val) => {
    if (val === 'contado') {
      formState.fecha_vencimiento = dayjs()
    } else {
      formState.fecha_vencimiento = dayjs().add(30, 'day')
    }
  },
)

// --- LÓGICA COMPROBANTE ---
const tipoSeleccionado = computed(() =>
  !formState.tipo_comprobante
    ? null
    : tiposComprobante.value.find((t) => t.value === formState.tipo_comprobante),
)
const esNumeracionManual = computed(() =>
  tipoSeleccionado.value ? !tipoSeleccionado.value.fullData.numeracion_automatica : true,
)
watch(esNumeracionManual, (esManual) => {
  if (!esManual) formState.numero = ''
})

// --- ARTÍCULOS ---
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
    item.key = Math.random()
    item.articuloId = art.cod_articulo
    item.codigo = art.cod_articulo
    item.descripcion = art.descripcion
    // Datos visuales para panel derecho (IGUAL QUE POS)
    item.foto = art.foto
    item.stock = parseFloat(art.stock_total || 0)
    item.ubicacion = art.ubicacion || 'General'

    let precio = 0
    if (art.precio_venta) {
      precio =
        typeof art.precio_venta === 'object'
          ? parseFloat(art.precio_venta.amount)
          : parseFloat(art.precio_venta)
    }
    item.precio = isNaN(precio) ? 0 : precio

    selectedRowKey.value = item.key
  }
}

const handleRowClick = (record) => {
  selectedRowKey.value = record.key
}

const itemInfo = computed(() => {
  if (!selectedRowKey.value) return null
  return items.value.find((i) => i.key === selectedRowKey.value) || null
})

const getImageUrl = (path) => {
  if (!path) return 'https://via.placeholder.com/150?text=Sin+Imagen'
  if (path.startsWith('http')) return path
  return `http://tenant1.localhost:8000${path}`
}

const createEmptyRow = () => ({
  key: Date.now(),
  articuloId: null,
  codigo: '',
  descripcion: '',
  cantidad: 1,
  precio: 0,
  descuento: 0,
})
const addItem = () => items.value.push(createEmptyRow())
const removeItem = (index) => {
  if (items.value.length > 1) items.value.splice(index, 1)
  else message.warning('Mínimo 1 línea')
}

// --- CÁLCULOS (CON IMPUESTOS) ---
const subtotalNeto = computed(() => {
  return items.value.reduce((acc, item) => {
    const bruto = item.cantidad * item.precio
    const factor = 1 - (item.descuento || 0) / 100
    return acc + bruto * factor
  }, 0)
})

// Cálculo de impuestos (21%) para que no de cero
const impuestos = computed(() => subtotalNeto.value * 0.21)

// Total Final
const totalVenta = computed(() => {
  const baseMasIva = subtotalNeto.value + impuestos.value
  return baseMasIva * (1 - (formState.descuento_global || 0) / 100)
})

// Tesorería
const totalPagos = computed(() =>
  pagos.value.reduce((acc, p) => acc + (parseFloat(p.monto) || 0), 0),
)
const saldoRestante = computed(() => Math.max(0, totalVenta.value - totalPagos.value))

const agregarPago = () => pagos.value.push({ metodo: 'EFECTIVO', monto: saldoRestante.value })
const quitarPago = (index) => pagos.value.splice(index, 1)

watch(totalVenta, (newTotal) => {
  if (formState.condicion_venta === 'contado' && pagos.value.length === 1) {
    pagos.value[0].monto = newTotal
  }
})

// --- GUARDAR ---
const onFinish = async () => {
  if (!formState.cliente) return message.warning('Falta el Cliente')
  // ... validaciones ...

  loading.value = true
  try {
    const payload = {
      cliente: formState.cliente,
      tipo_comprobante: formState.tipo_comprobante,
      punto_venta: formState.punto_venta,
      numero: esNumeracionManual.value ? parseInt(formState.numero) : 0,
      fecha: formState.fecha.format('YYYY-MM-DD'),
      fecha_vencimiento: formState.fecha_vencimiento.format('YYYY-MM-DD'),
      vendedor_id: formState.vendedor,
      observaciones: formState.observaciones,
      descuento_global: formState.descuento_global,
      items: validItems.map((i) => ({
        articulo: i.articuloId,
        cantidad: i.cantidad,
        precio_unitario_original: i.precio,
        descuento_porcentaje: i.descuento,
      })),
      pagos: formState.condicion_venta === 'contado' ? pagos.value : [],
    }

    await axios.post('http://tenant1.localhost:8000/api/comprobantes-venta/', payload)

    Modal.success({
      title: 'Factura Guardada',
      content: 'Operación registrada correctamente.',
      onOk: () => {
        items.value = [createEmptyRow()]
        formState.cliente = null
        formState.observaciones = ''
        formState.descuento_global = 0
        pagos.value = [{ metodo: 'EFECTIVO', monto: 0 }]
      },
    })
  } catch (e) {
    message.error('Error al guardar')
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
          <a-button type="text" class="header-btn" @click="router.back()"
            ><ArrowLeftOutlined
          /></a-button>

          <div class="logo-wrapper">
            <img v-if="configStore.logoUrl" :src="configStore.logoUrl" class="pos-logo" />
            <h2 v-else>Factura Administrativa</h2>
          </div>

          <a-tag class="status-tag">ADMINISTRACIÓN</a-tag>
        </div>
        <div class="user-pill"><UserOutlined /> <span>Admin</span></div>
      </header>

      <a-spin :spinning="loading">
        <main class="pos-body">
          <section class="left-panel">
            <a-card class="form-card mb-3" :bordered="false">
              <div class="row-fiscal">
                <div class="field-group" style="flex: 2">
                  <label>Tipo Comprobante</label>
                  <a-select
                    v-model:value="formState.tipo_comprobante"
                    :options="tiposComprobante"
                    class="full-width"
                  />
                </div>
                <div class="field-group" style="flex: 1">
                  <label>Pto. Venta</label>
                  <a-input-number v-model:value="formState.punto_venta" class="full-width" />
                </div>
                <div class="field-group" style="flex: 1">
                  <label>Número</label>
                  <a-input
                    v-model:value="formState.numero"
                    :disabled="!esNumeracionManual"
                    placeholder="Auto"
                  >
                    <template #prefix><NumberOutlined /></template>
                  </a-input>
                </div>
                <div class="field-group" style="flex: 1.5">
                  <label>Emisión</label>
                  <a-date-picker
                    v-model:value="formState.fecha"
                    class="full-width"
                    format="DD/MM/YYYY"
                  />
                </div>
                <div class="field-group" style="flex: 1.5">
                  <label>Vencimiento</label>
                  <a-date-picker
                    v-model:value="formState.fecha_vencimiento"
                    class="full-width"
                    format="DD/MM/YYYY"
                  />
                </div>
              </div>

              <a-divider style="margin: 12px 0" />

              <a-row :gutter="12" align="bottom">
                <a-col :span="14">
                  <label class="field-label">Cliente</label>
                  <a-select
                    v-model:value="formState.cliente"
                    :options="clientes"
                    show-search
                    placeholder="Buscar Cliente (min. 3 letras)..."
                    :filter-option="false"
                    @search="searchClientes"
                    class="full-width client-search-input"
                    size="large"
                    :dropdownMatchSelectWidth="500"
                  >
                    <template #suffixIcon><SearchOutlined class="search-icon" /></template>
                    <template #option="{ label, cuit, condicion }">
                      <div class="client-option-row">
                        <div class="main-info">
                          <span class="client-name">{{ label }}</span
                          ><span class="client-cuit">{{ cuit }}</span>
                        </div>
                        <a-tag>{{ condicion }}</a-tag>
                      </div>
                    </template>
                  </a-select>
                </a-col>
                <a-col :span="5">
                  <label class="field-label">Vendedor</label>
                  <a-select
                    v-model:value="formState.vendedor"
                    :options="vendedores"
                    placeholder="Seleccione..."
                    class="full-width"
                    size="large"
                  >
                    <template #suffixIcon><UserOutlined /></template>
                  </a-select>
                </a-col>
                <a-col :span="5">
                  <label class="field-label">Condición</label>
                  <a-select
                    v-model:value="formState.condicion_venta"
                    class="full-width"
                    size="large"
                  >
                    <a-select-option value="contado">Contado</a-select-option>
                    <a-select-option value="cta_cte">Cta. Corriente</a-select-option>
                  </a-select>
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
                :scroll="{ y: 350 }"
                :customRow="
                  (record) => ({
                    onClick: () => handleRowClick(record),
                    class: record.key === selectedRowKey ? 'row-selected' : '',
                  })
                "
              >
                <template #bodyCell="{ column, record, index }">
                  <template v-if="column.dataIndex === 'articulo'">
                    <a-auto-complete
                      v-model:value="record.codigo"
                      :options="productOptions"
                      @search="searchArticulos"
                      @select="(val, opt) => onSelectArticulo(val, opt, index)"
                      class="full-width search-autocomplete"
                      :bordered="false"
                      placeholder="🔍 Buscar..."
                    >
                      <template #option="{ fullData }">
                        <div class="product-option-row">
                          <span class="prod-desc">{{ fullData.descripcion }}</span>
                          <div class="prod-meta">
                            <span class="prod-brand">{{ fullData.marca?.nombre || '-' }}</span
                            ><span class="prod-stock">{{ fullData.stock_total }} un.</span>
                          </div>
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
                      v-model:value="record.precio"
                      :min="0"
                      :bordered="false"
                      class="full-width right-align-input"
                      :formatter="(v) => `$ ${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')"
                      :parser="(v) => v.replace(/\$\s?|(,*)/g, '')"
                    />
                  </template>

                  <template v-if="column.dataIndex === 'descuento'">
                    <a-input-number
                      v-model:value="record.descuento"
                      :bordered="false"
                      class="full-width centered-input"
                      :formatter="(value) => `${value}%`"
                      :parser="(value) => value.replace('%', '')"
                    />
                  </template>

                  <template v-if="column.dataIndex === 'subtotal'">
                    <span class="subtotal-val"
                      >$
                      {{
                        (
                          record.cantidad *
                          record.precio *
                          (1 - (record.descuento || 0) / 100)
                        ).toLocaleString('es-AR', { minimumFractionDigits: 2 })
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
                <a-button type="dashed" block @click="addItem" size="large"
                  ><PlusOutlined /> Agregar (F2)</a-button
                >
              </div>
            </a-card>

            <a-card class="form-card mt-3" :bordered="false">
              <label class="field-label"><FileTextOutlined /> Observaciones</label>
              <a-textarea
                v-model:value="formState.observaciones"
                placeholder="Notas internas o para impresión..."
                :rows="2"
              />
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
                    <img :src="getImageUrl(itemInfo.foto)" class="product-img" />
                    <div class="stock-badge">{{ itemInfo.stock }} UN</div>
                  </div>
                  <h3>{{ itemInfo.descripcion }}</h3>
                  <div class="meta-row">
                    <span>Ubicación:</span> <strong>{{ itemInfo.ubicacion }}</strong>
                  </div>
                </div>

                <div v-else-if="clienteSeleccionado" class="info-card client-mode" key="client">
                  <div class="card-header"><UserOutlined /> Info Cliente</div>
                  <div class="client-avatar">{{ clienteSeleccionado.label.charAt(0) }}</div>
                  <h3>{{ clienteSeleccionado.label }}</h3>
                  <p class="cuit">{{ clienteSeleccionado.cuit }}</p>
                  <div class="meta-row">
                    <span>Condición:</span>
                    <a-tag color="blue">{{ clienteSeleccionado.condicion }}</a-tag>
                  </div>
                  <div class="meta-row alert">
                    <span>Saldo:</span>
                    <strong>$ {{ clienteSeleccionado.saldo?.toLocaleString() }}</strong>
                  </div>
                </div>

                <div v-else class="info-card empty-mode" key="empty">
                  <BarcodeOutlined style="font-size: 48px; opacity: 0.2" />
                  <p>Seleccione un ítem para ver detalles</p>
                </div>
              </transition>
            </div>

            <div v-if="formState.condicion_venta === 'contado'" class="info-card mt-3 payment-card">
              <div class="card-header"><DollarOutlined /> Pagos</div>
              <div class="payment-list">
                <div v-for="(pago, idx) in pagos" :key="idx" class="payment-row">
                  <a-select v-model:value="pago.metodo" style="width: 90px" size="small">
                    <a-select-option value="EFECTIVO">Efectivo</a-select-option>
                    <a-select-option value="TARJETA">Tarjeta</a-select-option>
                    <a-select-option value="CHEQUE">Cheque</a-select-option>
                  </a-select>
                  <a-input-number
                    v-model:value="pago.monto"
                    style="flex: 1"
                    size="small"
                    :formatter="(v) => `$ ${v}`"
                    :parser="(v) => v.replace(/\$\s?|(,*)/g, '')"
                  />
                  <a-button
                    v-if="pagos.length > 1"
                    type="text"
                    danger
                    size="small"
                    @click="quitarPago(idx)"
                    ><DeleteOutlined
                  /></a-button>
                </div>
                <a-button type="dashed" block size="small" @click="agregarPago" class="mt-2"
                  ><PlusOutlined /> Agregar Medio</a-button
                >
              </div>
              <div class="payment-summary">
                <span>Falta:</span
                ><strong :class="saldoRestante > 0 ? 'text-red' : 'text-green'"
                  >$
                  {{ saldoRestante.toLocaleString('es-AR', { minimumFractionDigits: 2 }) }}</strong
                >
              </div>
            </div>

            <div class="totals-widget">
              <div class="row align-center mb-3">
                <span>% Desc. Global</span>
                <a-input-number
                  v-model:value="formState.descuento_global"
                  :min="0"
                  :max="100"
                  size="small"
                  style="width: 70px"
                  :formatter="(value) => `${value}%`"
                  :parser="(value) => value.replace('%', '')"
                />
              </div>

              <div class="row">
                <span>Subtotal Neto</span
                ><span
                  >$ {{ subtotalNeto.toLocaleString('es-AR', { minimumFractionDigits: 2 }) }}</span
                >
              </div>
              <div class="row">
                <span>Impuestos (21%)</span
                ><span
                  >$ {{ impuestos.toLocaleString('es-AR', { minimumFractionDigits: 2 }) }}</span
                >
              </div>
              <div class="divider-line"></div>

              <div class="total-big">
                <small>TOTAL FINAL</small>
                <div class="amount-display">
                  $ {{ totalVenta.toLocaleString('es-AR', { minimumFractionDigits: 2 }) }}
                </div>
              </div>

              <a-button
                type="primary"
                block
                size="large"
                class="pay-btn"
                @click="onFinish"
                :loading="loading"
              >
                <SaveOutlined /> GUARDAR
                {{ formState.condicion_venta === 'contado' ? 'Y COBRAR' : 'EN CTA. CTE.' }}
              </a-button>
            </div>
          </section>
        </main>
      </a-spin>
    </div>
  </a-config-provider>
</template>

<style scoped>
/* ESTILOS EXACTOS DE POS (Reutilizados) */
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
  --bg-panel-right: #ffffff;
  --text-panel-right: #1e293b;
  --dropdown-bg: #ffffff;
  --dropdown-text: #333333;
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
  --bg-panel-right: #1e293b;
  --text-panel-right: #f8fafc;
  --dropdown-bg: #1e293b;
  --dropdown-text: #f1f5f9;
}

.pos-layout {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: var(--bg-app);
  color: var(--text-primary);
  font-family: 'Inter', sans-serif;
  transition: background 0.3s;
}
.pos-header {
  background: var(--bg-header-gradient);
  height: 60px;
  padding: 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--text-header);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}
.brand-area {
  display: flex;
  align-items: center;
  gap: 12px;
}
.header-btn {
  color: white;
  font-size: 1.2rem;
}
.status-tag {
  background: rgba(255, 255, 255, 0.15);
  color: white;
  border: 1px solid rgba(255, 255, 255, 0.3);
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}
.pos-logo {
  height: 32px;
  filter: brightness(0) invert(1);
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
  min-width: 350px;
}

.form-card,
.grid-card,
.info-card,
.totals-widget {
  border-radius: 12px;
  background-color: var(--bg-card);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
}
.form-card {
  padding: 16px;
}
.info-card {
  padding: 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}
.totals-widget {
  padding: 20px;
  margin-top: auto;
  background: var(--bg-totals);
  color: var(--text-totals);
}

.field-label {
  display: block;
  font-size: 0.9rem;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 6px;
}
.field-label-small {
  display: block;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 2px;
  text-transform: uppercase;
}

/* SEARCH STYLE (POS) */
.client-search-input :deep(.ant-select-selector) {
  height: 45px !important;
  border-radius: 6px !important;
  display: flex;
  align-items: center;
  font-size: 1.1rem;
}
.client-option-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: 4px 0;
}
.client-name {
  font-weight: 700;
  font-size: 1rem;
  color: var(--text-primary);
}
.client-cuit {
  font-size: 0.8rem;
  color: var(--text-secondary);
  display: block;
}
.search-icon {
  color: var(--text-secondary);
  font-size: 1.2rem;
  margin-right: 8px;
}

/* ROW FISCAL */
.row-fiscal {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  flex-wrap: wrap;
  margin-bottom: 5px;
}
.field-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.field-group label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
}

/* INFO CARD EXACTO A POS */
.client-avatar {
  width: 60px;
  height: 60px;
  background: #3b82f6;
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2rem;
  font-weight: 700;
  margin-bottom: 10px;
  margin-left: auto;
  margin-right: auto;
}
.provider-details h3 {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 700;
  text-align: center;
}
.provider-details .cuit {
  color: var(--text-secondary);
  font-size: 0.9rem;
  margin-bottom: 8px;
  text-align: center;
}
.meta-row {
  width: 100%;
  display: flex;
  justify-content: space-between;
  margin-top: 15px;
  padding-top: 10px;
  border-top: 1px dashed var(--border-color);
}
.card-header {
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 1px;
  font-weight: 600;
  opacity: 0.6;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 8px;
  margin-bottom: 15px;
  width: 100%;
  text-align: left;
}
.empty-state {
  text-align: center;
  color: var(--text-secondary);
  padding: 20px;
}

/* PRODUCT VISUAL */
.product-visual {
  position: relative;
  margin-bottom: 15px;
  text-align: center;
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

/* TOTALS */
.total-big {
  text-align: right;
}
.total-big small {
  font-size: 0.8rem;
  opacity: 0.7;
}
.amount-display {
  font-size: 2.5rem;
  font-weight: 800;
  color: #60a5fa;
  line-height: 1.1;
}
.row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
  font-size: 0.95rem;
}
.pay-btn {
  margin-top: 20px;
  background: #3b82f6 !important;
  border: none;
  font-weight: 700;
  color: white !important;
  height: 55px;
  font-size: 1.25rem;
  box-shadow: 0 4px 6px rgba(37, 99, 235, 0.3);
}

/* PAGOS */
.payment-list {
  margin-top: 10px;
  max-height: 150px;
  overflow-y: auto;
  width: 100%;
}
.payment-row {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
  align-items: center;
}
.payment-summary {
  display: flex;
  justify-content: space-between;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed var(--border-color);
  font-size: 0.9rem;
  width: 100%;
}
.text-red {
  color: #ef4444;
}
.text-green {
  color: #10b981;
}

/* SEARCH ARTICULO */
.search-autocomplete :deep(.ant-select-selector) {
  height: 40px !important;
}
.prod-option {
  display: flex;
  justify-content: space-between;
}
.prod-name {
  font-weight: 600;
}
.prod-stock {
  color: #10b981;
  font-weight: 600;
}

:deep(.ant-table) {
  color: var(--text-primary);
}
:deep(.ant-table-thead > tr > th) {
  background: var(--bg-panel-right);
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-color);
}
:deep(.ant-input),
:deep(.ant-select-selector),
:deep(.ant-picker) {
  background-color: transparent !important;
  color: var(--text-primary) !important;
  border-color: var(--border-color) !important;
}
:deep(.row-selected td) {
  background-color: rgba(59, 130, 246, 0.1) !important;
}

/* GRID ACTIONS */
.grid-actions {
  padding: 12px;
  border-top: 1px solid var(--border-color);
  background: rgba(0, 0, 0, 0.01);
}
</style>
