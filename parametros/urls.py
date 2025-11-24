# parametros/urls.py (VERSIÓN FINAL Y ROBUSTA)

from django.urls import path, include
from rest_framework.routers import DefaultRouter

# --- INICIO DE LA CORRECCIÓN ---
# Se importa MonedaViewSet, TipoComprobanteViewSet y las NUEVAS vistas de impuestos.
# Se elimina la importación de la obsoleta 'ReglaImpuestoViewSet'.
from .views import (
    MonedaViewSet, TipoComprobanteViewSet,
    ImpuestoViewSet, CategoriaImpositivaViewSet
)
# --- FIN DE LA CORRECCIÓN ---

router = DefaultRouter()
router.register(r'monedas', MonedaViewSet, basename='moneda')
router.register(r'tipos-comprobante', TipoComprobanteViewSet, basename='tipocomprobante')

# --- INICIO DE LA CORRECCIÓN ---
# Se elimina la ruta obsoleta para 'reglas-impuesto'.
# Se registran las nuevas rutas para la arquitectura robusta.
router.register(r'impuestos', ImpuestoViewSet, basename='impuesto')
router.register(r'categorias-impositivas', CategoriaImpositivaViewSet, basename='categoriaimpositiva')
# --- FIN DE LA CORRECCIÓN ---

urlpatterns = [
    path('', include(router.urls)),
]