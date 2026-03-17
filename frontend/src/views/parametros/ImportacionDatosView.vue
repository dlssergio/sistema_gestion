<template>
  <div class="p-6 max-w-4xl mx-auto font-sans">
    <div class="mb-8">
      <h1 class="text-2xl font-bold text-slate-800 tracking-tight">Importación Masiva</h1>
      <p class="text-sm text-slate-500">
        Sube archivos CSV para importar datos en lote sin bloquear el sistema.
      </p>
    </div>

    <div class="bg-white border border-slate-200 rounded-lg p-6 shadow-sm mb-6">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        <div>
          <label class="block text-sm font-medium text-slate-700 mb-2"
            >¿Qué datos vas a importar?</label
          >
          <a-select v-model:value="entidad" class="w-full" placeholder="Seleccione una entidad">
            <a-select-option value="ARTICULOS">Artículos / Inventario</a-select-option>
            <a-select-option value="PRECIOS_VENTA" disabled
              >Listas de Precios (Venta) - Pronto</a-select-option
            >
            <a-select-option value="PRECIOS_COMPRA" disabled
              >Listas de Precios (Compra) - Pronto</a-select-option
            >
            <a-select-option value="CLIENTES">Clientes</a-select-option>
            <a-select-option value="PROVEEDORES">Proveedores</a-select-option>
          </a-select>
        </div>

        <div>
          <label class="block text-sm font-medium text-slate-700 mb-2">Modo de Operación</label>
          <a-select v-model:value="modo" class="w-full" placeholder="Seleccione el modo">
            <a-select-option value="AMBOS">Crear nuevos y Actualizar existentes</a-select-option>
            <a-select-option value="CREAR">Solo Crear (Omitir existentes)</a-select-option>
            <a-select-option value="ACTUALIZAR">Solo Actualizar (Omitir nuevos)</a-select-option>
          </a-select>
        </div>
      </div>

      <a-upload-dragger
        v-model:fileList="fileList"
        name="archivo"
        :multiple="false"
        :before-upload="beforeUpload"
        @remove="handleRemove"
        class="bg-slate-50"
      >
        <p class="ant-upload-drag-icon text-blue-500">
          <InboxOutlined />
        </p>
        <p class="ant-upload-text font-medium text-slate-700">
          Haz clic o arrastra un archivo CSV aquí
        </p>
        <p class="ant-upload-hint text-slate-400">
          Solo se permite 1 archivo a la vez. El archivo debe contener los encabezados correctos.
        </p>
      </a-upload-dragger>

      <div class="mt-6 flex justify-end">
        <a-button
          type="primary"
          size="large"
          class="bg-blue-600"
          :disabled="fileList.length === 0 || !entidad || !modo"
          :loading="isStartingUpload"
          @click="iniciarImportacion"
        >
          Iniciar Importación
        </a-button>
      </div>
    </div>

    <div
      v-if="cargaId"
      class="bg-white border border-slate-200 rounded-lg p-6 shadow-sm mb-6 transition-all"
    >
      <div class="flex justify-between items-end mb-2">
        <h3 class="text-lg font-semibold text-slate-800">Progreso de la operación</h3>
        <span class="text-xs font-medium px-2 py-1 rounded bg-slate-100 text-slate-600">
          Estado: {{ estadoCarga }}
        </span>
      </div>

      <a-progress
        :percent="porcentaje"
        :status="progressStatus"
        :stroke-color="{ '0%': '#3b82f6', '100%': '#10b981' }"
      />

      <p class="text-sm text-slate-500 mt-3 flex items-center">
        <LoadingOutlined v-if="isProcessing" class="mr-2 text-blue-500 text-lg" />
        {{ mensajeProgreso }}
      </p>
    </div>

    <div v-if="errores.length > 0" class="bg-red-50 border border-red-200 rounded-lg p-6">
      <h3 class="text-red-800 font-semibold mb-3 flex items-center">
        <ExclamationCircleOutlined class="mr-2 text-xl" />
        Se encontraron {{ errores.length }} errores (Omitidos)
      </h3>
      <div class="max-h-60 overflow-y-auto bg-white border border-red-100 rounded text-sm">
        <table class="w-full text-left">
          <thead class="bg-red-50 text-red-700 sticky top-0">
            <tr>
              <th class="py-2 px-4 border-b border-red-100">Fila CSV</th>
              <th class="py-2 px-4 border-b border-red-100">Motivo del Error</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(err, idx) in errores"
              :key="idx"
              class="border-b border-slate-100 hover:bg-slate-50"
            >
              <td class="py-2 px-4 font-medium">{{ err.fila }}</td>
              <td class="py-2 px-4 text-slate-600">{{ err.error }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onUnmounted } from 'vue'
import { message } from 'ant-design-vue'
import { InboxOutlined, LoadingOutlined, ExclamationCircleOutlined } from '@ant-design/icons-vue'
import axios from 'axios'

const entidad = ref(null)
const modo = ref('AMBOS')
const fileList = ref([])
const isStartingUpload = ref(false)

const cargaId = ref(null)
const isProcessing = ref(false)
const porcentaje = ref(0)
const estadoCarga = ref('')
const filasProcesadas = ref(0)
const totalFilas = ref(0)
const errores = ref([])
let pollingInterval = null

const beforeUpload = (file) => {
  fileList.value = [file]
  return false
}

const handleRemove = () => {
  fileList.value = []
}

const progressStatus = computed(() => {
  if (
    estadoCarga.value === 'ERROR' ||
    (estadoCarga.value === 'COMPLETADO' && errores.value.length > 0)
  )
    return 'exception'
  if (estadoCarga.value === 'COMPLETADO') return 'success'
  return 'active'
})

const mensajeProgreso = computed(() => {
  if (estadoCarga.value === 'PENDIENTE') return 'En cola, esperando a que el servidor inicie...'
  if (estadoCarga.value === 'PROCESANDO')
    return `Procesando: ${filasProcesadas.value} de ${totalFilas.value} filas...`
  if (estadoCarga.value === 'COMPLETADO')
    return `¡Finalizado! ${filasProcesadas.value} filas procesadas correctamente.`
  if (estadoCarga.value === 'ERROR') return 'Ocurrió un error crítico durante la importación.'
  return ''
})

const iniciarImportacion = async () => {
  if (!fileList.value[0] || !entidad.value || !modo.value) return

  isStartingUpload.value = true
  errores.value = []
  porcentaje.value = 0
  cargaId.value = null

  const formData = new FormData()
  const archivoReal = fileList.value[0].originFileObj || fileList.value[0]
  formData.append('archivo', archivoReal)
  formData.append('entidad', entidad.value)
  formData.append('modo', modo.value)

  try {
    const token = localStorage.getItem('accessToken')

    const response = await axios.post(
      'http://tenant1.localhost:8000/api/cargas-masivas/',
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
          Authorization: `Bearer ${token}`,
        },
      },
    )

    message.success('Archivo subido. Iniciando procesamiento en segundo plano.')
    cargaId.value = response.data.id
    iniciarPolling()
  } catch (error) {
    if (error.response && error.response.data) {
      console.error('⛔ Django rechazó los datos por esto:', error.response.data)
      message.error(`Error de validación. Revisa la consola (F12).`)
    } else {
      message.error('Error de red o servidor no responde.')
      console.error(error)
    }
  } finally {
    isStartingUpload.value = false
  }
}

const iniciarPolling = () => {
  isProcessing.value = true

  pollingInterval = setInterval(async () => {
    try {
      const token = localStorage.getItem('accessToken')

      const { data } = await axios.get(
        `http://tenant1.localhost:8000/api/cargas-masivas/${cargaId.value}/`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        },
      )

      porcentaje.value = data.porcentaje_progreso
      estadoCarga.value = data.estado
      filasProcesadas.value = data.filas_procesadas
      totalFilas.value = data.total_filas

      if (
        ['OK', 'ER', 'Completado', 'Error General'].includes(data.estado) ||
        ['OK', 'ER', 'Completado', 'Error General'].includes(data.estado_display)
      ) {
        clearInterval(pollingInterval)
        isProcessing.value = false

        // Evaluamos si fue exitoso (OK o Completado)
        const fueExitoso =
          data.estado === 'OK' ||
          data.estado === 'Completado' ||
          data.estado_display === 'Completado'

        estadoCarga.value = fueExitoso ? 'COMPLETADO' : 'ERROR'
        errores.value = data.detalle_errores || []

        if (errores.value.length === 0 && fueExitoso) {
          message.success('¡Importación completada con éxito!')
        } else if (errores.value.length > 0) {
          message.warning(`Importación completada, pero con ${errores.value.length} errores.`)
        }
      }
    } catch (error) {
      clearInterval(pollingInterval)
      isProcessing.value = false
      message.error('Se perdió la conexión con el servidor al consultar el progreso.')
    }
  }, 1500)
}

onUnmounted(() => {
  if (pollingInterval) clearInterval(pollingInterval)
})
</script>
