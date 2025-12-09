// en src/router/index.js

import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

// Layouts
import MainLayout from '@/layouts/MainLayout.vue'

import HomeView from '../views/HomeView.vue'
import LoginView from '../views/LoginView.vue'
import VentaCreateView from '../views/VentaCreateView.vue'
import CompraCreateView from '../views/CompraCreateView.vue'
import ArticuloListView from '../views/ArticuloListView.vue'
import ArticuloFormView from '../views/ArticuloFormView.vue'
import VentaPOSView from '../views/ventas/VentaPOSView.vue'
import ProveedorListView from '../views/compras/ProveedorListView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    // RUTA PÚBLICA
    {
      path: '/login',
      name: 'login',
      component: LoginView,
    },

    // RUTA DEL POS (Pantalla Completa, sin Layout Administrativo)
    {
      path: '/ventas/pos',
      name: 'venta-pos',
      component: VentaPOSView,
      meta: { requiresAuth: true, title: 'Punto de Venta' },
    },

    // RUTAS ADMINISTRATIVAS (Con Layout)
    {
      path: '/',
      component: MainLayout, // <--- EL LAYOUT ENVUELVE TODO ESTO
      meta: { requiresAuth: true },
      children: [
        {
          path: '', // Home / Dashboard
          name: 'home',
          component: HomeView,
          meta: { title: 'Dashboard Ejecutivo' },
        },
        {
          path: 'articulos',
          name: 'articulo-lista',
          component: ArticuloListView,
          meta: { title: 'Gestión de Artículos' },
        },
        {
          path: 'articulos/nuevo',
          name: 'articulo-crear',
          component: ArticuloFormView,
          meta: { title: 'Nuevo Artículo' },
        },
        {
          path: 'articulos/editar/:id',
          name: 'articulo-editar',
          component: ArticuloFormView,
          meta: { title: 'Editar Artículo' },
        },
        {
          path: 'compras/nueva',
          name: 'compra-nueva',
          component: CompraCreateView,
          meta: { title: 'Registrar Compra' },
        },
        {
          path: 'proveedores',
          name: 'proveedores-lista',
          component: ProveedorListView,
          meta: { title: 'Gestión de Proveedores' },
        },
        // ... aquí irán compras, proveedores, etc ...
      ],
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
