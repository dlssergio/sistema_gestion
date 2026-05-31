# inventario/urls.py — VERSIÓN DEFINITIVA (Fase 1 + 2 + 3 + ProveedorArticulo)

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    # Artículos
    ArticuloViewSet,
    # Maestros
    MarcaViewSet,
    RubroViewSet,
    CategoriaImpositivaViewSet,
    DepositoViewSet,
    MotivoAjusteViewSet,
    TipoStockViewSet,
    # Operaciones de stock
    AjusteStockViewSet,
    TransferenciaViewSet,
    # Consultas
    LedgerViewSet,
    BalanceStockViewSet,
    # Fase 3
    ValorizacionView,
    ActualizacionPreciosView,
    # Proveedor de artículo
    ProveedorArticuloViewSet,
    # Vistas admin (Django templates)
    kardex_articulo_view,
    reporte_valorizacion_view,
)

router = DefaultRouter()

# ── Artículos y maestros ──────────────────────────────────────
router.register(r'articulos',              ArticuloViewSet,            basename='articulo')
router.register(r'marcas',                 MarcaViewSet,               basename='marca')
router.register(r'rubros',                 RubroViewSet,               basename='rubro')
router.register(r'categorias-impositivas', CategoriaImpositivaViewSet, basename='categoria-impositiva')

# ── Configuración de inventario ───────────────────────────────
router.register(r'inventario/depositos',      DepositoViewSet,     basename='deposito')
router.register(r'inventario/motivos-ajuste', MotivoAjusteViewSet, basename='motivo-ajuste')
router.register(r'inventario/tipos-stock',    TipoStockViewSet,    basename='tipo-stock')

# ── Operaciones de stock ──────────────────────────────────────
router.register(r'inventario/ajustes',        AjusteStockViewSet,   basename='ajuste-stock')
router.register(r'inventario/transferencias', TransferenciaViewSet, basename='transferencia')

# ── Consultas (solo lectura) ──────────────────────────────────
router.register(r'inventario/ledger',   LedgerViewSet,       basename='ledger')
router.register(r'inventario/balance',  BalanceStockViewSet, basename='balance-stock')

# ── Fase 3: Reportes y precios ────────────────────────────────
router.register(r'inventario/valorizacion',       ValorizacionView,         basename='valorizacion')
router.register(r'inventario/actualizar-precios', ActualizacionPreciosView, basename='actualizar-precios')


urlpatterns = [
    path('', include(router.urls)),

    # ── Rutas nested: Proveedores de un Artículo ─────────────
    # GET/POST  /api/articulos/{articulo_pk}/proveedores/
    path(
        'articulos/<int:articulo_pk>/proveedores/',
        ProveedorArticuloViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='articulo-proveedores-list',
    ),
    # GET/PATCH/DELETE  /api/articulos/{articulo_pk}/proveedores/{pk}/
    path(
        'articulos/<int:articulo_pk>/proveedores/<int:pk>/',
        ProveedorArticuloViewSet.as_view({
            'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy',
        }),
        name='articulo-proveedores-detail',
    ),
    # POST  /api/articulos/{articulo_pk}/proveedores/{pk}/set_fuente_de_verdad/
    path(
        'articulos/<int:articulo_pk>/proveedores/<int:pk>/set_fuente_de_verdad/',
        ProveedorArticuloViewSet.as_view({'post': 'set_fuente_de_verdad'}),
        name='articulo-proveedores-fuente',
    ),

    # ── Vistas Django admin (templates, solo staff) ───────────
    path(
        'admin-views/kardex/<int:articulo_id>/',
        kardex_articulo_view,
        name='kardex-articulo',
    ),
    path(
        'admin-views/valorizacion/',
        reporte_valorizacion_view,
        name='reporte-valorizacion',
    ),
]

# ─────────────────────────────────────────────────────────────
# ENDPOINTS COMPLETOS (referencia rápida)
# ─────────────────────────────────────────────────────────────
#
# ARTÍCULOS
#   GET    /api/articulos/                                lista paginada
#   POST   /api/articulos/                                crear
#   GET    /api/articulos/{id}/                           detalle completo
#   PATCH  /api/articulos/{id}/                           editar parcial
#   DELETE /api/articulos/{id}/                           desactivar lógico
#   POST   /api/articulos/{id}/desactivar/
#   POST   /api/articulos/{id}/activar/
#   GET    /api/articulos/{id}/stock/                     balance por depósito
#   GET    /api/articulos/{id}/kardex/                    historial con saldo
#   GET    /api/articulos/choices/
#   GET    /api/articulos/alertas/                        bajo stock mínimo
#   GET    /api/articulos/dashboard/                      KPIs
#
# PROVEEDORES DEL ARTÍCULO
#   GET    /api/articulos/{articulo_pk}/proveedores/
#   POST   /api/articulos/{articulo_pk}/proveedores/
#   GET    /api/articulos/{articulo_pk}/proveedores/{pk}/
#   PATCH  /api/articulos/{articulo_pk}/proveedores/{pk}/
#   DELETE /api/articulos/{articulo_pk}/proveedores/{pk}/
#   POST   /api/articulos/{articulo_pk}/proveedores/{pk}/set_fuente_de_verdad/
#
# MAESTROS
#   /api/marcas/                    CRUD
#   /api/rubros/                    CRUD
#   /api/categorias-impositivas/    CRUD
#   /api/inventario/depositos/      CRUD
#   /api/inventario/motivos-ajuste/ CRUD
#   /api/inventario/tipos-stock/    solo lectura
#
# AJUSTES DE STOCK
#   GET/POST   /api/inventario/ajustes/
#   GET/PATCH  /api/inventario/ajustes/{id}/
#   POST       /api/inventario/ajustes/{id}/confirmar/
#   POST       /api/inventario/ajustes/{id}/anular/
#
# TRANSFERENCIAS
#   GET/POST   /api/inventario/transferencias/
#   GET/PATCH  /api/inventario/transferencias/{id}/
#   POST       /api/inventario/transferencias/{id}/enviar/
#   POST       /api/inventario/transferencias/{id}/recibir/
#   POST       /api/inventario/transferencias/{id}/anular/
#
# CONSULTAS
#   GET  /api/inventario/ledger/      historial inmutable
#   GET  /api/inventario/balance/     balance actual
#
# FASE 3
#   GET  /api/inventario/valorizacion/                        tabla JSON
#   GET  /api/inventario/valorizacion/exportar_excel/
#   GET  /api/inventario/valorizacion/exportar_pdf/
#   POST /api/inventario/actualizar-precios/preview/
#   POST /api/inventario/actualizar-precios/aplicar/