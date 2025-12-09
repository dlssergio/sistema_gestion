<script setup>
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useConfigStore } from '@/stores/config'
import { useAuthStore } from '@/stores/auth'
import { message, theme } from 'ant-design-vue'
import {
  PieChartOutlined,
  UserOutlined,
  LogoutOutlined,
  ShopOutlined,
  ShoppingOutlined,
  TagsOutlined,
  SettingOutlined,
  MenuUnfoldOutlined,
  MenuFoldOutlined,
  BankOutlined,
  SkinOutlined,
} from '@ant-design/icons-vue'

const router = useRouter()
const route = useRoute()
const configStore = useConfigStore()
const authStore = useAuthStore()

const collapsed = ref(false)
const selectedKeys = computed(() => [route.name])
const openKeys = ref([])

// Configuración dinámica para componentes Ant Design
const themeConfig = computed(() => {
  const mode = configStore.currentTheme || 'light'
  const isDark = mode === 'dark'

  const algorithm = isDark ? theme.darkAlgorithm : theme.defaultAlgorithm
  const token = { borderRadius: 6, wireframe: false }

  if (isDark) {
    token.colorPrimary = '#3b82f6'
    token.colorBgBase = '#1e293b'
    token.colorTextBase = '#ffffff'
  } else {
    token.colorPrimary = '#1e40af'
  }

  return { algorithm, token }
})

const handleLogout = () => {
  authStore.logout()
  router.push('/login')
}

const toggleTheme = () => {
  const newTheme = configStore.currentTheme === 'dark' ? 'light' : 'dark'
  configStore.setTheme(newTheme)
  message.success(`Tema: ${newTheme === 'dark' ? 'Oscuro' : 'Profesional'}`)
}
</script>

<template>
  <a-config-provider :theme="themeConfig">
    <div class="app-wrapper" :class="`theme-${configStore.currentTheme || 'light'}`">
      <a-layout style="min-height: 100vh">
        <a-layout-sider
          v-model:collapsed="collapsed"
          collapsible
          width="260"
          class="custom-sider"
          :trigger="null"
        >
          <div class="logo-area">
            <img v-if="configStore.logoUrl" :src="configStore.logoUrl" class="logo-img" />
            <h1 v-if="!collapsed" class="logo-text">{{ configStore.nombreFantasia }}</h1>
          </div>

          <a-menu
            v-model:selectedKeys="selectedKeys"
            v-model:openKeys="openKeys"
            theme="dark"
            mode="inline"
            class="custom-menu"
          >
            <a-menu-item key="home" @click="router.push('/')">
              <PieChartOutlined /> <span>Dashboard</span>
            </a-menu-item>

            <a-sub-menu key="sub-ventas">
              <template #title
                ><span><ShopOutlined /><span>Ventas</span></span></template
              >
              <a-menu-item key="venta-pos" @click="router.push({ name: 'venta-pos' })"
                >Punto de Venta</a-menu-item
              >
              <a-menu-item key="venta-lista">Historial</a-menu-item>
              <a-menu-item key="clientes-lista">Clientes</a-menu-item>
            </a-sub-menu>

            <a-sub-menu key="sub-inventario">
              <template #title
                ><span><TagsOutlined /><span>Inventario</span></span></template
              >
              <a-menu-item key="articulo-lista" @click="router.push({ name: 'articulo-lista' })"
                >Artículos</a-menu-item
              >
              <a-menu-item key="articulo-crear" @click="router.push({ name: 'articulo-crear' })"
                >Nuevo Artículo</a-menu-item
              >
              <a-menu-item key="marcas-lista">Marcas & Rubros</a-menu-item>
            </a-sub-menu>

            <a-sub-menu key="sub-compras">
              <template #title>
                <span><ShoppingOutlined /><span>Compras</span></span>
              </template>
              <a-menu-item key="compra-nueva" @click="router.push({ name: 'compra-nueva' })">
                Nueva Compra
              </a-menu-item>
              <a-menu-item
                key="proveedores-lista"
                @click="router.push({ name: 'proveedores-lista' })"
              >
                Proveedores
              </a-menu-item>
            </a-sub-menu>

            <a-sub-menu key="sub-finanzas">
              <template #title>
                <span><BankOutlined /><span>Finanzas</span></span>
              </template>
              <a-menu-item key="caja-lista" @click="router.push({ name: 'caja-lista' })">
                Caja y Bancos
              </a-menu-item>
              <a-menu-item key="cheques-lista" @click="router.push({ name: 'cheques-lista' })">
                Cheques
              </a-menu-item>
            </a-sub-menu>

            <div class="menu-divider"></div>

            <a-menu-item key="config">
              <SettingOutlined />
              <span>Configuración</span>
            </a-menu-item>
          </a-menu>
        </a-layout-sider>

        <a-layout>
          <a-layout-header class="main-header">
            <div class="header-left">
              <div class="trigger" @click="() => (collapsed = !collapsed)">
                <component :is="collapsed ? MenuUnfoldOutlined : MenuFoldOutlined" />
              </div>
              <h2 class="page-title">{{ route.meta.title || 'Panel de Control' }}</h2>
            </div>

            <div class="header-right">
              <a-tooltip title="Cambiar Tema">
                <a-button type="text" class="icon-btn" @click="toggleTheme">
                  <SkinOutlined />
                </a-button>
              </a-tooltip>
              <div class="user-pill"><UserOutlined /> <span>Admin</span></div>
              <a-button type="text" class="icon-btn logout" @click="handleLogout">
                <LogoutOutlined />
              </a-button>
            </div>
          </a-layout-header>

          <a-layout-content class="content-wrapper">
            <router-view v-slot="{ Component }">
              <transition name="fade" mode="out-in">
                <component :is="Component" />
              </transition>
            </router-view>
          </a-layout-content>

          <a-layout-footer class="main-footer">
            {{ configStore.nombreFantasia }} ©2025
          </a-layout-footer>
        </a-layout>
      </a-layout>
    </div>
  </a-config-provider>
</template>

<style scoped>
/* =========================================================
   VARIABLES GLOBALES
   ========================================================= */
.app-wrapper {
  transition: all 0.3s ease;
  background-color: var(--content-bg);
}

/* TEMA LIGHT (Forzado explícitamente para garantizar Azul)
   -------------------------------------------------------
*/
.theme-light {
  --sider-bg: linear-gradient(180deg, #1e3a8a 0%, #0f172a 100%); /* Azul Marino Profundo */
  --header-bg: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%); /* Azul Real Vibrante */
  --content-bg: #f1f5f9;
  --text-header: #ffffff; /* Texto Blanco */
  --footer-text: #94a3b8;
  --menu-active-bg: #3b82f6;

  /* Variables para tarjetas del dashboard */
  --bg-card: #ffffff;
  --text-primary: #1e293b;
  --text-secondary: #64748b;
}

/* Reglas específicas para Light Mode (Override de AntD) */
.theme-light .main-header {
  background: var(--header-bg) !important;
  color: #ffffff !important;
  box-shadow: 0 4px 10px rgba(37, 99, 235, 0.2);
}
.theme-light .page-title {
  color: #ffffff !important;
}
.theme-light .icon-btn {
  color: #ffffff !important;
}
.theme-light .trigger {
  color: #ffffff !important;
}

/* TEMA DARK
   ---------
*/
.theme-dark {
  --sider-bg: linear-gradient(180deg, #000000 0%, #1e293b 100%);
  --header-bg: #0f172a; /* Slate 900 */
  --content-bg: #020617; /* Slate 950 */
  --text-header: #e2e8f0;
  --footer-text: #475569;
  --menu-active-bg: #facc15;

  /* Variables para tarjetas */
  --bg-card: #1e293b;
  --text-primary: #f8fafc;
  --text-secondary: #94a3b8;
}

.theme-dark .main-header {
  background: var(--header-bg) !important;
  color: var(--text-header) !important;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

/* =========================================================
   COMPONENTES
   ========================================================= */

/* Sidebar */
.custom-sider {
  background: var(--sider-bg) !important;
  box-shadow: 4px 0 10px rgba(0, 0, 0, 0.1);
}

/* Menú Transparente */
:deep(.ant-menu.ant-menu-dark) {
  background: transparent;
}
:deep(.ant-menu-dark .ant-menu-item-selected) {
  background-color: var(--menu-active-bg) !important;
}
:deep(.ant-menu-dark .ant-menu-sub) {
  background: rgba(0, 0, 0, 0.25) !important;
}

.logo-area {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.2);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}
.logo-img {
  height: 30px;
  margin-right: 10px;
}
.logo-text {
  color: white;
  font-weight: 700;
  font-size: 1.1rem;
  margin: 0;
}
.menu-divider {
  height: 1px;
  background: rgba(255, 255, 255, 0.1);
  margin: 15px 20px;
}

/* Header Estructural */
.main-header {
  padding: 0 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 64px;
  line-height: 64px;
  transition: all 0.3s;
}

.header-left,
.header-right {
  display: flex;
  align-items: center;
  gap: 15px;
}
.trigger {
  font-size: 20px;
  cursor: pointer;
}
.page-title {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
}

.icon-btn {
  font-size: 18px;
  transition: opacity 0.2s;
}
.icon-btn:hover {
  opacity: 0.8;
  background: rgba(255, 255, 255, 0.1);
}

.user-pill {
  background: rgba(255, 255, 255, 0.15);
  padding: 0 15px;
  border-radius: 20px;
  height: 36px;
  line-height: 36px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.9rem;
  font-weight: 500;
  color: inherit;
}

.content-wrapper {
  margin: 24px;
  min-height: 280px;
}
.main-footer {
  text-align: center;
  color: var(--footer-text);
  background: transparent;
  padding: 10px 50px;
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
