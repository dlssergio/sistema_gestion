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
      component: () => import('@/views/LoginView.vue'),
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

        // ✅ POS AHORA DENTRO DEL LAYOUT (para que herede diseño/tema/drawer)
        {
          path: 'ventas/pos', // => /ventas/pos
          name: 'venta-pos',
          component: VentaPOSView,
          meta: { title: 'Punto de Venta', posMode: true },
        },

        // --- VENTAS ---
        {
          path: 'ventas/presupuesto/nuevo', // => /ventas/presupuesto/nuevo
          name: 'venta-presupuesto-nuevo',
          component: PresupuestoCreate,
          meta: { title: 'Nuevo Presupuesto' },
        },
        {
          path: 'ventas/remito/nuevo', // => /ventas/remito/nuevo
          name: 'venta-remito-nuevo',
          component: RemitoVentaCreate,
          meta: { title: 'Nuevo Remito de Salida' },
        },
        {
          path: 'ventas/comprobantes',
          name: 'consulta-comprobantes',
          component: () => import('../views/ventas/ConsultaComprobantes.vue'),
          meta: { title: 'Consulta de Comprobantes' },
        },
        {
          path: 'ventas/factura-admin/nueva', // => /ventas/factura-admin/nueva
          name: 'venta-factura-admin-nueva',
          component: () => import('../views/ventas/FacturaVentaCreate.vue'),
          meta: { title: 'Nueva Factura Administrativa' },
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
        {
          path: 'proveedores',
          name: 'proveedores-lista',
          component: () => import('../views/compras/ProveedorListView.vue'),
          meta: { title: 'Gestión de Proveedores' },
        },
        {
          path: 'compras/factura/nueva',
          name: 'compra-factura-nueva',
          component: () => import('../views/compras/FacturaCreate.vue'),
          meta: { title: 'Nueva Factura' },
        },
        {
          path: 'compras/remito/nuevo',
          name: 'compra-remito-nuevo',
          component: () => import('../views/compras/RemitoCreate.vue'),
          meta: { title: 'Nuevo Remito' },
        },
        {
          path: 'compras/orden/nueva',
          name: 'compra-orden-nueva',
          component: () => import('../views/compras/OrdenCompraCreate.vue'),
          meta: { title: 'Nueva Orden de Compra' },
        },

        // Carga Masiva (Importación de datos)
        {
          path: 'importar-datos',
          name: 'importacion-masiva',
          component: () => import('../views/parametros/ImportacionDatosView.vue'),
          meta: { title: 'Importación Masiva' },
        },
      ],
    },

    // ✅ (Opcional) Ruta 404
    // { path: '/:pathMatch(.*)*', redirect: '/' },
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
