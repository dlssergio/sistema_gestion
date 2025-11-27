// en src/router/index.js

import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import HomeView from '../views/HomeView.vue'
import LoginView from '../views/LoginView.vue'
import VentaCreateView from '../views/VentaCreateView.vue'
import CompraCreateView from '../views/CompraCreateView.vue'
import ArticuloListView from '../views/ArticuloListView.vue'
import ArticuloFormView from '../views/ArticuloFormView.vue'
import VentaPOSView from '../views/ventas/VentaPOSView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
      meta: { requiresAuth: true },
    },
    { path: '/login', name: 'login', component: LoginView },
    {
      path: '/ventas/nuevo', // <-- La URL para nuestro formulario
      name: 'venta-crear',
      component: VentaCreateView,
      meta: { requiresAuth: true },
    },
    {
      path: '/compras/nuevo',
      name: 'compra-crear',
      component: CompraCreateView,
      meta: { requiresAuth: true },
    },
    {
      path: '/articulos',
      name: 'articulo-lista',
      component: ArticuloListView,
      meta: { requiresAuth: true },
    },
    {
      path: '/articulos/nuevo',
      name: 'articulo-crear',
      component: ArticuloFormView,
      meta: { requiresAuth: true },
    },
    {
      path: '/articulos/editar/:id',
      name: 'articulo-editar',
      component: ArticuloFormView,
      meta: { requiresAuth: true },
    },
    {
      path: '/ventas/pos', // Esta será la URL para entrar
      name: 'venta-pos',
      component: VentaPOSView,
      meta: { requiresAuth: false },
    },
  ],
})

// --- 3. AÑADIMOS EL GUARDIA DE NAVEGACIÓN ---
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()

  // Si la ruta requiere autenticación y el usuario no está autenticado...
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    // ...lo redirigimos a la página de login.
    next({ name: 'login' })
  } else {
    // Si no, le permitimos continuar.
    next()
  }
})

export default router
