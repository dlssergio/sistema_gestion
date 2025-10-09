<script setup>
// 1. Definimos las propiedades que este componente espera recibir de su padre.
const props = defineProps({
  items: {
    type: Array,
    required: true,
  },
  // Le pasamos un string para saber si es una tabla de 'Venta' o 'Compra'
  // y así mostrar el encabezado correcto ('Precio Unit.' o 'Costo Unit.').
  tipo: {
    type: String,
    default: 'Venta',
  },
})

// 2. Definimos los eventos que este componente puede emitir hacia su padre.
const emit = defineEmits(['eliminar-item', 'actualizar-item'])

// 3. Cuando se hace clic en eliminar, emitimos el evento con el índice del ítem.
const solicitarEliminacion = (index) => {
  emit('eliminar-item', index)
}
</script>

<template>
  <table class="tabla-items">
    <thead>
      <tr>
        <th>Descripción</th>
        <th>Cantidad</th>
        <th>{{ tipo === 'Venta' ? 'Precio Unit.' : 'Costo Unit.' }}</th>
        <th>Subtotal</th>
        <th>Acciones</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="(item, index) in props.items" :key="index">
        <td>{{ item.articulo.descripcion }}</td>
        <td><input type="number" v-model="item.cantidad" min="0" step="0.01" /></td>
        <td v-if="tipo === 'Venta'">
          <input type="number" v-model="item.precio_unitario_original" min="0" step="0.01" />
        </td>
        <td v-else>
          <input type="number" v-model="item.precio_costo_unitario_original" min="0" step="0.01" />
        </td>

        <td>
          {{
            tipo === 'Venta'
              ? (item.cantidad * item.precio_unitario_original).toFixed(2)
              : (item.cantidad * item.precio_costo_unitario_original).toFixed(2)
          }}
        </td>

        <td>
          <button type="button" @click="solicitarEliminacion(index)" class="btn-eliminar">
            Eliminar
          </button>
        </td>
      </tr>
      <tr v-if="props.items.length === 0">
        <td colspan="5">Aún no se han agregado artículos.</td>
      </tr>
    </tbody>
  </table>
</template>

<style scoped>
/* Los estilos para la tabla ahora viven aquí, de forma aislada */
.tabla-items {
  width: 100%;
  border-collapse: collapse;
  margin-top: 2rem;
}
.tabla-items th,
.tabla-items td {
  border: 1px solid #ddd;
  padding: 0.75rem;
  text-align: left;
}
.tabla-items th {
  background-color: #f8f8f8;
}
.tabla-items input {
  width: 100%;
  padding: 0.5rem;
  border: 1px solid #ccc;
  border-radius: 4px;
}
.tabla-items td[colspan='5'] {
  text-align: center;
  color: #777;
  padding: 2rem;
}
.btn-eliminar {
  background: #e74c3c;
  color: white;
  border: none;
  padding: 0.5rem;
  border-radius: 4px;
  cursor: pointer;
}
.btn-eliminar:hover {
  background: #c0392b;
}
</style>
