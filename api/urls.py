from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

# Routers de las Apps
# NOTA: inventario se incluye con include() completo para soportar
# rutas manuales (nested ProveedorArticulo) además del router automático.
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
    path('dashboard/metrics/', dashboard_metrics_api, name='api_dashboard_metrics'),

    # 4. Inventario — include completo para que las rutas nested funcionen
    path('', include('inventario.urls')),

    # 5. Rutas legacy / manuales
    path('', include('ventas.urls')),

    # 6. Incluir urlpatterns manuales de entidades
    path('', include('entidades.urls')),
]

# 7. Routers automáticos
urlpatterns += parametros_router.urls
urlpatterns += ventas_router.urls
urlpatterns += compras_router.urls
urlpatterns += [path('finanzas/', include(finanzas_router.urls))]