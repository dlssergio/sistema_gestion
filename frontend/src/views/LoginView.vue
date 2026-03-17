<template>
  <div class="login-page">
    <div class="login-wrapper">
      <!-- NO envolver con .panel-left adentro: el componente ya es el panel -->
      <LoginBrandPanel />

      <!-- NO envolver con .panel-right extra: el componente ya controla su layout -->
      <LoginForm :loading="isLoading" :error="formError" @submit="handleLogin" />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

import LoginBrandPanel from '@/components/login/LoginBrandPanel.vue'
import LoginForm from '@/components/login/LoginForm.vue'

const router = useRouter()
const authStore = useAuthStore()

const isLoading = ref(false)
const formError = ref('')

const handleLogin = async ({ username, password }) => {
  formError.value = ''
  isLoading.value = true
  try {
    const ok = await authStore.login(username, password)
    if (ok) router.push({ name: 'home' })
    else formError.value = 'Credenciales incorrectas'
  } catch (e) {
    formError.value = 'Error de conexión'
  } finally {
    isLoading.value = false
  }
}
</script>

<style scoped>
.login-page {
  height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  font-family:
    Inter,
    system-ui,
    -apple-system,
    Segoe UI,
    Roboto,
    Arial,
    sans-serif;

  /* Fondo parecido al prototipo */
  background: radial-gradient(circle at 75% 20%, #6b82bf 0%, #2a3e74 45%, #1b2b55 100%);
}

.login-wrapper {
  width: 1250px;
  height: 700px;
  display: flex;
  border-radius: 22px;
  overflow: hidden;
  box-shadow: 0 50px 100px rgba(0, 0, 0, 0.45);
}
</style>
