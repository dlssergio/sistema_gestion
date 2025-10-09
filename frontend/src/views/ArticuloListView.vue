<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { useToast } from 'vue-toastification'
import { RouterLink } from 'vue-router'

const toast = useToast()
const articulos = ref([])
const cargando = ref(true)
const error = ref(null)

// Función para cargar los artículos (sin cambios)
const cargarArticulos = async () => {
  cargando.value = true
  try {
    const response = await axios.get('http://127.0.0.1:8000/api/articulos/')
    articulos.value = response.data.results ? response.data.results : response.data
  } catch (e) {
    error.value = 'No se pudieron cargar los artículos.'
    toast.error('Error al cargar los artículos.')
    console.error(e)
  } finally {
    cargando.value = false
  }
}

onMounted(() => {
  cargarArticulos()
})

// --- NUEVA FUNCIÓN PARA ELIMINAR ---
const eliminarArticulo = async (articuloId) => {
  // 1. Pedimos confirmación al usuario
  if (
    window.confirm(
      `¿Estás seguro de que deseas eliminar el artículo ${articuloId}? Esta acción no se puede deshacer.`,
    )
  ) {
    try {
      // 2. Si confirma, enviamos la petición DELETE a la API
      await axios.delete(`http://127.0.0.1:8000/api/articulos/${articuloId}/`)

      // 3. Si la API responde con éxito, eliminamos el artículo de nuestra lista local
      //    para que la tabla se actualice instantáneamente sin recargar la página.
      articulos.value = articulos.value.filter((a) => a.cod_articulo !== articuloId)

      toast.success('Artículo eliminado con éxito.')
    } catch (e) {
      toast.error('Ocurrió un error al eliminar el artículo.')
      console.error(e)
    }
  }
}
</script>

<template>
  <div class="lista-articulos">
    <header class="lista-header">
      <h1>Gestión de Artículos</h1>
      <RouterLink to="/articulos/nuevo" class="btn-nuevo">Crear Nuevo Artículo</RouterLink>
    </header>

    <div v-if="cargando">Cargando artículos...</div>
    <div v-if="error" class="error">{{ error }}</div>

    <table v-if="articulos.length">
      <thead>
        <tr>
          <th>Código</th>
          <th>Descripción</th>
          <th>Stock Total</th>
          <th>Precio Venta</th>
          <th>Estado</th>
          <th>Acciones</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="articulo in articulos" :key="articulo.cod_articulo">
          <td>{{ articulo.cod_articulo }}</td>
          <td>{{ articulo.descripcion }}</td>
          <td>{{ articulo.stock_total }}</td>
          <td>${{ parseFloat(articulo.precio_venta_base).toFixed(2) }}</td>
          <td>
            <span :class="['estado', articulo.esta_activo ? 'activo' : 'inactivo']">
              {{ articulo.esta_activo ? 'Activo' : 'Inactivo' }}
            </span>
          </td>
          <td class="acciones">
            <RouterLink
              :to="{ name: 'articulo-editar', params: { id: articulo.cod_articulo } }"
              class="btn-accion editar"
            >
              Editar
            </RouterLink>
            <button @click="eliminarArticulo(articulo.cod_articulo)" class="btn-accion eliminar">
              Eliminar
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else-if="!cargando && !error">
      <p>No se encontraron artículos.</p>
    </div>
  </div>
</template>

<style scoped>
/* ... (Los estilos no necesitan cambios) ... */
.lista-articulos {
  padding: 2rem;
}
.lista-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
}
h1 {
  font-size: 2em;
}
.btn-nuevo {
  background-color: #2c3e50;
  color: white;
  padding: 0.7rem 1.2rem;
  border: none;
  border-radius: 5px;
  font-size: 1rem;
  cursor: pointer;
  text-decoration: none;
}
table {
  width: 100%;
  border-collapse: collapse;
}
th,
td {
  border: 1px solid #ddd;
  padding: 0.8rem;
  text-align: left;
}
th {
  background-color: #f8f8f8;
}
.estado {
  padding: 0.2rem 0.5rem;
  border-radius: 15px;
  font-size: 0.8em;
  font-weight: bold;
}
.estado.activo {
  background-color: #e8f5e9;
  color: #388e3c;
}
.estado.inactivo {
  background-color: #ffebee;
  color: #d32f2f;
}
.acciones .btn-accion {
  margin-right: 0.5rem;
  padding: 0.3rem 0.6rem;
  border: 1px solid #ccc;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9em;
  text-decoration: none;
  display: inline-block;
}
.editar {
  background-color: #e0e0e0;
  color: #333;
}
.eliminar {
  background-color: #ffcdd2;
  color: #c62828;
}
</style>
