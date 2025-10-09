# en compras/urls.py (NUEVO ARCHIVO)

from rest_framework.routers import DefaultRouter
from .views import ComprobanteCompraViewSet

# El router se encarga de todo, igual que en las otras apps
router = DefaultRouter()
router.register(r'comprobantes-compra', ComprobanteCompraViewSet, basename='comprobantecompra')

# No necesitamos urlpatterns aquí, solo exportar el router