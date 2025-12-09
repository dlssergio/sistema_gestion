<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { message } from 'ant-design-vue'
import { useRouter } from 'vue-router'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons-vue'

const router = useRouter()
const data = ref([])
const loading = ref(false)
const searchText = ref('')

// Columnas de la Tabla
const columns = [
  { title: 'Código', dataIndex: 'cod_articulo', width: 100, sorter: true },
  { title: 'Descripción', dataIndex: 'descripcion', sorter: true },
  { title: 'Marca', dataIndex: ['marca', 'nombre'], width: 150 },
  { title: 'Rubro', dataIndex: ['rubro', 'nombre'], width: 150 },
  { title: 'Stock', dataIndex: 'stock_total', width: 100, align: 'center' },
  { title: 'Precio Venta', dataIndex: 'precio_venta', width: 120, align: 'right' },
  { title: 'Activo', dataIndex: 'esta_activo', width: 80, align: 'center' },
  { title: 'Acciones', key: 'actions', width: 120, align: 'center' },
]

const cargarArticulos = async () => {
  loading.value = true
  try {
    const params = {}
    if (searchText.value) params.search = searchText.value
    const response = await axios.get('http://tenant1.localhost:8000/api/articulos/', { params })
    data.value = response.data.results ? response.data.results : response.data
  } catch (e) {
    message.error('Error al cargar artículos')
  } finally {
    loading.value = false
  }
}

const eliminarArticulo = async (id) => {
  try {
    await axios.delete(`http://tenant1.localhost:8000/api/articulos/${id}/`)
    message.success('Artículo eliminado')
    cargarArticulos()
  } catch (e) {
    message.error('No se pudo eliminar')
  }
}

onMounted(() => cargarArticulos())
</script>

<template>
  <div class="page-container">
    <div class="toolbar">
      <div class="search-area">
        <a-input-search
          v-model:value="searchText"
          placeholder="Buscar (Cod, Nombre, Marca)..."
          style="width: 300px"
          @search="cargarArticulos"
          enter-button
          allow-clear
        />
      </div>
      <a-button type="primary" @click="router.push({ name: 'articulo-crear' })" class="btn-create">
        <PlusOutlined /> Nuevo Artículo
      </a-button>
    </div>

    <a-table
      :columns="columns"
      :data-source="data"
      :loading="loading"
      row-key="cod_articulo"
      :pagination="{ pageSize: 10 }"
      size="middle"
      class="enterprise-table"
      bordered
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.dataIndex === 'precio_venta'">
          <span class="price-tag" v-if="record.precio_venta">
            $
            {{
              parseFloat(record.precio_venta.amount || record.precio_venta).toLocaleString(
                'es-AR',
                { minimumFractionDigits: 2 },
              )
            }}
          </span>
        </template>

        <template v-if="column.dataIndex === 'esta_activo'">
          <CheckCircleOutlined v-if="record.esta_activo" style="color: #10b981" />
          <CloseCircleOutlined v-else style="color: #ef4444" />
        </template>

        <template v-if="column.key === 'actions'">
          <a-space>
            <a-tooltip title="Editar">
              <a-button
                type="text"
                size="small"
                class="btn-icon-edit"
                @click="
                  router.push({ name: 'articulo-editar', params: { id: record.cod_articulo } })
                "
              >
                <EditOutlined />
              </a-button>
            </a-tooltip>
            <a-popconfirm title="¿Eliminar?" @confirm="eliminarArticulo(record.cod_articulo)">
              <a-button type="text" danger size="small">
                <DeleteOutlined />
              </a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </template>
    </a-table>
  </div>
</template>

<style scoped>
.page-container {
  background: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 20px;
  border-bottom: 1px solid #f0f0f0;
}
.btn-create {
  height: 40px;
  font-weight: 500;
}
.enterprise-table :deep(.ant-table-thead > tr > th) {
  background: #f8fafc;
  color: #475569;
  font-weight: 600;
}
.price-tag {
  font-weight: 600;
  color: #334155;
}
.btn-icon-edit {
  color: #2563eb;
}
.btn-icon-edit:hover {
  background: #eff6ff;
}
</style>
