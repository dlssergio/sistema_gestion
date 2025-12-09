<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import axios from 'axios'
import { message } from 'ant-design-vue'
import { SaveOutlined, ArrowLeftOutlined } from '@ant-design/icons-vue'

const router = useRouter()
const route = useRoute()
const isEditMode = computed(() => !!route.params.id)
const loading = ref(false)
const submitting = ref(false)

const formState = reactive({
  razon_social: '',
  cuit: '',
  email: '',
})

const fetchProveedor = async () => {
  if (!isEditMode.value) return
  loading.value = true
  try {
    const { data } = await axios.get(
      `http://tenant1.localhost:8000/api/proveedores/${route.params.id}/`,
    )
    // Asumiendo estructura de respuesta del serializer
    const entidad = data.entidad || data.entidad_data || {}
    formState.razon_social = entidad.razon_social
    formState.cuit = entidad.cuit
    formState.email = entidad.email
  } catch (e) {
    message.error('Error cargando datos')
  } finally {
    loading.value = false
  }
}

const onFinish = async () => {
  submitting.value = true
  try {
    // Ajustar payload según lo que espere tu backend para escritura (CreateSerializer)
    // Normalmente para escritura se envía la estructura plana o anidada según configures
    const payload = { ...formState }

    if (isEditMode.value) {
      await axios.put(`http://tenant1.localhost:8000/api/proveedores/${route.params.id}/`, payload)
      message.success('Proveedor actualizado')
    } else {
      await axios.post('http://tenant1.localhost:8000/api/proveedores/', payload)
      message.success('Proveedor creado')
    }
    router.push({ name: 'proveedores-lista' })
  } catch (e) {
    message.error('Error al guardar')
    console.error(e)
  } finally {
    submitting.value = false
  }
}

onMounted(() => fetchProveedor())
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <div class="title-area">
        <a-button shape="circle" @click="router.back()"><ArrowLeftOutlined /></a-button>
        <h2>{{ isEditMode ? 'Editar Proveedor' : 'Nuevo Proveedor' }}</h2>
      </div>
      <a-button type="primary" :loading="submitting" @click="onFinish" size="large">
        <SaveOutlined /> Guardar
      </a-button>
    </div>

    <a-spin :spinning="loading">
      <a-form layout="vertical" :model="formState">
        <a-card :bordered="false">
          <a-row :gutter="16">
            <a-col :span="12">
              <a-form-item label="Razón Social" name="razon_social" :rules="[{ required: true }]">
                <a-input v-model:value="formState.razon_social" />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="CUIT" name="cuit" :rules="[{ required: true }]">
                <a-input v-model:value="formState.cuit" />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="16">
            <a-col :span="12">
              <a-form-item label="Email">
                <a-input v-model:value="formState.email" />
              </a-form-item>
            </a-col>
          </a-row>
        </a-card>
      </a-form>
    </a-spin>
  </div>
</template>

<style scoped>
.page-container {
  max-width: 800px;
  margin: 0 auto;
  background: white;
  padding: 20px;
  border-radius: 8px;
}
.page-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 20px;
}
.title-area {
  display: flex;
  gap: 10px;
  align-items: center;
}
.title-area h2 {
  margin: 0;
}
</style>
