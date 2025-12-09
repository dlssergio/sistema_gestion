<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import axios from 'axios'
import { message } from 'ant-design-vue'
import {
  SaveOutlined,
  ArrowLeftOutlined,
  UploadOutlined,
  LoadingOutlined,
  BarcodeOutlined,
} from '@ant-design/icons-vue'

const router = useRouter()
const route = useRoute()

const isEditMode = computed(() => !!route.params.id)
const pageTitle = computed(() => (isEditMode.value ? 'Editar Artículo' : 'Nuevo Artículo'))

const loading = ref(false)
const submitting = ref(false)

// Estado del Formulario (Modelo Real)
const formState = reactive({
  cod_articulo: '',
  descripcion: '',
  ean: '',
  qr: '',
  marca: null,
  rubro: null,
  perfil: 'BS', // Default: Bienes de Cambio
  unidad_medida_compra: 1, // Default: Unidad (ID 1 asumiendo fixtures)
  unidad_medida_venta: 1,
  alicuota_iva: 21.0,
  precio_costo: 0,
  precio_venta: 0,
  ubicacion: '',
  observaciones: '',
  esta_activo: true,
  foto: null,
})

const fileList = ref([])
const previewImage = ref('')

// Listas desplegables
const marcasOptions = ref([])
const rubrosOptions = ref([])
const perfilesOptions = ref([])
const unidadesOptions = ref([]) // Para U.M.

// --- CARGA DE DATOS ---

const fetchAuxiliares = async () => {
  try {
    const [marcasRes, rubrosRes, choicesRes, unidadesRes] = await Promise.allSettled([
      axios.get('http://tenant1.localhost:8000/api/marcas/'),
      axios.get('http://tenant1.localhost:8000/api/rubros/'),
      axios.get('http://tenant1.localhost:8000/api/articulos/choices/'), // Endpoint nuevo
      axios.get('http://tenant1.localhost:8000/api/unidades-medida/'), // Asumiendo que existe endpoint de U.M.
    ])

    // Marcas
    if (marcasRes.status === 'fulfilled') {
      const d = marcasRes.value.data
      const lista = d.results || d
      marcasOptions.value = lista.map((m) => ({ value: m.id, label: m.nombre }))
    }

    // Rubros
    if (rubrosRes.status === 'fulfilled') {
      const d = rubrosRes.value.data
      const lista = d.results || d
      rubrosOptions.value = lista.map((r) => ({ value: r.id, label: r.nombre }))
    }

    // Perfiles Reales (Backend)
    if (choicesRes.status === 'fulfilled') {
      // choices devuelve [["BS", "Bienes de Cambio"], ...]
      perfilesOptions.value = choicesRes.value.data.perfil.map((p) => ({
        value: p[0],
        label: p[1],
      }))
    }

    // Unidades (Mock si no existe API aún)
    if (unidadesRes.status === 'fulfilled') {
      // ... lógica similar ...
    } else {
      unidadesOptions.value = [
        { value: 1, label: 'Unidad' },
        { value: 2, label: 'Kilo' },
        { value: 3, label: 'Litro' },
      ]
    }
  } catch (e) {
    console.error('Error auxiliares', e)
  }
}

const fetchArticulo = async () => {
  if (!isEditMode.value) return
  loading.value = true
  try {
    const { data } = await axios.get(
      `http://tenant1.localhost:8000/api/articulos/${route.params.id}/`,
    )

    Object.assign(formState, {
      cod_articulo: data.cod_articulo,
      descripcion: data.descripcion,
      ean: data.ean,
      qr: data.qr,
      ubicacion: data.ubicacion,
      perfil: data.perfil,
      observaciones: data.observaciones,
      esta_activo: data.esta_activo,
      marca: data.marca?.id || data.marca,
      rubro: data.rubro?.id || data.rubro,
      unidad_medida_compra: data.unidad_medida_compra?.id || data.unidad_medida_compra,
      unidad_medida_venta: data.unidad_medida_venta?.id || data.unidad_medida_venta,
      // Precios
      precio_venta: parseFloat(data.precio_venta?.amount || data.precio_venta || 0),
      precio_costo: parseFloat(data.precio_costo?.amount || data.precio_costo || 0),
      alicuota_iva: parseFloat(data.alicuota_iva || 21),
    })

    if (data.foto) {
      previewImage.value = data.foto
      fileList.value = [{ uid: '-1', name: 'actual', status: 'done', url: data.foto }]
    }
  } catch (e) {
    message.error('Error al cargar')
    router.push({ name: 'articulo-lista' })
  } finally {
    loading.value = false
  }
}

// --- SUBIDA ---
const handleUploadChange = (info) => {
  const file = info.file
  if (info.fileList.length === 0) {
    formState.foto = null
    previewImage.value = ''
    return
  }
  formState.foto = file.originFileObj || file
  const reader = new FileReader()
  reader.readAsDataURL(formState.foto)
  reader.onload = (e) => (previewImage.value = e.target.result)
}

const onFinish = async () => {
  submitting.value = true
  try {
    const formData = new FormData()
    for (const key in formState) {
      if (key === 'foto') continue
      if (formState[key] !== null && formState[key] !== undefined) {
        formData.append(key, formState[key])
      }
    }
    if (formState.foto instanceof File) formData.append('foto', formState.foto)

    const config = { headers: { 'Content-Type': 'multipart/form-data' } }

    if (isEditMode.value) {
      await axios.put(
        `http://tenant1.localhost:8000/api/articulos/${route.params.id}/`,
        formData,
        config,
      )
      message.success('Actualizado')
    } else {
      await axios.post('http://tenant1.localhost:8000/api/articulos/', formData, config)
      message.success('Creado')
    }
    router.push({ name: 'articulo-lista' })
  } catch (e) {
    const errData = e.response?.data || {}
    const firstError = Object.values(errData)[0]
    message.error(`Error: ${firstError || 'Verifique los datos'}`)
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  await fetchAuxiliares()
  await fetchArticulo()
})
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <div class="title-area">
        <a-button shape="circle" class="back-btn" @click="router.back()"
          ><ArrowLeftOutlined
        /></a-button>
        <h2>{{ pageTitle }}</h2>
      </div>
      <div class="actions">
        <a-button type="primary" :loading="submitting" @click="onFinish" size="large">
          <SaveOutlined /> Guardar
        </a-button>
      </div>
    </div>

    <a-spin :spinning="loading">
      <a-form layout="vertical" :model="formState" class="form-content">
        <a-row :gutter="24">
          <a-col :xs="24" :lg="16">
            <a-card title="Identificación" :bordered="false" class="mb-4">
              <a-row :gutter="16">
                <a-col :span="8">
                  <a-form-item label="Código *" name="cod_articulo" :rules="[{ required: true }]">
                    <a-input v-model:value="formState.cod_articulo" :disabled="isEditMode" />
                  </a-form-item>
                </a-col>
                <a-col :span="8">
                  <a-form-item label="EAN / Barras" name="ean">
                    <a-input v-model:value="formState.ean">
                      <template #prefix><BarcodeOutlined /></template>
                    </a-input>
                  </a-form-item>
                </a-col>
                <a-col :span="8">
                  <a-form-item label="Código QR" name="qr">
                    <a-input v-model:value="formState.qr" />
                  </a-form-item>
                </a-col>
              </a-row>

              <a-form-item label="Descripción *" name="descripcion" :rules="[{ required: true }]">
                <a-textarea v-model:value="formState.descripcion" rows="2" />
              </a-form-item>

              <a-row :gutter="16">
                <a-col :span="8">
                  <a-form-item label="Marca">
                    <a-select
                      v-model:value="formState.marca"
                      :options="marcasOptions"
                      show-search
                      option-filter-prop="label"
                      placeholder="Buscar..."
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="8">
                  <a-form-item label="Rubro">
                    <a-select
                      v-model:value="formState.rubro"
                      :options="rubrosOptions"
                      show-search
                      option-filter-prop="label"
                      placeholder="Buscar..."
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="8">
                  <a-form-item label="Perfil (Tipo)">
                    <a-select v-model:value="formState.perfil" :options="perfilesOptions" />
                  </a-form-item>
                </a-col>
              </a-row>
            </a-card>

            <a-card title="Definición Comercial" :bordered="false" class="mb-4">
              <a-row :gutter="16">
                <a-col :span="12">
                  <a-form-item label="U. Medida Compra *">
                    <a-select
                      v-model:value="formState.unidad_medida_compra"
                      :options="unidadesOptions"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="U. Medida Venta *">
                    <a-select
                      v-model:value="formState.unidad_medida_venta"
                      :options="unidadesOptions"
                    />
                  </a-form-item>
                </a-col>
              </a-row>
              <a-row :gutter="16">
                <a-col :span="8">
                  <a-form-item label="Costo Neto">
                    <a-input-number
                      v-model:value="formState.precio_costo"
                      class="full-width"
                      :min="0"
                      :formatter="(v) => `$ ${v}`"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="8">
                  <a-form-item label="IVA %">
                    <a-input-number
                      v-model:value="formState.alicuota_iva"
                      class="full-width"
                      :min="0"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="8">
                  <a-form-item label="Precio Venta Final *" :rules="[{ required: true }]">
                    <a-input-number
                      v-model:value="formState.precio_venta"
                      class="full-width font-bold"
                      :min="0"
                      :formatter="(v) => `$ ${v}`"
                    />
                  </a-form-item>
                </a-col>
              </a-row>
            </a-card>
          </a-col>

          <a-col :xs="24" :lg="8">
            <a-card title="Foto" :bordered="false" class="mb-4 text-center">
              <div class="image-preview-wrapper">
                <img v-if="previewImage" :src="previewImage" class="image-preview" />
                <div v-else class="image-placeholder">Sin Imagen</div>
              </div>
              <a-upload
                :file-list="fileList"
                :before-upload="() => false"
                @change="handleUploadChange"
                :max-count="1"
                list-type="picture"
                class="mt-3"
              >
                <a-button block><UploadOutlined /> Subir</a-button>
              </a-upload>
            </a-card>

            <a-card title="Ubicación y Estado" :bordered="false">
              <a-form-item label="Ubicación Física">
                <a-input v-model:value="formState.ubicacion" placeholder="Ej: Pasillo 1" />
              </a-form-item>
              <a-divider />
              <a-form-item>
                <a-switch
                  v-model:checked="formState.esta_activo"
                  checked-children="Activo"
                  un-checked-children="Inactivo"
                />
              </a-form-item>
            </a-card>
          </a-col>
        </a-row>
      </a-form>
    </a-spin>
  </div>
</template>

<style scoped>
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
.font-bold {
  font-weight: 700;
}
.mb-4 {
  margin-bottom: 16px;
}
.mt-3 {
  margin-top: 12px;
}
.text-center {
  text-align: center;
}

.image-preview-wrapper {
  width: 100%;
  height: 200px;
  background: #f5f5f5;
  border-radius: 8px;
  border: 2px dashed #d9d9d9;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.image-preview {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.image-placeholder {
  color: #ccc;
}
</style>
