# parametros/urls.py (VERSIÓN FINAL Y ROBUSTA)

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    MonedaViewSet, TipoComprobanteViewSet,
    ImpuestoViewSet, CategoriaImpositivaViewSet,
    ConfiguracionEmpresaView, CargaMasivaViewSet
)

router = DefaultRouter()
router.register(r'monedas', MonedaViewSet, basename='moneda')
router.register(r'tipos-comprobante', TipoComprobanteViewSet, basename='tipocomprobante')

router.register(r'impuestos', ImpuestoViewSet, basename='impuesto')
router.register(r'categorias-impositivas', CategoriaImpositivaViewSet, basename='categoriaimpositiva')

router.register(r'cargas-masivas', CargaMasivaViewSet, basename='carga-masiva')

urlpatterns = [
    path('configuracion/', ConfiguracionEmpresaView.as_view(), name='configuracion-empresa'), # <-- Nueva URL
    path('', include(router.urls)),
]