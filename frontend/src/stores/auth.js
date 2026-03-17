// frontend/src/stores/auth.js
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'

export const useAuthStore = defineStore('auth', () => {
  // ===== STATE =====
  const accessToken = ref(localStorage.getItem('accessToken'))
  const refreshToken = ref(localStorage.getItem('refreshToken'))
  const user = ref(null)
  const loading = ref(false)

  const isAuthenticated = computed(() => !!accessToken.value)

  // ===== LOGIN =====
  async function login(username, password) {
    loading.value = true
    try {
      const { data } = await api.post('/api/token/', {
        username,
        password,
      })

      accessToken.value = data.access
      refreshToken.value = data.refresh

      localStorage.setItem('accessToken', data.access)
      localStorage.setItem('refreshToken', data.refresh)

      // Opcional: cargar datos del usuario
      await fetchUser()

      return true
    } catch (error) {
      console.error('Error de autenticación:', error)
      logout()
      return false
    } finally {
      loading.value = false
    }
  }

  // ===== CARGAR USUARIO ACTUAL =====
  async function fetchUser() {
    try {
      const { data } = await api.get('/api/auth/me/')
      user.value = data?.user || null
    } catch (error) {
      console.warn('No se pudo obtener el usuario:', error)
      user.value = null
    }
  }

  // ===== RESTAURAR SESIÓN (cuando refrescás la página) =====
  async function restoreSession() {
    if (!accessToken.value) return
    try {
      await fetchUser()
    } catch {
      logout()
    }
  }

  // ===== LOGOUT =====
  function logout() {
    accessToken.value = null
    refreshToken.value = null
    user.value = null

    localStorage.removeItem('accessToken')
    localStorage.removeItem('refreshToken')
  }

  return {
    accessToken,
    refreshToken,
    user,
    loading,
    isAuthenticated,
    login,
    logout,
    restoreSession,
  }
})
