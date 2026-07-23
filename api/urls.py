from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

# Routers de las Apps
from entidades.urls import router as entidades_router
from parametros.urls import router as parametros_router
from ventas.urls import router as ventas_router
# from compras.urls import router as compras_router  <-- Ya no lo importamos así
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

    # 4. Apps con rutas mixtas (Router + Vistas Manuales)
    # Al hacer include('app.urls'), Django lee TODO el archivo urls.py de esa app.
    path('', include('inventario.urls')),
    path('', include('ventas.urls')),
    path('', include('entidades.urls')),
    path('', include('compras.urls')), # <-- ¡AQUÍ ESTÁ LA MAGIA! Ahora leerá proveedores-admin/
]

# 5. Routers automáticos puros (apps que no tienen vistas manuales o se incluyen diferente)
urlpatterns += parametros_router.urls
urlpatterns += ventas_router.urls
urlpatterns += [path('finanzas/', include(finanzas_router.urls))]