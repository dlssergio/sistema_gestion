from django.urls import path, include
from rest_framework.routers import DefaultRouter
# <<< CAMBIO CLAVE: Reemplazamos ImpuestoViewSet por ReglaImpuestoViewSet >>>
from .views import MonedaViewSet, TipoComprobanteViewSet, ReglaImpuestoViewSet

router = DefaultRouter()
router.register(r'monedas', MonedaViewSet, basename='moneda')
router.register(r'tipos-comprobante', TipoComprobanteViewSet, basename='tipocomprobante')
# <<< CAMBIO CLAVE: Reemplazamos la ruta obsoleta por la nueva >>>
router.register(r'reglas-impuesto', ReglaImpuestoViewSet, basename='reglaimpuesto')

urlpatterns = [
    path('', include(router.urls)),
]