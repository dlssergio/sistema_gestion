<script setup>
import { onMounted } from 'vue'
import { RouterView } from 'vue-router'
import { useConfigStore } from './stores/config'

const configStore = useConfigStore()

onMounted(async () => {
  // Intentamos cargar configuración (logo, nombre) si es posible
  try {
    await configStore.cargarConfiguracion()
  } catch (e) {}
})
</script>

<template>
  <RouterView />
</template>

<style>
html,
body {
  margin: 0 !important;
  padding: 0 !important;
  height: 100%;
  width: 100%;
  font-family:
    'Inter',
    -apple-system,
    BlinkMacSystemFont,
    'Segoe UI',
    Roboto,
    Helvetica,
    Arial,
    sans-serif;
  background-color: #f0f2f5; /* Color de fondo base del admin */
  overflow-x: hidden; /* Evita scroll horizontal innecesario */
}

#app {
  height: 100%;
}
</style>
