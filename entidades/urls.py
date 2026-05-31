from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ClienteViewSet, ProveedorViewSet, SituacionIVAViewSet
from ventas.clientes_admin_views import (
    ClienteAdminViewSet,
    clientes_admin_meta_categorias_api,
    clientes_admin_meta_price_lists_api,
    clientes_admin_meta_situaciones_iva_api,
    clientes_admin_meta_vendedores_api,
)

router = DefaultRouter()
router.register(r'clientes', ClienteViewSet, basename='cliente')
# ProveedorViewSet de entidades removido — usar compras.urls (ModelViewSet completo)
router.register(r'situaciones-iva', SituacionIVAViewSet, basename='situacion-iva')
router.register(r'clientes-admin', ClienteAdminViewSet, basename='cliente-admin')

urlpatterns = [
    path('clientes-admin-meta/situaciones-iva/', clientes_admin_meta_situaciones_iva_api),
    path('clientes-admin-meta/categorias/', clientes_admin_meta_categorias_api),
    path('clientes-admin-meta/vendedores/', clientes_admin_meta_vendedores_api),
    path('clientes-admin-meta/price-lists/', clientes_admin_meta_price_lists_api),
    path('', include(router.urls)),
]