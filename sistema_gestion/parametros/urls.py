# en parametros/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MonedaViewSet, TipoComprobanteViewSet, ImpuestoViewSet

router = DefaultRouter()
router.register(r'monedas', MonedaViewSet, basename='moneda')
router.register(r'tipos-comprobante', TipoComprobanteViewSet, basename='tipocomprobante')
router.register(r'impuestos', ImpuestoViewSet, basename='impuesto')

urlpatterns = [
    path('', include(router.urls)),
]