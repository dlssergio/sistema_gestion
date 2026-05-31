# compras/urls.py
from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import (
    ComprobanteCompraViewSet,
    ProveedorViewSet,
    OrdenPagoViewSet,
    ListaPreciosProveedorViewSet,
    get_precio_proveedor_json,
    get_comprobante_info,
)

router = DefaultRouter()
router.register(r'comprobantes-compra', ComprobanteCompraViewSet, basename='comprobantecompra')
router.register(r'proveedores',         ProveedorViewSet,         basename='proveedor')
router.register(r'ordenes-pago',        OrdenPagoViewSet,         basename='orden-pago')
router.register(r'listas-precios',      ListaPreciosProveedorViewSet, basename='lista-precios')

urlpatterns = [
    path('', include(router.urls)),
    path('precio-proveedor/<int:proveedor_pk>/<int:articulo_pk>/', get_precio_proveedor_json),
    path('comprobante-info/<int:pk>/', get_comprobante_info),
]