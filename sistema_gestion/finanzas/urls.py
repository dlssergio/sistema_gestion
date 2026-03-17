# finanzas/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    TipoValorViewSet,
    CuentaFondoViewSet,
    BancoViewSet,
    PlanCuotaViewSet,
)

router = DefaultRouter()
router.register(r'tipos-valores', TipoValorViewSet, basename='tipos-valores')
router.register(r'cuentas-fondo', CuentaFondoViewSet, basename='cuentas-fondo')
router.register(r'bancos', BancoViewSet, basename='bancos')
router.register(r'planes-cuota', PlanCuotaViewSet, basename='planes-cuota')

urlpatterns = [
    path('', include(router.urls)),
]