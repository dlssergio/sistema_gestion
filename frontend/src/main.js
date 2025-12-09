import './assets/main.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Toast from 'vue-toastification'
import 'vue-toastification/dist/index.css'
import axios from 'axios'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'

import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia) // Importante: Pinia antes que el router
app.use(router)
app.use(Toast)
app.use(Antd)

// --- CONFIGURACIÓN AXIOS (INTERCEPTORES) ---

// 1. Interceptor de Solicitud: Inyecta el Token
axios.interceptors.request.use((config) => {
  const authStore = useAuthStore()
  const token = authStore.accessToken
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 2. Interceptor de Respuesta: Maneja el Token Vencido
axios.interceptors.response.use(
  (response) => response, // Si todo sale bien, pasa
  async (error) => {
    const originalRequest = error.config
    const authStore = useAuthStore()

    // Si el error es 401 (No autorizado) y no hemos reintentado ya...
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true // Marcamos para no entrar en bucle infinito

      try {
        console.log('🔄 Renovando token...')
        // Intentamos renovar el token usando el endpoint de refresh
        const response = await axios.post('http://tenant1.localhost:8000/api/token/refresh/', {
          refresh: authStore.refreshToken,
        })

        // Si funciona, guardamos el nuevo token
        const newToken = response.data.access
        authStore.accessToken = newToken
        localStorage.setItem('accessToken', newToken)

        // Actualizamos la cabecera de la petición original y reintentamos
        originalRequest.headers.Authorization = `Bearer ${newToken}`
        return axios(originalRequest)
      } catch (refreshError) {
        // Si falla la renovación (ej: pasó mucho tiempo), cerramos sesión
        console.error('Sesión caducada, cerrando...')
        authStore.logout()
        router.push('/login')
        return Promise.reject(refreshError)
      }
    }
    return Promise.reject(error)
  },
)

app.mount('#app')
