# en api/urls.py (Versión Completa y Limpia)

from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from inventario.urls import router as inventario_router
from entidades.urls import router as entidades_router
from parametros.urls import router as parametros_router
from ventas.urls import router as ventas_router
from compras.urls import router as compras_router

# Combinamos todas las URLs
urlpatterns = [
    # Endpoints de Autenticación
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Endpoints de la App (incluyendo la ruta legacy que teníamos)
    path('', include('ventas.urls')),
]

# Añadimos las URLs de los routers
urlpatterns += inventario_router.urls
urlpatterns += entidades_router.urls
urlpatterns += parametros_router.urls
urlpatterns += ventas_router.urls
urlpatterns += compras_router.urls