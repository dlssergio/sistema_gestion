// en src/stores/auth.js (NUEVO ARCHIVO)

import { defineStore } from 'pinia'
import axios from 'axios'
import { ref, computed } from 'vue'

// Definimos el store de autenticación
export const useAuthStore = defineStore('auth', () => {
  // -- ESTADO --
  // Guardaremos los tokens aquí. Los obtenemos de localStorage por si el usuario
  // ya había iniciado sesión antes y refrescó la página.
  const accessToken = ref(localStorage.getItem('accessToken'))
  const refreshToken = ref(localStorage.getItem('refreshToken'))
  const user = ref(null) // Podríamos guardar aquí info del usuario si quisiéramos

  // -- GETTERS (Propiedades Computadas) --
  // Un getter para saber si el usuario está autenticado, simplemente
  // verificando si existe el token de acceso.
  const isAuthenticated = computed(() => !!accessToken.value)

  // -- ACCIONES --
  // Acción para iniciar sesión
  async function login(username, password) {
    try {
      // Hacemos la petición al endpoint /api/token/ que creamos en Django
      const response = await axios.post('http://127.0.0.1:8000/api/token/', {
        username: username,
        password: password,
      })

      // Si es exitoso, guardamos los tokens en el estado
      accessToken.value = response.data.access
      refreshToken.value = response.data.refresh

      // Y también los guardamos en localStorage para persistir la sesión
      localStorage.setItem('accessToken', accessToken.value)
      localStorage.setItem('refreshToken', refreshToken.value)

      return true // Devolvemos true para indicar que el login fue exitoso
    } catch (error) {
      // Si hay un error, limpiamos cualquier token viejo y devolvemos false
      logout()
      console.error('Error de autenticación:', error)
      return false
    }
  }

  // Acción para cerrar sesión
  function logout() {
    accessToken.value = null
    refreshToken.value = null
    localStorage.removeItem('accessToken')
    localStorage.removeItem('refreshToken')
    // Normalmente aquí también redirigiríamos al login
  }

  // Exponemos el estado y las acciones para que otros componentes puedan usarlos
  return {
    accessToken,
    isAuthenticated,
    login,
    logout,
  }
})
