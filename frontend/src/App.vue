<script setup>
import { RouterLink, RouterView } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { useRouter } from 'vue-router'

const authStore = useAuthStore()
const router = useRouter()

const handleLogout = () => {
  authStore.logout()
  router.push('/login')
}
</script>

<template>
  <header>
    <div class="wrapper">
      <h1>ERP System</h1>

      <nav v-if="authStore.isAuthenticated">
        <RouterLink to="/">Inicio</RouterLink>
        <RouterLink to="/articulos">Artículos</RouterLink>
        <RouterLink to="/ventas/nuevo">Nueva Venta</RouterLink>
        <RouterLink to="/compras/nuevo">Nueva Compra</RouterLink>
        <a @click="handleLogout" class="logout-button">Cerrar Sesión</a>
      </nav>

      <nav v-else>
        <RouterLink to="/login">Iniciar Sesión</RouterLink>
      </nav>
    </div>
  </header>
  <RouterView />
</template>

<style scoped>
header {
  line-height: 1.5;
  max-height: 100vh;
  border-bottom: 1px solid #ccc;
  padding: 1rem;
}
h1 {
  font-weight: bold;
}
nav {
  width: 100%;
  font-size: 1rem;
  text-align: left;
  margin-top: 1rem;
}
nav a {
  display: inline-block;
  padding: 0 1rem;
  border-left: 1px solid var(--color-border);
}
nav a:first-of-type {
  border: 0;
  padding-left: 0;
}

/* Estilo para el botón de logout para que parezca un enlace */
.logout-button {
  cursor: pointer;
  color: var(--color-text);
  text-decoration: underline;
}
.logout-button:hover {
  color: var(--color-heading);
}
</style>
