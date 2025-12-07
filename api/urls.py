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

# --- IMPORTACIÓN NUEVA ---
from parametros.views import ConfiguracionEmpresaView

urlpatterns = [
    # 1. Autenticación
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # 2. Configuración de Empresa (Ruta Manual)
    # Esta es la línea que faltaba para conectar el cable
    path('parametros/configuracion/', ConfiguracionEmpresaView.as_view(), name='configuracion-empresa'),

    # 3. Rutas Legacy (si las hay)
    path('', include('ventas.urls')),
]

# 4. Sumar Rutas Automáticas (ViewSets)
urlpatterns += inventario_router.urls
urlpatterns += entidades_router.urls
urlpatterns += parametros_router.urls
urlpatterns += ventas_router.urls
urlpatterns += compras_router.urls