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

# --- IMPORTACIONES MANUALES ---
from parametros.views import ConfiguracionEmpresaView
# 1. IMPORTAR LA VISTA DE FINANZAS
from finanzas.views import dashboard_metrics_api

urlpatterns = [
    # 1. Autenticación
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # 2. Configuración de Empresa
    path('parametros/configuracion/', ConfiguracionEmpresaView.as_view(), name='configuracion-empresa'),

    # 3. Dashboard Ejecutivo (NUEVA RUTA)
    # Como este archivo ya está bajo el prefijo 'api/', la ruta final será 'api/dashboard/metrics/'
    path('dashboard/metrics/', dashboard_metrics_api, name='api_dashboard_metrics'),

    # 4. Rutas Legacy
    path('', include('ventas.urls')),
]

# 5. Sumar Rutas Automáticas
urlpatterns += inventario_router.urls
urlpatterns += entidades_router.urls
urlpatterns += parametros_router.urls
urlpatterns += ventas_router.urls
urlpatterns += compras_router.urls