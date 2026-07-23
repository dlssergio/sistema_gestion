# compras/urls.py
from rest_framework.routers import DefaultRouter
from django.urls import path, include

# Vistas regulares y ViewSets
from .views import (
    ComprobanteCompraViewSet,
    ProveedorViewSet,
    OrdenPagoViewSet,
    ListaPreciosProveedorViewSet,
    get_precio_proveedor_json,
    get_comprobante_info,
)

# Nuevas vistas de Cuenta Corriente (API)
from .cuenta_corriente_api import (
    cc_proveedor_api,
    compras_impagas_api,
    ordenes_pago_api,
    resumen_cartera_proveedores_api
)

router = DefaultRouter()
router.register(r'comprobantes-compra', ComprobanteCompraViewSet, basename='comprobantecompra')
router.register(r'proveedores', ProveedorViewSet, basename='proveedor')
router.register(r'ordenes-pago', OrdenPagoViewSet, basename='orden-pago')
router.register(r'listas-precios', ListaPreciosProveedorViewSet, basename='lista-precios')

urlpatterns = [
    # ── Rutas de Cuenta Corriente de Proveedores (Nuevas) ──
    # IMPORTANTE: Colocarlas ANTES de incluir el router para que no colisionen con los ViewSets
    path('proveedores-admin/resumen-cartera/', resumen_cartera_proveedores_api, name='resumen-cartera-proveedores'),

    # ¡FÍJATE BIEN EN ESTAS RUTAS PARA QUE COINCIDAN CON AXIOS!
    path('proveedores-admin/<int:pk>/cuenta-corriente/', cc_proveedor_api, name='proveedor-cuenta-corriente-api'),
    path('proveedores-admin/<int:pk>/comprobantes-impagos/', compras_impagas_api,
         name='proveedor-comprobantes-impagos-api'),
    path('proveedores-admin/<int:pk>/ordenes-pago/', ordenes_pago_api, name='proveedor-ordenes-pago-api'),

    # ── Rutas personalizadas (Existentes) ──
    path('precio-proveedor/<int:proveedor_pk>/<int:articulo_pk>/', get_precio_proveedor_json),
    path('comprobante-info/<int:pk>/', get_comprobante_info),

    # ── Rutas del Router (ViewSets) ──
    path('', include(router.urls)),
]