<script setup>
import { ref, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useConfigStore } from '@/stores/config'
import { useAuthStore } from '@/stores/auth'
import { message, theme } from 'ant-design-vue'
import {
  PieChartOutlined,
  UserOutlined,
  ShopOutlined,
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
const selectedKeys = ref([route.name])
const openKeys = ref([])

watch(
  () => route.name,
  (newVal) => {
    selectedKeys.value = [newVal]
  },
)

/**
 * ✅ Detecta si la vista actual pide "modo POS".
 * Se activa poniendo meta: { posMode: true } en la ruta.
 */
const isPosMode = computed(() => !!route.meta?.posMode)

const appWrapperRef = ref(null)
const cssVar = (name, fallback = '') => {
  const el = appWrapperRef.value || document.documentElement
  const v = getComputedStyle(el).getPropertyValue(name).trim()
  return v || fallback
}

/** Layout sizing (para fixed sider + content offset) */
const siderExpanded = 260
const siderCollapsed = 84
const siderWidth = computed(() => (collapsed.value ? siderCollapsed : siderExpanded))
const contentOffset = computed(() => `${siderWidth.value + 32}px`) // 16px margin a cada lado

/** Drawer Config */
const settingsOpen = ref(false)
const toggleTheme = () => {
  const newTheme = configStore.currentTheme === 'dark' ? 'light' : 'dark'
  configStore.setTheme(newTheme)
  message.success(`Tema: ${newTheme === 'dark' ? 'Oscuro' : 'Profesional'}`)
}

/** Usuario */
const userLabel = computed(() => authStore.user?.name || authStore.user?.username || 'Usuario')

const handleLogout = () => {
  authStore.logout()
  router.push('/login')
}

/** =========================
 * Sidebar presets (persistente vía configStore)
 * ========================= */
const sidebarColors = [
  { key: 'blue', name: 'Azul', swatch: '#2563eb' },
  { key: 'slate', name: 'Slate', swatch: '#64748b' },
  { key: 'emerald', name: 'Esmeralda', swatch: '#10b981' },
  { key: 'gray', name: 'Gris', swatch: '#9ca3af' },
  { key: 'orange', name: 'Naranja', swatch: '#f97316' },
  { key: 'red', name: 'Rojo', swatch: '#ef4444' },
]

/** Fallback: inicial para cuando no hay logo */
const brandInitial = computed(() => {
  const n = (configStore.nombreFantasia || '').trim()
  return n ? n[0].toUpperCase() : 'E'
})

/** Tokens Ant Design leyendo CSS vars */
const themeConfig = computed(() => {
  const mode = configStore.currentTheme || 'light'
  const isDark = mode === 'dark'
  const algorithm = isDark ? theme.darkAlgorithm : theme.defaultAlgorithm

  const primary = cssVar('--primary', isDark ? '#3b82f6' : '#1e40af')
  const siderAccent = cssVar('--sider-accent', primary)

  const token = {
    borderRadius: parseInt(cssVar('--radius-lg', '10px'), 10),
    wireframe: false,
    fontFamily: cssVar(
      '--font-sans',
      "Manrope, Inter, system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif",
    ),

    colorPrimary: siderAccent,
    colorBgBase: cssVar('--app-bg', isDark ? '#0b1020' : '#f1f5f9'),
    colorBgContainer: cssVar('--surface-1', isDark ? '#111827' : '#ffffff'),
    colorTextBase: cssVar('--text-0', isDark ? '#e5e7eb' : '#0f172a'),
    colorBorder: cssVar('--border', isDark ? 'rgba(148,163,184,0.12)' : 'rgba(15,23,42,0.10)'),

    /* ✅ Anti “ámbar” (outline warning) */
    controlOutlineWidth: 0,
    controlOutline: 'transparent',

    boxShadowSecondary: 'none',
    boxShadowTertiary: 'none',
  }

  return { algorithm, token }
})
</script>

<template>
  <a-config-provider :theme="themeConfig">
    <div
      ref="appWrapperRef"
      class="app-wrapper"
      :class="[`theme-${configStore.currentTheme || 'light'}`, { 'pos-mode': isPosMode }]"
    >
      <!-- FIXED SIDER -->
      <a-layout-sider
        v-model:collapsed="collapsed"
        collapsible
        :width="siderExpanded"
        :collapsedWidth="siderCollapsed"
        class="custom-sider"
        :trigger="null"
      >
        <!-- ✅ BRAND / LOGO AREA -->
        <a-tooltip
          placement="right"
          :title="configStore.nombreFantasia"
          :mouseEnterDelay="0.25"
          :mouseLeaveDelay="0"
        >
          <div class="logo-area" :class="{ collapsed }">
            <!-- Collapsed: badge -->
            <div v-if="collapsed" class="brand-badge" aria-hidden="true">
              <img
                v-if="configStore.logoUrl"
                :src="configStore.logoUrl"
                class="brand-badge-img"
                alt=""
              />
              <div v-else class="brand-badge-fallback">{{ brandInitial }}</div>
            </div>

            <!-- Expanded: logo + name -->
            <div v-else class="brand-row">
              <div class="brand-avatar">
                <img
                  v-if="configStore.logoUrl"
                  :src="configStore.logoUrl"
                  class="brand-avatar-img"
                  alt="Logo"
                />
                <div v-else class="brand-avatar-fallback">{{ brandInitial }}</div>
              </div>

              <div class="brand-text">
                <div class="brand-name" :title="configStore.nombreFantasia">
                  {{ configStore.nombreFantasia }}
                </div>
                <div class="brand-sub">Gestión PyME</div>
              </div>
            </div>
          </div>
        </a-tooltip>

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
            <template #title>
              <span><ShopOutlined /><span>Ventas</span></span>
            </template>
            <a-menu-item key="venta-pos" @click="router.push({ name: 'venta-pos' })"
              >Punto de Venta</a-menu-item
            >
            <a-menu-item key="venta-presupuesto">
              <router-link :to="{ name: 'venta-presupuesto-nuevo' }">Presupuesto</router-link>
            </a-menu-item>
            <a-menu-item key="venta-factura-admin">
              <router-link :to="{ name: 'venta-factura-admin-nueva' }">Factura Admin.</router-link>
            </a-menu-item>
            <a-menu-item key="venta-remito">
              <router-link :to="{ name: 'venta-remito-nuevo' }">Remito Salida</router-link>
            </a-menu-item>
            <a-menu-item
              key="consulta-comprobantes"
              @click="router.push({ name: 'consulta-comprobantes' })"
            >
              Comprobantes
            </a-menu-item>
            <a-menu-item key="clientes-lista">Clientes</a-menu-item>
          </a-sub-menu>

          <a-sub-menu key="sub-inventario">
            <template #title>
              <span><TagsOutlined /><span>Inventario</span></span>
            </template>
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
              <span><ShopOutlined /><span>Compras</span></span>
            </template>
            <a-sub-menu key="sub-compras-prov">
              <template #title>Admin. Proveedores</template>
              <a-menu-item key="proveedores-lista">
                <router-link :to="{ name: 'proveedores-lista' }">Proveedores</router-link>
              </a-menu-item>
            </a-sub-menu>

            <a-sub-menu key="sub-compras-docs">
              <template #title>Comprobantes</template>
              <a-menu-item key="compra-orden">
                <router-link :to="{ name: 'compra-orden-nueva' }">Orden de Compra</router-link>
              </a-menu-item>
              <a-menu-item key="compra-factura">
                <router-link :to="{ name: 'compra-factura-nueva' }">Factura Proveedor</router-link>
              </a-menu-item>
              <a-menu-item key="compra-remito">
                <router-link :to="{ name: 'compra-remito-nuevo' }">Remito Ingreso</router-link>
              </a-menu-item>
            </a-sub-menu>
          </a-sub-menu>

          <a-sub-menu key="sub-finanzas">
            <template #title>
              <span><BankOutlined /><span>Finanzas</span></span>
            </template>
            <a-menu-item key="caja-lista" @click="router.push({ name: 'caja-lista' })"
              >Caja y Bancos</a-menu-item
            >
            <a-menu-item key="cheques-lista" @click="router.push({ name: 'cheques-lista' })"
              >Cheques</a-menu-item
            >
          </a-sub-menu>

          <div class="menu-divider"></div>

          <a-menu-item key="config">
            <SettingOutlined />
            <span>Configuración</span>
          </a-menu-item>
        </a-menu>
      </a-layout-sider>

      <!-- CONTENT LAYOUT (offset por sider fixed) -->
      <a-layout
        class="content-shell"
        :class="{ 'pos-mode': isPosMode }"
        :style="{ marginLeft: contentOffset }"
      >
        <!-- HEADER flotante -->
        <a-layout-header class="main-header">
          <div class="header-left">
            <div class="trigger" @click="collapsed = !collapsed">
              <component :is="collapsed ? MenuUnfoldOutlined : MenuFoldOutlined" />
            </div>

            <div class="page-block">
              <div class="page-kicker">{{ isPosMode ? 'POS' : 'Panel' }}</div>
              <div class="page-title">
                {{ route.meta.title || (isPosMode ? 'Punto de Venta' : 'Dashboard Ejecutivo') }}
              </div>
            </div>
          </div>

          <div class="header-right">
            <a-tooltip title="Opciones">
              <a-button type="text" class="icon-btn" @click="settingsOpen = true">
                <SettingOutlined />
              </a-button>
            </a-tooltip>

            <a-dropdown trigger="click">
              <div class="user-pill">
                <UserOutlined />
                <span class="user-name">{{ userLabel }}</span>
              </div>

              <template #overlay>
                <a-menu>
                  <a-menu-item key="profile">Perfil</a-menu-item>
                  <a-menu-item key="settings" @click="settingsOpen = true">Settings</a-menu-item>
                  <a-menu-divider />
                  <a-menu-item key="logout" @click="handleLogout">Cerrar sesión</a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </div>
        </a-layout-header>

        <a-layout-content class="content-wrapper" :class="{ 'pos-mode': isPosMode }">
          <router-view v-slot="{ Component, route: currentRoute }">
            <transition name="route">
              <component :is="Component" :key="currentRoute.name" />
            </transition>
          </router-view>
        </a-layout-content>

        <!-- ✅ En modo POS ocultamos el footer -->
        <a-layout-footer v-if="!isPosMode" class="main-footer">
          {{ configStore.nombreFantasia }} ©2025
        </a-layout-footer>
      </a-layout>

      <!-- Drawer -->
      <a-drawer
        v-model:open="settingsOpen"
        title="Opciones"
        placement="right"
        width="340"
        :bodyStyle="{ padding: '16px' }"
      >
        <div class="drawer-section">
          <div class="drawer-title">Modo</div>
          <div class="drawer-row">
            <a-button block @click="toggleTheme">
              <SkinOutlined />
              <span style="margin-left: 8px">
                Cambiar a {{ configStore.currentTheme === 'dark' ? 'Profesional' : 'Oscuro' }}
              </span>
            </a-button>
          </div>
        </div>

        <div class="drawer-section">
          <div class="drawer-title">Sidebar mini</div>
          <div class="drawer-row">
            <a-switch v-model:checked="collapsed" />
            <span style="margin-left: 10px">Contraer / expandir</span>
          </div>
        </div>

        <div class="drawer-section">
          <div class="drawer-title">Color del Sidebar</div>
          <div class="color-options">
            <button
              v-for="c in sidebarColors"
              :key="c.key"
              class="color-dot"
              :class="{ active: configStore.sidebarPreset === c.key }"
              :title="c.name"
              type="button"
              @click="configStore.setSidebarPreset(c.key)"
            >
              <span class="color-dot-fill" :style="{ background: c.swatch }" />
            </button>
          </div>
          <div class="drawer-hint" style="margin-top: 10px">
            Menú, switch, header y gráfico se adaptan al color elegido.
          </div>
        </div>
      </a-drawer>
    </div>
  </a-config-provider>
</template>

<style scoped>
/* Base */
.app-wrapper {
  background: var(--app-bg, #f1f5f9);
  min-height: 100vh;
  font-family: var(--font-sans, Manrope, Inter, system-ui, -apple-system, 'Segoe UI', Roboto);
}

/* =========================
   SIDER FIXED + FLOATING
   ========================= */
.custom-sider {
  position: fixed !important;
  top: 16px;
  left: 16px;
  height: calc(100vh - 32px) !important;
  z-index: 100;

  background: var(--sider-bg) !important;
  border-radius: 6px;
  overflow: hidden;

  box-shadow: 0 12px 26px -12px rgba(2, 6, 23, 0.55);
  border: 1px solid rgba(148, 163, 184, 0.14);

  /* ✅ animación "premium" al colapsar/expandir */
  transition: width 420ms cubic-bezier(0.22, 1, 0.36, 1) !important;
}

/* =========================
   BRAND / LOGO AREA
   ========================= */
.logo-area {
  height: 72px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 14px;

  /* base */
  background: rgba(0, 0, 0, 0.18);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);

  /* transición suave */
  transition:
    padding 420ms cubic-bezier(0.22, 1, 0.36, 1),
    height 420ms cubic-bezier(0.22, 1, 0.36, 1);
}

.logo-area.collapsed {
  height: 78px;
  padding: 0;
}

/* Expanded row */
.brand-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.brand-avatar {
  width: 38px;
  height: 38px;
  border-radius: 12px;
  overflow: hidden;

  display: grid;
  place-items: center;

  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.12);

  box-shadow: 0 10px 18px -14px rgba(0, 0, 0, 0.55);
}

.brand-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.brand-avatar-fallback {
  font-weight: 900;
  font-size: 16px;
  color: rgba(255, 255, 255, 0.92);
}

.brand-text {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.brand-name {
  color: rgba(255, 255, 255, 0.96);
  font-weight: 800;
  font-size: 15px;
  line-height: 1.05;

  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.brand-sub {
  color: rgba(255, 255, 255, 0.68);
  font-weight: 650;
  font-size: 12px;
  letter-spacing: 0.04em;
}

/* Collapsed badge */
.brand-badge {
  width: 44px;
  height: 44px;
  border-radius: 999px;
  overflow: hidden;

  display: grid;
  place-items: center;

  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.14);

  /* halo sutil basado en accent */
  box-shadow:
    0 14px 26px -18px rgba(0, 0, 0, 0.65),
    0 0 0 4px rgba(var(--accent-rgb), 0.14);
}

.brand-badge-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.brand-badge-fallback {
  font-weight: 950;
  font-size: 18px;
  color: rgba(255, 255, 255, 0.94);
}

/* Divider */
.menu-divider {
  height: 1px;
  background: rgba(255, 255, 255, 0.1);
  margin: 14px 18px;
}

/* =========================
   MENU CORPORATIVO
   ========================= */
:deep(.ant-menu.ant-menu-dark) {
  background: transparent;
  border-right: none;
}

:deep(.ant-menu-dark .ant-menu-item),
:deep(.ant-menu-dark .ant-menu-submenu-title) {
  border-radius: 6px;
  transition: all 0.18s ease;
}

/* Hover elegante */
:deep(.ant-menu-dark .ant-menu-item:hover),
:deep(.ant-menu-dark .ant-menu-submenu-title:hover) {
  background: var(--menu-hover-bg);
}

/* Active corporativo */
:deep(.ant-menu-dark .ant-menu-item-selected) {
  background: var(--menu-active-bg);
  border-left: 3px solid var(--menu-active-border);
}

:deep(.ant-menu-dark .ant-menu-item-selected .ant-menu-title-content),
:deep(.ant-menu-dark .ant-menu-item-selected .anticon) {
  color: var(--menu-active-strong);
}

/* Content shell */
.content-shell {
  min-height: 100vh;
  padding-right: 16px;

  /* ✅ acompaña el cambio de ancho del sider */
  transition: margin-left 420ms cubic-bezier(0.22, 1, 0.36, 1);
}

/* ✅ POS: que el contenido tenga más espacio útil */
.content-shell.pos-mode {
  padding-right: 0;
}

/* Header */
.main-header {
  position: sticky;
  top: 16px;
  z-index: 90;

  margin: 16px 16px 0 0;
  height: 64px;

  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;

  border-radius: 6px;

  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(15, 23, 42, 0.06);
  box-shadow: 0 8px 18px -10px rgba(2, 6, 23, 0.35);

  padding: 0 18px;
}

.theme-dark .main-header {
  background: rgba(11, 18, 35, 0.78);
  border-color: rgba(148, 163, 184, 0.14);
  backdrop-filter: blur(10px);
  box-shadow: 0 14px 30px rgba(0, 0, 0, 0.45);
}

.header-left,
.header-right {
  display: flex;
  align-items: center;
  gap: 14px;
}

.header-left {
  min-width: 0;
}

.trigger {
  font-size: 20px;
  cursor: pointer;
  color: var(--header-icon);
  transition: color 0.15s ease;
}
.trigger:hover {
  color: var(--header-accent);
}

.page-block {
  display: flex;
  flex-direction: column;
  justify-content: center;
  line-height: 1.05;
  min-width: 0;
}

.page-kicker {
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(100, 116, 139, 0.95);
}

.page-title {
  font-size: 18px;
  font-weight: 650;
  color: var(--header-text);

  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 52vw;
}

.icon-btn {
  font-size: 18px;
  color: var(--header-icon);
  border-radius: 6px;
  transition:
    background 0.2s,
    opacity 0.2s;
}
.icon-btn:hover {
  background: var(--header-hover);
}

.user-pill {
  display: inline-flex;
  align-items: center;
  gap: 10px;

  padding: 0 14px;
  height: 36px;
  border-radius: 999px;

  background: var(--header-pill-bg);
  border: 1px solid var(--header-pill-border);
  color: var(--header-text);

  cursor: pointer;
  transition: background 0.2s;
}
.user-pill:hover {
  background: var(--header-hover);
}
.user-name {
  font-weight: 600;
}

.content-wrapper {
  margin: 26px 16px 0 0;
  min-height: 280px;
  /* Necesario para que route-leave-active con position:absolute funcione correctamente */
  position: relative;
}

/* ✅ POS: sin “marcos” extra, más alto útil */
.content-wrapper.pos-mode {
  margin: 16px 16px 0 0;
  min-height: calc(100vh - 16px - 64px - 16px - 16px); /* aprox: top + header + spacing */
}

.main-footer {
  text-align: center;
  color: var(--text-2, #64748b);
  background: transparent;
  padding: 14px 16px;
}

/* Drawer */
.drawer-section {
  padding: 10px 0 16px;
  border-bottom: 1px solid var(--border);
}
.drawer-title {
  font-weight: 800;
  margin-bottom: 10px;
  color: var(--text-0);
}
.drawer-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.drawer-hint {
  margin-top: 10px;
  font-size: 12px;
  color: var(--text-2);
}

.color-options {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  padding-top: 4px;
}

.color-dot {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  cursor: pointer;
  padding: 0;
  background: transparent;

  display: grid;
  place-items: center;

  border: 1px solid rgba(15, 23, 42, 0.18);
  box-shadow: 0 6px 14px -10px rgba(2, 6, 23, 0.35);
  transition:
    transform 0.2s cubic-bezier(0.22, 1, 0.36, 1),
    border-color 0.2s ease;
}
.color-dot:hover {
  transform: scale(1.08);
}

.color-dot-fill {
  width: 18px;
  height: 18px;
  border-radius: 999px;
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.18);
}

.color-dot.active {
  border-color: rgba(var(--accent-rgb), 0.9);
}

/* Switch (sidebar mini) con el mismo acento del sidebar */
:deep(.ant-switch-checked) {
  background: var(--sider-accent) !important;
}

/* =====================
   ROUTE TRANSITIONS
   ===================== */
:global(.route-enter-active) {
  transition:
    opacity 280ms cubic-bezier(0.22, 1, 0.36, 1),
    transform 280ms cubic-bezier(0.22, 1, 0.36, 1);
}
:global(.route-leave-active) {
  /* Salida rápida y fuera del flujo para no bloquear la entrada */
  transition: opacity 180ms ease;
  position: absolute;
  width: 100%;
  pointer-events: none;
}
:global(.route-enter-from) {
  opacity: 0;
  transform: translateY(8px);
}
:global(.route-leave-to) {
  opacity: 0;
}
</style>
