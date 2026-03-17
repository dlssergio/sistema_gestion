<script setup>
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import api from '@/services/api'

const props = defineProps({
  open: { type: Boolean, default: false },
})
const emit = defineEmits(['update:open', 'select'])

const internalOpen = computed({
  get: () => props.open,
  set: (v) => emit('update:open', v),
})

const loading = ref(false)
const rows = ref([])

const columns = [
  { title: 'Nro', dataIndex: 'numero_completo', width: 140 },
  { title: 'Cliente', dataIndex: 'cliente', ellipsis: true },
  { title: 'Fecha', dataIndex: 'fecha', width: 160 },
  { title: 'Total', dataIndex: 'total', width: 140, align: 'right' },
]

const money = (n) =>
  (Number(n) || 0).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const load = async () => {
  loading.value = true
  try {
    const { data } = await api.get('/api/comprobantes-venta/', { params: { estado: 'BR' } })
    const list = data?.results ?? data
    rows.value = (list || []).map((c) => ({
      id: c.id,
      numero_completo: c.numero_completo || `#${c.id}`,
      cliente: c.cliente?.entidad?.razon_social || '—',
      fecha: c.fecha ? String(c.fecha).replace('T', ' ').slice(0, 16) : '—',
      total: c.total || 0,
      raw: c,
    }))
  } catch (e) {
    console.error(e)
    message.error('No se pudieron cargar los borradores')
  } finally {
    loading.value = false
  }
}

watch(
  () => props.open,
  (v) => {
    if (v) load()
  },
)

const onSelectRow = async (row) => {
  // Traemos detalle por si la lista no incluye items (pero tu serializer sí los incluye)
  try {
    const { data } = await api.get(`/api/comprobantes-venta/${row.id}/`)
    emit('select', data)
    internalOpen.value = false
  } catch (e) {
    console.error(e)
    message.error('No se pudo cargar el borrador seleccionado')
  }
}
</script>

<template>
  <a-modal v-model:open="internalOpen" title="Ventas suspendidas" width="900px" centered>
    <a-table
      :columns="columns"
      :data-source="rows"
      :loading="loading"
      rowKey="id"
      :pagination="{ pageSize: 8 }"
      size="middle"
      :customRow="
        (record) => ({
          onClick: () => onSelectRow(record),
          style: { cursor: 'pointer' },
        })
      "
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.dataIndex === 'total'"> $ {{ money(record.total) }} </template>
      </template>
    </a-table>
  </a-modal>
</template>
