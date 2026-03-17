<script setup>
import { onMounted, watch } from 'vue'
import { RouterView } from 'vue-router'
import { useConfigStore } from './stores/config'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const configStore = useConfigStore()

onMounted(() => {
  auth.restoreSession?.()
})

// Cuando se autentica, recién ahí pedimos la configuración de empresa
watch(
  () => auth.isAuthenticated,
  async (isAuth) => {
    if (!isAuth) return
    try {
      await configStore.cargarConfiguracion()
    } catch (e) {
      console.error('[Config] no se pudo cargar configuración:', e)
    }
  },
  { immediate: true },
)
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
  font-family: var(--font-sans, Manrope, Inter, system-ui, -apple-system, 'Segoe UI', Roboto);
  background: var(--app-bg, #f1f5f9);
  color: var(--text-0, #0f172a);
  overflow-x: hidden;
}

#app {
  height: 100%;
}
</style>
