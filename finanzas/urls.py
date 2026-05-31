# finanzas/urls.py
from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import (
    TipoValorViewSet, CuentaFondoViewSet, BancoViewSet,
    PlanCuotaViewSet, ChequeViewSet, MovimientoFondoViewSet,
    dashboard_metrics_api,
    reporte_cashflow_view, libro_iva_view, exportar_libro_iva_view,
)

router = DefaultRouter()
router.register(r'tipos-valores',   TipoValorViewSet,       basename='tipos-valores')
router.register(r'cuentas-fondo',   CuentaFondoViewSet,     basename='cuentas-fondo')
router.register(r'bancos',          BancoViewSet,           basename='bancos')
router.register(r'planes-cuota',    PlanCuotaViewSet,       basename='planes-cuota')
router.register(r'cheques',         ChequeViewSet,          basename='cheques')
router.register(r'movimientos',     MovimientoFondoViewSet, basename='movimientos')

urlpatterns = [
    path('', include(router.urls)),
]