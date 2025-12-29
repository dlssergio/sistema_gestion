<script setup>
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { message, theme } from 'ant-design-vue'
import dayjs from 'dayjs'
import { useConfigStore } from '@/stores/config'
import {
  SaveOutlined,
  ArrowLeftOutlined,
  PlusOutlined,
  DeleteOutlined,
} from '@ant-design/icons-vue'

const router = useRouter()
const configStore = useConfigStore()
const loading = ref(false)

const themeConfig = computed(() => {
  const isDark = configStore.currentTheme === 'dark'
  let algorithm = isDark ? theme.darkAlgorithm : theme.defaultAlgorithm
  let token = { borderRadius: 6, wireframe: false, fontFamily: "'Inter', sans-serif" }
  if (isDark) {
    token.colorPrimary = '#3b82f6'
    token.colorBgBase = '#0f172a'
    token.colorBgContainer = '#1e293b'
    token.colorBorder = '#334155'
  } else {
    token.colorPrimary = '#1e40af'
  }
  return { algorithm, token }
})

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

const columns = ref([
  { title: 'Artículo (Búsqueda)', dataIndex: 'articulo', width: '60%' },
  { title: 'Cant.', dataIndex: 'cantidad', width: '20%', align: 'center' },
  { title: '', dataIndex: 'actions', width: '20%', align: 'center' },
])

const fetchAuxiliares = async () => {
  try {
    const [provRes, tipoRes] = await Promise.allSettled([
      axios.get('http://tenant1.localhost:8000/api/proveedores/'),
      axios.get('http://tenant1.localhost:8000/api/tipos-comprobante/'),
    ])
    if (provRes.status === 'fulfilled') {
      const data = provRes.value.data.results || provRes.value.data
      proveedores.value = data.map((p) => ({
        value: p.id,
        label: p.entidad_data?.razon_social,
        cuit: p.entidad_data?.cuit,
      }))
    }
    if (tipoRes.status === 'fulfilled') {
      const data = tipoRes.value.data.results || tipoRes.value.data

      // --- CORRECCIÓN AQUÍ ---
      // Filtramos por nombre "Remito" Y ADEMÁS que sea clase 'C' (Compras)
      tiposComprobante.value = data
        .filter((t) => t.clase === 'C' && t.nombre.toLowerCase().includes('remito'))
        .map((t) => ({ value: t.id, label: t.nombre, fullData: t }))

      // Auto-selección si hay uno solo (muy útil si solo tienes un tipo de remito de compra)
      if (tiposComprobante.value.length > 0) {
        formState.tipo_comprobante = tiposComprobante.value[0].value
      }
    }
  } catch (e) {
    message.error('Error datos')
  }
}

watch(tiposComprobante, (newVal) => {
  if (newVal && newVal.length > 0 && !formState.tipo_comprobante)
    formState.tipo_comprobante = newVal[0].value
})

const esNumeracionManual = computed(() => {
  if (!formState.tipo_comprobante) return true
  const t = tiposComprobante.value.find((x) => x.value === formState.tipo_comprobante)
  return t ? !t.fullData.numeracion_automatica : true
})

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
    item.precio_costo_unitario = 0
  }
}

const createEmptyRow = () => ({
  key: Date.now(),
  articuloId: null,
  codigo: '',
  descripcion: '',
  cantidad: 1,
})
const addItem = () => items.value.push(createEmptyRow())
const removeItem = (index) => {
  if (items.value.length > 1) items.value.splice(index, 1)
}

const filterProveedor = (input, option) => option.label.toLowerCase().includes(input.toLowerCase())

const onFinish = async () => {
  if (!formState.proveedor || !formState.tipo_comprobante)
    return message.warning('Complete los datos')
  if (esNumeracionManual.value && !formState.numero) return message.warning('Falta Número')

  const validItems = items.value.filter((i) => i.articuloId)
  if (validItems.length === 0) return message.warning('Sin artículos')

  loading.value = true
  try {
    const payload = {
      ...formState,
      numero: esNumeracionManual.value ? parseInt(formState.numero, 10) : 0,
      fecha: formState.fecha.format('YYYY-MM-DD'),
      items: validItems.map((i) => ({
        articulo: i.articuloId,
        cantidad: i.cantidad,
        precio_costo_unitario: 0,
      })),
    }
    await axios.post('http://tenant1.localhost:8000/api/comprobantes-compra/', payload)
    message.success('Remito guardado')
    items.value = [createEmptyRow()]
    formState.numero = ''
    formState.proveedor = null
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
          <h2>Nuevo Remito de Ingreso</h2>
        </div>
      </header>
      <a-spin :spinning="loading">
        <main class="pos-body">
          <section class="left-panel">
            <a-card class="form-card mb-3" :bordered="false">
              <a-row :gutter="16">
                <a-col :span="10"
                  ><label class="field-label">Proveedor</label
                  ><a-select
                    v-model:value="formState.proveedor"
                    :options="proveedores"
                    show-search
                    placeholder="Buscar..."
                    :filter-option="filterProveedor"
                    class="full-width custom-select"
                    size="large"
                  ></a-select
                ></a-col>
                <a-col :span="5"
                  ><label class="field-label">Tipo</label
                  ><a-select
                    v-model:value="formState.tipo_comprobante"
                    :options="tiposComprobante"
                    size="large"
                    class="full-width"
                /></a-col>
                <a-col :span="3"
                  ><label class="field-label">Pto. Venta</label
                  ><a-input-number
                    v-model:value="formState.punto_venta"
                    class="full-width"
                    size="large"
                /></a-col>
                <a-col :span="3"
                  ><label class="field-label">Número</label
                  ><a-input
                    v-model:value="formState.numero"
                    size="large"
                    :disabled="!esNumeracionManual"
                /></a-col>
                <a-col :span="3"
                  ><label class="field-label">Fecha</label
                  ><a-date-picker
                    v-model:value="formState.fecha"
                    class="full-width"
                    format="DD/MM/YYYY"
                    size="large"
                /></a-col>
              </a-row>
            </a-card>
            <a-card class="grid-card" :bordered="false" :bodyStyle="{ padding: 0 }">
              <a-table
                :columns="columns"
                :data-source="items"
                :pagination="false"
                rowKey="key"
                size="middle"
              >
                <template #bodyCell="{ column, record, index }">
                  <template v-if="column.dataIndex === 'articulo'"
                    ><a-auto-complete
                      v-model:value="record.codigo"
                      :options="productOptions"
                      @search="searchArticulos"
                      @select="(val, opt) => onSelectArticulo(val, opt, index)"
                      class="full-width"
                      :bordered="false"
                      placeholder="🔍 Artículo..."
                      ><template #option="{ fullData }">{{
                        fullData.descripcion
                      }}</template></a-auto-complete
                    ></template
                  >
                  <template v-if="column.dataIndex === 'cantidad'"
                    ><a-input-number
                      v-model:value="record.cantidad"
                      :min="0"
                      :bordered="false"
                      class="full-width centered-input"
                  /></template>
                  <template v-if="column.dataIndex === 'actions'"
                    ><a-button type="text" danger size="small" @click="removeItem(index)"
                      ><DeleteOutlined /></a-button
                  ></template>
                </template>
              </a-table>
              <div class="grid-footer">
                <a-button type="dashed" block @click="addItem" size="large"
                  ><PlusOutlined /> Agregar Ítem</a-button
                >
              </div>
            </a-card>
          </section>
          <section class="right-panel">
            <div class="mt-4">
              <a-button
                type="primary"
                block
                size="large"
                class="save-btn"
                @click="onFinish"
                :loading="loading"
                ><SaveOutlined /> GUARDAR REMITO</a-button
              >
            </div>
          </section>
        </main>
      </a-spin>
    </div>
  </a-config-provider>
</template>

<style scoped>
/* ESTILOS ENTERPRISE BLUE & DARK */
.theme-light {
  --bg-app: #f1f5f9;
  --bg-header-gradient: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
  --text-header: #ffffff;
  --bg-card: #ffffff;
  --text-primary: #1e293b;
  --text-secondary: #64748b;
  --border-color: #e2e8f0;
}
.theme-dark {
  --bg-app: #020617;
  --bg-header-gradient: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  --text-header: #f8fafc;
  --bg-card: #1e293b;
  --text-primary: #f8fafc;
  --text-secondary: #94a3b8;
  --border-color: #334155;
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
  color: var(--text-header);
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
.form-card,
.grid-card {
  border-radius: 12px;
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
:deep(.ant-table) {
  color: var(--text-primary);
}
:deep(.ant-table-thead > tr > th) {
  background: transparent;
  color: var(--text-secondary);
}
.save-btn {
  background: #3b82f6;
  border: none;
  font-weight: 700;
  height: 50px;
  font-size: 1.1rem;
  color: white;
}
</style>
