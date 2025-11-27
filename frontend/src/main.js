// en src/main.js

import './assets/main.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Toast from 'vue-toastification'
import 'vue-toastification/dist/index.css'

// --- 1. IMPORTACIONES ADICIONALES ---
import axios from 'axios'
import { useAuthStore } from './stores/auth'

import App from './App.vue'
import router from './router'

// --- IMPORTACIONES DE ANT DESIGN ---
import Antd from 'ant-design-vue' // <--- NUEVO 1
import 'ant-design-vue/dist/reset.css' // <--- NUEVO 2

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(Toast)
app.use(Antd) // <--- NUEVO 3: Registrar la librería

// --- 2. CONFIGURACIÓN DEL INTERCEPTOR DE AXIOS ---
// Este código se ejecutará antes de cada petición de Axios
axios.interceptors.request.use((config) => {
  // Obtenemos el store de autenticación
  const authStore = useAuthStore()
  const token = authStore.accessToken

  // Si el token existe, lo añadimos a la cabecera 'Authorization'
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

app.mount('#app')
