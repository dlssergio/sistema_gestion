<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import axios from 'axios'
import { useRouter } from 'vue-router'
import TablaItems from '../components/TablaItems.vue' // <-- 1. IMPORTAMOS EL COMPONENTE
import { useToast } from 'vue-toastification'

const router = useRouter()
const toast = useToast()

// Cambiamos 'clientes' por 'proveedores'
const proveedores = ref([])
const tiposComprobante = ref([])
const proveedorSeleccionado = ref(null)
const tipoComprobanteSeleccionado = ref(null)
const fechaComprobante = ref(new Date().toISOString().slice(0, 10))

const itemsCompra = ref([])
const busquedaArticulo = ref('')
const resultadosBusqueda = ref([])

const error = ref(null)
const cargando = ref(true)
const guardando = ref(false)
let debounceTimer = null

// --- NUEVA FUNCIÓN PARA LIMPIAR EL FORMULARIO ---
const resetearFormulario = () => {
  proveedorSeleccionado.value = null
  tipoComprobanteSeleccionado.value = null
  fechaComprobante.value = new Date().toISOString().slice(0, 10)
  itemsCompra.value = []
  busquedaArticulo.value = ''
}

// --- LÓGICA (MÉTODOS) ---
onMounted(async () => {
  try {
    const [resProveedores, resTipos] = await Promise.all([
      axios.get('http://127.0.0.1:8000/api/proveedores/'),
      axios.get('http://127.0.0.1:8000/api/tipos-comprobante/'),
    ])
    proveedores.value = resProveedores.data.results
      ? resProveedores.data.results
      : resProveedores.data
    tiposComprobante.value = resTipos.data.results ? resTipos.data.results : resTipos.data
  } catch (e) {
    error.value = 'Error al cargar los datos iniciales.'
    console.error(e)
  } finally {
    cargando.value = false
  }
})

const buscarArticulos = async () => {
  if (busquedaArticulo.value.length < 2) {
    resultadosBusqueda.value = []
    return
  }
  try {
    const response = await axios.get(
      `http://127.0.0.1:8000/api/articulos/?search=${busquedaArticulo.value}`,
    )
    resultadosBusqueda.value = response.data.results ? response.data.results : response.data
  } catch (e) {
    console.error('Error buscando artículos:', e)
  }
}

const agregarItem = (articulo) => {
  itemsCompra.value.push({
    articulo: articulo,
    cantidad: 1,
    precio_costo_unitario_original: parseFloat(articulo.precio_costo_base).toFixed(2),
    moneda_costo: articulo.moneda_costo,
  })
  busquedaArticulo.value = ''
  resultadosBusqueda.value = []
}

const guardarComprobante = async () => {
  if (
    !proveedorSeleccionado.value ||
    !tipoComprobanteSeleccionado.value ||
    itemsCompra.value.length === 0
  ) {
    toast.warning('Por favor, complete la cabecera y añada al menos un artículo.')
    return
  }
  guardando.value = true
  error.value = null
  const payload = {
    proveedor: proveedorSeleccionado.value,
    tipo_comprobante: tipoComprobanteSeleccionado.value,
    fecha: fechaComprobante.value,
    estado: 'FN',
    punto_venta: 1,
    numero: Math.floor(Math.random() * 100000),
    items: itemsCompra.value.map((item) => ({
      articulo: item.articulo.cod_articulo,
      cantidad: item.cantidad,
      precio_costo_unitario_original: item.precio_costo_unitario_original,
      moneda_costo: item.moneda_costo,
    })),
  }
  try {
    await axios.post('http://127.0.0.1:8000/api/comprobantes-compra/', payload)
    toast.success('Comprobante de compra guardado con éxito!')

    // EN LUGAR DE REDIRIGIR, LIMPIAMOS EL FORMULARIO
    resetearFormulario()
  } catch (e) {
    const errorMessage = e.response?.data?.error || 'Ocurrió un error inesperado al guardar.'
    toast.error(errorMessage, { timeout: 7000 })
    console.error('Error al guardar:', e.response ? e.response.data : e.message)
  } finally {
    guardando.value = false
  }
}

watch(busquedaArticulo, () => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(buscarArticulos, 300)
})

const totalComprobante = computed(() => {
  return itemsCompra.value.reduce((total, item) => {
    return total + item.cantidad * item.precio_costo_unitario_original
  }, 0)
})
</script>

<template>
  <div class="form-compra">
    <h1>Crear Nuevo Comprobante de Compra</h1>

    <div v-if="cargando">Cargando datos...</div>
    <div v-if="error" class="error">{{ error }}</div>

    <form v-if="!cargando && !error" @submit.prevent="guardarComprobante">
      <fieldset class="seccion">
        <legend>Cabecera</legend>
        <div class="cabecera-grid">
          <div class="form-group">
            <label for="proveedor">Proveedor:</label>
            <select id="proveedor" v-model="proveedorSeleccionado">
              <option :value="null" disabled>-- Seleccione un proveedor --</option>
              <option
                v-for="proveedor in proveedores"
                :key="proveedor.entidad.id"
                :value="proveedor.entidad.id"
              >
                {{ proveedor.entidad.razon_social }}
              </option>
            </select>
          </div>
          <div class="form-group">
            <label for="tipo-comprobante">Tipo de Comprobante:</label>
            <select id="tipo-comprobante" v-model="tipoComprobanteSeleccionado">
              <option :value="null" disabled>-- Seleccione un tipo --</option>
              <option v-for="tipo in tiposComprobante" :key="tipo.id" :value="tipo.id">
                {{ tipo.nombre }}
              </option>
            </select>
          </div>
          <div class="form-group">
            <label for="fecha">Fecha:</label>
            <input type="date" id="fecha" v-model="fechaComprobante" />
          </div>
        </div>
      </fieldset>

      <fieldset class="seccion">
        <legend>Detalle</legend>
        <div class="form-group buscador-articulo">
          <label for="busqueda-articulo">Buscar Artículo:</label>
          <input
            type="text"
            id="busqueda-articulo"
            v-model="busquedaArticulo"
            placeholder="Escriba el nombre o código..."
            autocomplete="off"
          />
          <ul v-if="resultadosBusqueda.length" class="resultados-busqueda">
            <li
              v-for="articulo in resultadosBusqueda"
              :key="articulo.cod_articulo"
              @click="agregarItem(articulo)"
            >
              {{ articulo.descripcion }}
            </li>
          </ul>
        </div>

        <TablaItems :items="itemsCompra" tipo="Compra" @eliminar-item="eliminarItem" />

        <div class="total-comprobante">
          <strong>Total:</strong> ${{ totalComprobante.toFixed(2) }}
        </div>
      </fieldset>

      <div class="acciones-form">
        <button type="submit" :disabled="guardando">
          {{ guardando ? 'Guardando...' : 'Guardar Comprobante' }}
        </button>
      </div>
    </form>
  </div>
</template>

<style scoped>
/* 3. SE ELIMINARON LOS ESTILOS DE LA TABLA */
.form-compra {
  padding: 1rem;
}
.seccion {
  border: none;
  padding: 0;
  margin-top: 2rem;
}
.seccion legend {
  font-size: 1.5em;
  font-weight: bold;
  margin-bottom: 1rem;
}
.cabecera-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1.5rem;
}
.form-group {
  display: flex;
  flex-direction: column;
}
.form-group label {
  margin-bottom: 0.5rem;
  font-weight: bold;
}
.form-group select,
.form-group input {
  padding: 0.5rem;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 1rem;
}
.error {
  color: red;
}
.buscador-articulo {
  position: relative;
}
.resultados-busqueda {
  list-style-type: none;
  padding: 0;
  margin: 0;
  border: 1px solid #ccc;
  border-top: none;
  position: absolute;
  top: 100%;
  width: 100%;
  background: white;
  z-index: 10;
  max-height: 200px;
  overflow-y: auto;
}
.resultados-busqueda li {
  padding: 0.75rem;
  cursor: pointer;
}
.resultados-busqueda li:hover {
  background-color: #f0f0f0;
}
.total-comprobante {
  text-align: right;
  margin-top: 1.5rem;
  font-size: 1.8em;
  font-weight: bold;
}
.acciones-form {
  margin-top: 2rem;
  padding-top: 2rem;
  border-top: 1px solid #eee;
  text-align: right;
}
.acciones-form button {
  background-color: #2c3e50;
  color: white;
  padding: 0.8rem 1.5rem;
  border: none;
  border-radius: 5px;
  font-size: 1.1rem;
  cursor: pointer;
  transition: background-color 0.2s;
}
.acciones-form button:hover {
  background-color: #34495e;
}
.acciones-form button:disabled {
  background-color: #95a5a6;
  cursor: not-allowed;
}
</style>
