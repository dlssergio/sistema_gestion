from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import ComprobanteCompraViewSet, ProveedorViewSet

router = DefaultRouter()
router.register(r'comprobantes-compra', ComprobanteCompraViewSet, basename='comprobantecompra')
router.register(r'proveedores', ProveedorViewSet)

urlpatterns = [
    path('', include(router.urls)),
]