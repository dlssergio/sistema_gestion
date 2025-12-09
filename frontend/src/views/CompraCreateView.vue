<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { message } from 'ant-design-vue'
import dayjs from 'dayjs'
import {
  SaveOutlined,
  ArrowLeftOutlined,
  PlusOutlined,
  DeleteOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue'

const router = useRouter()
const loading = ref(false)

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

// --- CARGA INICIAL ---
const fetchAuxiliares = async () => {
  try {
    const [provRes, tipoRes] = await Promise.allSettled([
      axios.get('http://tenant1.localhost:8000/api/proveedores/'),
      axios.get('http://tenant1.localhost:8000/api/tipos-comprobante/'),
    ])

    // Proveedores (Mapeo robusto usando entidad.id si falla el id directo)
    if (provRes.status === 'fulfilled') {
      const data = provRes.value.data.results || provRes.value.data
      proveedores.value = data.map((p) => {
        const entidad = p.entidad_data || p.entidad || {}
        return {
          value: p.id || entidad.id, // Fallback seguro
          label: entidad.razon_social
            ? `${entidad.razon_social} (${entidad.cuit || 'S/C'})`
            : `Proveedor`,
        }
      })
    }

    if (tipoRes.status === 'fulfilled') {
      const data = tipoRes.value.data.results || tipoRes.value.data
      tiposComprobante.value = data.map((t) => ({ value: t.id, label: t.nombre }))
    } else {
      tiposComprobante.value = [
        { value: 1, label: 'Factura A' },
        { value: 2, label: 'Factura B' },
      ]
    }
  } catch (e) {
    message.error('Error cargando datos')
  }
}

const filterProveedor = (input, option) => {
  return option.label.toLowerCase().includes(input.toLowerCase())
}

// --- BÚSQUEDA DE ARTÍCULOS ---
const searchArticulos = async (txt) => {
  if (!txt || txt.length < 3) {
    productOptions.value = []
    return
  }
  try {
    const { data } = await axios.get(`http://tenant1.localhost:8000/api/articulos/?search=${txt}`)
    const list = data.results || data

    productOptions.value = list.map((a) => ({
      value: a.cod_articulo, // USAMOS COD_ARTICULO COMO VALOR ÚNICO
      label: a.descripcion,
      fullData: a,
    }))
  } catch (e) {
    console.error(e)
  }
}

// AL SELECCIONAR ARTÍCULO
const onSelectArticulo = (val, option, index) => {
  const item = items.value[index]
  const art = option.fullData

  if (art) {
    // --- CAMBIO CLAVE: Usamos cod_articulo como ID ---
    item.articulo = art.cod_articulo // Esto es lo que espera el Backend (PrimaryKeyRelatedField)
    item.codigo = art.cod_articulo
    item.descripcion = art.descripcion

    // Precio Costo (Manejo seguro)
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
  articulo: null,
  codigo: '',
  descripcion: '',
  cantidad: 1,
  precio_costo_unitario: 0,
})

const addItem = () => items.value.push(createEmptyRow())
const removeItem = (index) => items.value.splice(index, 1)

const totalCompra = computed(() => {
  return items.value.reduce((acc, item) => acc + item.cantidad * item.precio_costo_unitario, 0)
})

const onFinish = async () => {
  if (!formState.proveedor) return message.warning('Seleccione un Proveedor')

  // Filtramos usando la propiedad correcta
  const validItems = items.value.filter((i) => i.articulo)

  if (validItems.length === 0) return message.warning('Ingrese al menos un artículo válido')

  loading.value = true
  try {
    const payload = {
      ...formState,
      fecha: formState.fecha.format('YYYY-MM-DD'),
      items: validItems.map((i) => ({
        articulo: i.articulo, // Enviamos el código (ej: "ART-001")
        cantidad: i.cantidad,
        precio_costo_unitario: i.precio_costo_unitario,
      })),
    }

    await axios.post('http://tenant1.localhost:8000/api/comprobantes-compra/', payload)
    message.success('Compra registrada correctamente')

    items.value = [createEmptyRow()]
    formState.numero = ''
    formState.proveedor = null
  } catch (e) {
    const errorData = e.response?.data
    let errorMsg = 'Error al guardar la compra'
    if (errorData?.error) errorMsg = errorData.error
    else if (typeof errorData === 'object') errorMsg = JSON.stringify(errorData)
    message.error(errorMsg)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchAuxiliares()
  addItem()
})
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <div class="title-area">
        <a-button shape="circle" class="back-btn" @click="router.back()"
          ><ArrowLeftOutlined
        /></a-button>
        <h2>Registrar Compra</h2>
      </div>
      <div class="actions">
        <a-button type="primary" :loading="loading" @click="onFinish" size="large">
          <SaveOutlined /> Guardar Compra
        </a-button>
      </div>
    </div>

    <a-spin :spinning="loading">
      <a-form layout="vertical" class="form-content">
        <a-card class="mb-4 form-card" :bordered="false">
          <a-row :gutter="16">
            <a-col :span="8">
              <a-form-item label="Proveedor">
                <a-select
                  v-model:value="formState.proveedor"
                  :options="proveedores"
                  show-search
                  placeholder="Buscar (Nombre o CUIT)..."
                  :filter-option="filterProveedor"
                  class="full-width"
                  size="large"
                />
              </a-form-item>
            </a-col>
            <a-col :span="4">
              <a-form-item label="Tipo">
                <a-select
                  v-model:value="formState.tipo_comprobante"
                  :options="tiposComprobante"
                  size="large"
                />
              </a-form-item>
            </a-col>
            <a-col :span="4">
              <a-form-item label="Pto. Venta">
                <a-input-number
                  v-model:value="formState.punto_venta"
                  class="full-width"
                  size="large"
                />
              </a-form-item>
            </a-col>
            <a-col :span="4">
              <a-form-item label="Número">
                <a-input v-model:value="formState.numero" size="large" />
              </a-form-item>
            </a-col>
            <a-col :span="4">
              <a-form-item label="Fecha">
                <a-date-picker
                  v-model:value="formState.fecha"
                  class="full-width"
                  format="DD/MM/YYYY"
                  size="large"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </a-card>

        <a-card class="grid-card" :bordered="false" :bodyStyle="{ padding: 0 }">
          <div class="table-container">
            <table class="custom-table">
              <thead>
                <tr>
                  <th width="40%">Artículo (Código / Nombre)</th>
                  <th width="15%">Cantidad</th>
                  <th width="20%">Costo Unit.</th>
                  <th width="20%">Subtotal</th>
                  <th width="5%"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(item, index) in items" :key="item.key">
                  <td>
                    <a-auto-complete
                      v-model:value="item.codigo"
                      :options="productOptions"
                      @search="searchArticulos"
                      @select="(val, opt) => onSelectArticulo(val, opt, index)"
                      class="full-width"
                      :bordered="false"
                      placeholder="Buscar..."
                    >
                      <template #option="{ fullData }">
                        <div style="display: flex; flex-direction: column">
                          <span style="font-weight: bold">{{ fullData.descripcion }}</span>
                          <span style="font-size: 0.8em; color: #888"
                            >Cod: {{ fullData.cod_articulo }}</span
                          >
                        </div>
                      </template>
                    </a-auto-complete>
                  </td>
                  <td>
                    <a-input-number
                      v-model:value="item.cantidad"
                      :min="0"
                      :bordered="false"
                      class="full-width centered-input"
                    />
                  </td>
                  <td>
                    <a-input-number
                      v-model:value="item.precio_costo_unitario"
                      :min="0"
                      :bordered="false"
                      class="full-width right-align-input"
                      :formatter="(value) => `$ ${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')"
                      :parser="(value) => value.replace(/\$\s?|(,*)/g, '')"
                    />
                  </td>
                  <td class="text-right subtotal-val">
                    $
                    {{
                      (item.cantidad * item.precio_costo_unitario).toLocaleString('es-AR', {
                        minimumFractionDigits: 2,
                      })
                    }}
                  </td>
                  <td class="text-center">
                    <a-button type="text" danger size="small" @click="removeItem(index)">
                      <DeleteOutlined />
                    </a-button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="grid-footer">
            <a-button type="dashed" block @click="addItem">
              <PlusOutlined /> Agregar Ítem
            </a-button>
          </div>
        </a-card>

        <div class="totals-area mt-4">
          <div class="total-row">
            <span>Total Compra:</span>
            <span class="amount"
              >$ {{ totalCompra.toLocaleString('es-AR', { minimumFractionDigits: 2 }) }}</span
            >
          </div>
        </div>
      </a-form>
    </a-spin>
  </div>
</template>

<style scoped>
/* Estilos Enterprise Blue */
.page-container {
  max-width: 1200px;
  margin: 0 auto;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.title-area {
  display: flex;
  align-items: center;
  gap: 15px;
}
.title-area h2 {
  margin: 0;
  font-size: 1.5rem;
  color: var(--text-primary);
}
.back-btn {
  border: none;
  background: transparent;
  font-size: 1.2rem;
}
.full-width {
  width: 100%;
}
.form-card,
.grid-card {
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.custom-table {
  width: 100%;
  border-collapse: collapse;
}
.custom-table th {
  background: #f8fafc;
  padding: 12px;
  text-align: left;
  font-weight: 600;
  color: #475569;
  border-bottom: 1px solid #e2e8f0;
}
.custom-table td {
  padding: 8px;
  border-bottom: 1px solid #f1f5f9;
  vertical-align: middle;
}
.text-right {
  text-align: right;
}
.text-center {
  text-align: center;
}
.grid-footer {
  padding: 10px;
  background: #f8fafc;
  border-top: 1px solid #e2e8f0;
}

.totals-area {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
}
.total-row {
  background: white;
  color: #333;
  padding: 15px 25px;
  border-radius: 8px;
  font-size: 1.2rem;
  font-weight: bold;
  display: flex;
  gap: 20px;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
  border: 1px solid #e5e7eb;
}

:deep(.right-align-input input) {
  text-align: right !important;
}
:deep(.centered-input input) {
  text-align: center !important;
}
.subtotal-val {
  padding-right: 24px;
  font-weight: 600;
  color: #334155;
}
</style>
