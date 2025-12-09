<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { message } from 'ant-design-vue'
import { useRouter } from 'vue-router'
import { PlusOutlined, EditOutlined, DeleteOutlined, SearchOutlined } from '@ant-design/icons-vue'

const router = useRouter()
const data = ref([])
const loading = ref(false)
const searchText = ref('')

const columns = [
  { title: 'Razón Social', dataIndex: ['entidad', 'razon_social'], sorter: true },
  { title: 'CUIT', dataIndex: ['entidad', 'cuit'], width: 150 },
  { title: 'Condición IVA', dataIndex: ['entidad', 'situacion_iva', 'nombre'], width: 200 },
  { title: 'Acciones', key: 'actions', width: 120, align: 'center' },
]

const cargarProveedores = async () => {
  loading.value = true
  try {
    const params = {}
    if (searchText.value) params.search = searchText.value
    // Nota: Asegúrate de que el puerto sea el correcto (8000)
    const response = await axios.get('http://tenant1.localhost:8000/api/proveedores/', { params })
    data.value = response.data.results ? response.data.results : response.data
  } catch (e) {
    message.error('Error cargando proveedores')
  } finally {
    loading.value = false
  }
}

const eliminar = async (id) => {
  try {
    await axios.delete(`http://tenant1.localhost:8000/api/proveedores/${id}/`)
    message.success('Proveedor eliminado')
    cargarProveedores()
  } catch (e) {
    message.error('Error al eliminar')
  }
}

const onSearch = () => cargarProveedores()

onMounted(() => cargarProveedores())
</script>

<template>
  <div class="page-container">
    <div class="toolbar">
      <div class="search-area">
        <a-input-search
          v-model:value="searchText"
          placeholder="Buscar proveedor..."
          style="width: 300px"
          @search="onSearch"
          enter-button
          allow-clear
        />
      </div>
      <a-button type="primary" class="btn-create" @click="router.push({ name: 'proveedor-crear' })">
        <PlusOutlined /> Nuevo Proveedor
      </a-button>
    </div>

    <a-table
      :columns="columns"
      :data-source="data"
      :loading="loading"
      row-key="id"
      :pagination="{ pageSize: 10 }"
      size="middle"
      class="enterprise-table"
      bordered
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'actions'">
          <a-space>
            <a-button
              type="text"
              size="small"
              class="btn-icon-edit"
              @click="router.push({ name: 'proveedor-editar', params: { id: record.id } })"
            >
              <EditOutlined />
            </a-button>
            <a-popconfirm title="¿Eliminar?" @confirm="eliminar(record.id)">
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
  margin-bottom: 20px;
  border-bottom: 1px solid #f0f0f0;
  padding-bottom: 20px;
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
.btn-icon-edit {
  color: #2563eb;
}
.btn-icon-edit:hover {
  background: #eff6ff;
}
</style>
