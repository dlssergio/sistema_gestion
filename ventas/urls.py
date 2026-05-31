from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views
from .clientes_dashboard_views import cliente_dashboard_api

router = DefaultRouter()
router.register(r'comprobantes-venta', views.ComprobanteVentaViewSet, basename='comprobanteventa')

urlpatterns = [
    # Utilidades
    path('get-precio-articulo/<str:pk>/', views.get_precio_articulo, name='get_precio_articulo'),

    # Comprobantes: PDF / email
    path('comprobantes-venta/<int:pk>/pdf/', views.generar_pdf_venta_api, name='venta_pdf_api'),
    path('comprobantes-venta/<int:pk>/enviar-email/', views.enviar_email_comprobante_api, name='venta_email_api'),
    path('clientes-admin/informe-saldos/', views.informe_saldos_clientes_api, name='informe_saldos_clientes'),
    path('clientes-admin/<int:pk>/enviar-estado-cuenta/', views.enviar_estado_cuenta_email_api,
         name='enviar_estado_cuenta'),
    path('dashboard-ventas/', views.dashboard_ventas_api, name='dashboard_ventas'),
    path('comprobantes-venta/<int:pk>/convertir/', views.convertir_comprobante_api, name='convertir_comprobante'),
    path('comprobantes-venta/<int:pk>/reglas-conversion/', views.reglas_conversion_para_comprobante_api,
         name='reglas_conversion_comprobante'),

    # Dashboard cliente 360°
    path('clientes-admin/<int:pk>/dashboard/', cliente_dashboard_api, name='cliente-dashboard-api'),

    # Router DRF
    path('', include(router.urls)),
]