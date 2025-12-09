# en ventas/urls.py (Refactorizado)

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Ya no necesitamos app_name = 'ventas' porque no usaremos namespaces aquí
# app_name = 'ventas'

router = DefaultRouter()
router.register(r'comprobantes-venta', views.ComprobanteVentaViewSet, basename='comprobanteventa')

urlpatterns = [
    # La ruta ahora es relativa, sin 'api/'.
    # La URL final será /api/get-precio-articulo/...
    path('get-precio-articulo/<str:pk>/', views.get_precio_articulo, name='get_precio_articulo'),

    # --- NUEVA RUTA PARA PDF ---
    path('comprobantes-venta/<int:pk>/pdf/', views.generar_pdf_venta_api, name='venta_pdf_api'),

    # El router principal se incluye sin prefijo
    path('', include(router.urls)),
]