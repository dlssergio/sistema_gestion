// src/router/index.js

import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

// Layouts
import MainLayout from '@/layouts/MainLayout.vue'

// Vistas principales (Static imports para lo esencial)
import HomeView from '../views/HomeView.vue'
import LoginView from '../views/LoginView.vue'
import VentaPOSView from '../views/ventas/VentaPOSView.vue'

const PresupuestoCreate = () => import('../views/ventas/PresupuestoCreate.vue')
const RemitoVentaCreate = () => import('../views/ventas/RemitoVentaCreate.vue')

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    // RUTA PÚBLICA
    {
      path: '/login',
      name: 'login',
      component: LoginView,
    },

    // RUTA DEL POS (Pantalla Completa)
    {
      path: '/ventas/pos',
      name: 'venta-pos',
      component: VentaPOSView,
      meta: { requiresAuth: true, title: 'Punto de Venta' },
    },
    // --- VENTAS ---
    {
      path: '/ventas/presupuesto/nuevo',
      name: 'venta-presupuesto-nuevo',
      component: PresupuestoCreate,
      meta: { title: 'Nuevo Presupuesto' },
    },
    {
      path: '/ventas/remito/nuevo',
      name: 'venta-remito-nuevo',
      component: RemitoVentaCreate,
      meta: { title: 'Nuevo Remito de Salida' },
    },
    {
      path: '/ventas/factura-admin/nueva',
      name: 'venta-factura-admin-nueva',
      component: () => import('../views/ventas/FacturaVentaCreate.vue'),
      meta: { title: 'Nueva Factura Administrativa' },
    },

    // RUTAS ADMINISTRATIVAS (Con Layout)
    {
      path: '/',
      component: MainLayout,
      meta: { requiresAuth: true },
      children: [
        {
          path: '', // Home / Dashboard
          name: 'home',
          component: HomeView,
          meta: { title: 'Dashboard Ejecutivo' },
        },

        // --- INVENTARIO ---
        {
          path: 'articulos',
          name: 'articulo-lista',
          component: () => import('../views/ArticuloListView.vue'),
          meta: { title: 'Gestión de Artículos' },
        },
        {
          path: 'articulos/nuevo',
          name: 'articulo-crear',
          component: () => import('../views/ArticuloFormView.vue'),
          meta: { title: 'Nuevo Artículo' },
        },
        {
          path: 'articulos/editar/:id',
          name: 'articulo-editar',
          component: () => import('../views/ArticuloFormView.vue'),
          meta: { title: 'Editar Artículo' },
        },

        // --- COMPRAS ---
        // 1. GESTIÓN DE PROVEEDORES
        {
          path: 'proveedores',
          name: 'proveedores-lista',
          // Asegúrate que el archivo esté en src/views/compras/ProveedorListView.vue
          component: () => import('../views/compras/ProveedorListView.vue'),
          meta: { title: 'Gestión de Proveedores' },
        },

        // 2. FACTURA (Nuevo archivo separado)
        {
          path: 'compras/factura/nueva',
          name: 'compra-factura-nueva',
          // IMPORTANTE: Verifica que src/views/compras/FacturaCreate.vue exista
          component: () => import('../views/compras/FacturaCreate.vue'),
          meta: { title: 'Nueva Factura' },
        },

        // 3. REMITO (Nuevo archivo separado)
        {
          path: 'compras/remito/nuevo',
          name: 'compra-remito-nuevo',
          // IMPORTANTE: Verifica que src/views/compras/RemitoCreate.vue exista
          component: () => import('../views/compras/RemitoCreate.vue'),
          meta: { title: 'Nuevo Remito' },
        },

        // 4. ORDEN DE COMPRA (Nuevo archivo separado)
        {
          path: 'compras/orden/nueva',
          name: 'compra-orden-nueva',
          // IMPORTANTE: Verifica que src/views/compras/OrdenCompraCreate.vue exista
          component: () => import('../views/compras/OrdenCompraCreate.vue'),
          meta: { title: 'Nueva Orden de Compra' },
        },
      ],
    },
  ],
})

// GUARDIA DE NAVEGACIÓN
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    next({ name: 'login' })
  } else {
    next()
  }
})

export default router
