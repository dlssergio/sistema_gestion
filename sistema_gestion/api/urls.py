# sistema_gestion/api/urls.py

from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

# Routers de las Apps
from inventario.urls import router as inventario_router
from entidades.urls import router as entidades_router
from parametros.urls import router as parametros_router
from ventas.urls import router as ventas_router
from compras.urls import router as compras_router
from finanzas.urls import router as finanzas_router

# Vistas manuales
from parametros.views import ConfiguracionEmpresaView
from finanzas.views import dashboard_metrics_api

urlpatterns = [
    # 1. Autenticación JWT
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # 2. Configuración de Empresa
    path('parametros/configuracion/', ConfiguracionEmpresaView.as_view(), name='configuracion-empresa'),

    # 3. Dashboard Ejecutivo
    # Ruta final: /api/dashboard/metrics/
    path('dashboard/metrics/', dashboard_metrics_api, name='api_dashboard_metrics'),

    # 4. Rutas legacy / manuales
    path('', include('ventas.urls')),
]

# 5. Routers automáticos
urlpatterns += inventario_router.urls
urlpatterns += entidades_router.urls
urlpatterns += parametros_router.urls
urlpatterns += ventas_router.urls
urlpatterns += compras_router.urls
urlpatterns += finanzas_router.urls