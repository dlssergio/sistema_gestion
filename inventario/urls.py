# en inventario/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ArticuloViewSet, MarcaViewSet, RubroViewSet

# El router se encarga de generar las URLs para el ViewSet automáticamente
router = DefaultRouter()
router.register(r'articulos', ArticuloViewSet, basename='articulo')
router.register(r'marcas', MarcaViewSet, basename='marca')
router.register(r'rubros', RubroViewSet, basename='rubro')

urlpatterns = [
    path('', include(router.urls)),
]