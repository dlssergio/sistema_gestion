import { defineStore } from 'pinia'
import axios from 'axios'
import { ref, computed } from 'vue'

export const useConfigStore = defineStore('config', () => {
  // --- ESTADO ---
  const empresa = ref(null)
  const cargando = ref(false)
  const error = ref(null)

  const currentTheme = ref(localStorage.getItem('userTheme') || 'light')

  // --- GETTERS ---
  // Url segura del logo (si no hay, devuelve null)
  // Nota: Asumimos que el backend devuelve la URL completa gracias a MinIO/S3
  const logoUrl = computed(() => empresa.value?.logo || null)
  const nombreFantasia = computed(() => empresa.value?.nombre_fantasia || 's423 ERP')

  // Helper para saber si ya tenemos datos
  const esIdentidadCargada = computed(() => !!empresa.value)

  // --- ACCIONES ---
  async function cargarConfiguracion() {
    // Evitamos llamar a la API si ya estamos cargando
    if (cargando.value) return

    cargando.value = true
    error.value = null
    try {
      // Antes decía 127.0.0.1 o demo.localhost
      const response = await axios.get(
        'http://tenant1.localhost:8000/api/parametros/configuracion/',
      )
      empresa.value = response.data

      // Opcional: Cambiar el título de la pestaña del navegador
      if (empresa.value.nombre_fantasia) {
        document.title = empresa.value.nombre_fantasia
      }

      return true
    } catch (e) {
      console.error('Error cargando configuración de empresa:', e)
      // No bloqueamos la app, pero guardamos el error
      error.value = 'No se pudo cargar la identidad.'
      return false
    } finally {
      cargando.value = false
    }
  }

  function setTheme(themeKey) {
    currentTheme.value = themeKey
    localStorage.setItem('userTheme', themeKey)
  }

  return {
    empresa,
    cargando,
    error,
    logoUrl,
    nombreFantasia,
    esIdentidadCargada,
    cargarConfiguracion,
    currentTheme, // Exportamos
    setTheme,
  }
})
