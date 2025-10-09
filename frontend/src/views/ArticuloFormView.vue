<script setup>
import { ref, onMounted, computed } from 'vue'
import axios from 'axios'
import { useToast } from 'vue-toastification'
import { useRouter, useRoute } from 'vue-router'

const toast = useToast()
const router = useRouter()
const route = useRoute()

const articleId = ref(route.params.id)
const isEditing = computed(() => !!articleId.value)
const pageTitle = computed(() => (isEditing.value ? 'Editar Artículo' : 'Crear Nuevo Artículo'))

const articulo = ref({
  cod_articulo: '',
  descripcion: '',
  ean: '',
  marca: null,
  rubro: null,
  impuesto: null,
  moneda_costo: 1,
  precio_costo_original: 0.0,
  utilidad: 0.0,
  moneda_venta: 1,
  precio_venta_original: 0.0,
  administra_stock: true,
  esta_activo: true,
})

const marcas = ref([])
const rubros = ref([])
const impuestos = ref([])
const monedas = ref([])
const cargando = ref(true)
const guardando = ref(false)
const error = ref(null)

onMounted(async () => {
  cargando.value = true
  try {
    const [resMarcas, resRubros, resImpuestos, resMonedas] = await Promise.all([
      axios.get('http://127.0.0.1:8000/api/marcas/'),
      axios.get('http://127.0.0.1:8000/api/rubros/'),
      axios.get('http://127.0.0.1:8000/api/impuestos/'),
      axios.get('http://127.0.0.1:8000/api/monedas/'),
    ])
    marcas.value = resMarcas.data.results || resMarcas.data
    rubros.value = resRubros.data.results || resRubros.data
    impuestos.value = resImpuestos.data.results || resImpuestos.data
    monedas.value = resMonedas.data.results || resMonedas.data

    if (isEditing.value) {
      const resArticulo = await axios.get(`http://127.0.0.1:8000/api/articulos/${articleId.value}/`)

      // --- MAPEO DE DATOS (LA CLAVE DE LA SOLUCIÓN) ---
      const dataFromApi = resArticulo.data
      // "Aplanamos" los datos para que coincidan con lo que el v-model espera
      articulo.value = {
        ...dataFromApi, // Copiamos todos los campos simples (descripcion, precios, etc.)
        marca: dataFromApi.marca ? dataFromApi.marca.id : null, // Extraemos solo el ID
        rubro: dataFromApi.rubro ? dataFromApi.rubro.id : null, // Extraemos solo el ID
        // impuesto, moneda_costo y moneda_venta ya vienen como IDs desde la API
      }
    }
  } catch (e) {
    error.value = 'No se pudieron cargar los datos necesarios.'
    toast.error(error.value)
  } finally {
    cargando.value = false
    onCostoUtilidadChange() // Hacemos un cálculo inicial
  }
})

// --- 2. CORRECCIÓN: Solo hay UNA definición de guardarArticulo ---
const guardarArticulo = async () => {
  guardando.value = true
  try {
    const payload = {
      ...articulo.value,
      precio_costo_original: parseFloat(articulo.value.precio_costo_original),
      utilidad: parseFloat(articulo.value.utilidad),
      precio_venta_original: parseFloat(articulo.value.precio_venta_original),
    }

    if (isEditing.value) {
      // Si estamos editando, usamos el método PUT
      await axios.put(`http://127.0.0.1:8000/api/articulos/${articleId.value}/`, payload)
      toast.success('Artículo actualizado con éxito.')
    } else {
      // Si estamos creando, usamos el método POST
      await axios.post('http://127.0.0.1:8000/api/articulos/', payload)
      toast.success('Artículo creado con éxito.')
    }
    router.push('/articulos')
  } catch (e) {
    let errorMessage = 'Error al guardar el artículo.'
    if (e.response && e.response.data) {
      const errors = e.response.data
      const errorMessages = Object.keys(errors).map((key) => {
        const errorValue = errors[key]
        return `${key}: ${Array.isArray(errorValue) ? errorValue.join(', ') : errorValue}`
      })
      errorMessage = errorMessages.join('; ')
    }
    toast.error(errorMessage, { timeout: 7000 })
    console.error('Error al guardar el artículo:', e.response?.data)
  } finally {
    guardando.value = false
  }
}

// ... (El resto de funciones y computadas no cambian)
const cotizacionCosto = computed(() => {
  const moneda = monedas.value.find((m) => m.id === articulo.value.moneda_costo)
  return moneda ? parseFloat(moneda.cotizacion) : 1
})
const cotizacionVenta = computed(() => {
  const moneda = monedas.value.find((m) => m.id === articulo.value.moneda_venta)
  return moneda ? parseFloat(moneda.cotizacion) : 1
})
const precioCostoBase = computed(() => {
  return (parseFloat(articulo.value.precio_costo_original) || 0) * cotizacionCosto.value
})
const precioVentaBase = computed(() => {
  return precioCostoBase.value * (1 + (parseFloat(articulo.value.utilidad) || 0) / 100)
})
const onCostoUtilidadChange = () => {
  if (cotizacionVenta.value > 0) {
    const nuevoPrecio = precioVentaBase.value / cotizacionVenta.value
    articulo.value.precio_venta_original = parseFloat(nuevoPrecio.toFixed(2))
  }
}
const onPrecioVentaChange = () => {
  const ventaBaseManual =
    (parseFloat(articulo.value.precio_venta_original) || 0) * cotizacionVenta.value
  if (precioCostoBase.value > 0 && ventaBaseManual >= precioCostoBase.value) {
    const nuevaUtilidad = (ventaBaseManual / precioCostoBase.value - 1) * 100
    articulo.value.utilidad = parseFloat(nuevaUtilidad.toFixed(2))
  } else {
    articulo.value.utilidad = 0
  }
}
const formatDecimalField = (fieldName) => {
  const value = parseFloat(articulo.value[fieldName])
  if (!isNaN(value)) {
    articulo.value[fieldName] = parseFloat(value.toFixed(2))
  }
}
</script>

<template>
  <div class="form-container">
    <header class="form-header">
      <h1>{{ pageTitle }}</h1>
      <RouterLink to="/articulos">Volver a la lista</RouterLink>
    </header>

    <div v-if="cargando">Cargando formulario...</div>
    <div v-if="error" class="error">{{ error }}</div>

    <form v-if="!cargando" @submit.prevent="guardarArticulo" class="form-grid">
      <div class="form-column">
        <fieldset class="seccion">
          <legend>Información Principal</legend>
          <div class="form-group">
            <label for="descripcion">Descripción</label>
            <input id="descripcion" v-model="articulo.descripcion" type="text" required />
          </div>
          <div class="form-group">
            <label for="cod_articulo">Código</label>
            <input
              id="cod_articulo"
              v-model="articulo.cod_articulo"
              type="text"
              :disabled="isEditing"
              placeholder="Se generará uno si se deja en blanco"
            />
          </div>
          <div class="form-group">
            <label for="ean">Código EAN</label>
            <input id="ean" v-model="articulo.ean" type="text" />
          </div>
          <div class="form-group-inline">
            <div class="form-group">
              <label for="marca">Marca</label>
              <select id="marca" v-model="articulo.marca">
                <option :value="null">-- Ninguna --</option>
                <option v-for="marca in marcas" :key="marca.id" :value="marca.id">
                  {{ marca.nombre }}
                </option>
              </select>
            </div>
            <div class="form-group">
              <label for="rubro">Rubro</label>
              <select id="rubro" v-model="articulo.rubro" required>
                <option :value="null" disabled>-- Seleccione --</option>
                <option v-for="rubro in rubros" :key="rubro.id" :value="rubro.id">
                  {{ rubro.nombre }}
                </option>
              </select>
            </div>
          </div>
        </fieldset>

        <fieldset class="seccion">
          <legend>Configuración</legend>
          <div class="form-group-checkbox">
            <input id="administra_stock" v-model="articulo.administra_stock" type="checkbox" />
            <label for="administra_stock">Administra Stock</label>
          </div>
          <div class="form-group-checkbox">
            <input id="esta_activo" v-model="articulo.esta_activo" type="checkbox" />
            <label for="esta_activo">Artículo Activo</label>
          </div>
        </fieldset>
      </div>

      <div class="form-column">
        <fieldset class="seccion">
          <legend>Precios y Costos</legend>
          <div class="form-group-inline">
            <div class="form-group">
              <label for="moneda_costo">Moneda Costo</label>
              <select
                id="moneda_costo"
                v-model="articulo.moneda_costo"
                @change="onCostoUtilidadChange"
              >
                <option v-for="moneda in monedas" :key="moneda.id" :value="moneda.id">
                  {{ moneda.nombre }}
                </option>
              </select>
            </div>
            <div class="form-group">
              <label for="precio_costo_original">Costo Original</label>
              <input
                id="precio_costo_original"
                v-model.number="articulo.precio_costo_original"
                type="number"
                step="0.01"
                @input="onCostoUtilidadChange"
                @blur="formatDecimalField('precio_costo_original')"
              />
            </div>
          </div>
          <div class="form-group">
            <label for="utilidad">Utilidad (%)</label>
            <input
              id="utilidad"
              v-model.number="articulo.utilidad"
              type="number"
              step="0.01"
              @input="onCostoUtilidadChange"
              @blur="formatDecimalField('utilidad')"
            />
          </div>
          <div class="form-group-inline">
            <div class="form-group">
              <label for="moneda_venta">Moneda Venta</label>
              <select
                id="moneda_venta"
                v-model="articulo.moneda_venta"
                @change="onCostoUtilidadChange"
              >
                <option v-for="moneda in monedas" :key="moneda.id" :value="moneda.id">
                  {{ moneda.nombre }}
                </option>
              </select>
            </div>
            <div class="form-group">
              <label for="precio_venta_original">Precio Venta</label>
              <input
                id="precio_venta_original"
                v-model.number="articulo.precio_venta_original"
                type="number"
                step="0.01"
                @input="onPrecioVentaChange"
                @blur="formatDecimalField('precio_venta_original')"
              />
            </div>
          </div>
          <div class="form-group">
            <label for="impuesto">Impuesto</label>
            <select id="impuesto" v-model="articulo.impuesto" required>
              <option :value="null" disabled>-- Seleccione --</option>
              <option v-for="impuesto in impuestos" :key="impuesto.id" :value="impuesto.id">
                {{ impuesto.descripcion }}
              </option>
            </select>
          </div>
          <div class="precios-calculados">
            <div>
              Costo Base (ARS): <strong>${{ precioCostoBase.toFixed(2) }}</strong>
            </div>
            <div>
              Venta Base (ARS): <strong>${{ precioVentaBase.toFixed(2) }}</strong>
            </div>
          </div>
        </fieldset>

        <div class="acciones-form">
          <button type="submit" :disabled="guardando">
            {{ guardando ? 'Guardando...' : 'Guardar Artículo' }}
          </button>
        </div>
      </div>
    </form>
  </div>
</template>

<style scoped>
.form-container {
  padding: 2rem;
  max-width: 1200px;
  margin: auto;
}
.form-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 2rem;
}
@media (min-width: 768px) {
  .form-grid {
    grid-template-columns: 1fr 1fr;
  }
}
.form-column,
.seccion {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}
.seccion {
  border: 1px solid #eee;
  padding: 1.5rem;
  border-radius: 8px;
}
.seccion legend {
  font-size: 1.2em;
  font-weight: bold;
  padding: 0 0.5rem;
  margin-left: -0.5rem;
}
.form-group {
  display: flex;
  flex-direction: column;
}
.form-group label {
  margin-bottom: 0.5rem;
  font-weight: 500;
}
.form-group-inline {
  display: flex;
  gap: 1rem;
}
.form-group-inline > .form-group {
  flex: 1;
}
.form-group-checkbox {
  display: flex;
  flex-direction: row-reverse;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
}
input,
select {
  width: 100%;
  padding: 0.8rem;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 1rem;
}
.precios-calculados {
  background-color: #f8f9fa;
  padding: 1rem;
  border-radius: 5px;
  display: flex;
  justify-content: space-around;
  font-size: 0.9em;
  border: 1px solid #e9ecef;
}
.acciones-form {
  text-align: right;
  margin-top: 1.5rem;
}
button {
  background-color: #2c3e50;
  color: white;
  padding: 0.8rem 1.5rem;
  border: none;
  border-radius: 5px;
  font-size: 1.1rem;
  cursor: pointer;
}
button:disabled {
  background-color: #95a5a6;
}
</style>
