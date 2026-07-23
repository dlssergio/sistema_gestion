from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views
from .clientes_dashboard_views import cliente_dashboard_api
from .cuenta_corriente_api import (
    cuenta_corriente_api,
    comprobantes_impagos_api,
    recibos_cliente_api,
    resumen_cartera_api,
)
from .afip_api import reintentar_cae_api

router = DefaultRouter()
router.register(r'comprobantes-venta', views.ComprobanteVentaViewSet, basename='comprobanteventa')

urlpatterns = [
    path('get-precio-articulo/<str:pk>/', views.get_precio_articulo, name='get_precio_articulo'),
    path('comprobantes-venta/<int:pk>/pdf/', views.generar_pdf_venta_api, name='venta_pdf_api'),
    path('comprobantes-venta/<int:pk>/enviar-email/', views.enviar_email_comprobante_api, name='venta_email_api'),
    path('clientes-admin/informe-saldos/', views.informe_saldos_clientes_api, name='informe_saldos_clientes'),
    path('clientes-admin/resumen-cartera/', resumen_cartera_api, name='resumen-cartera'),
    path('clientes-admin/<int:pk>/enviar-estado-cuenta/', views.enviar_estado_cuenta_email_api, name='enviar_estado_cuenta'),
    path('clientes-admin/<int:pk>/dashboard/', cliente_dashboard_api, name='cliente-dashboard-api'),
    path('clientes-admin/<int:pk>/cuenta-corriente/', cuenta_corriente_api, name='cliente-cuenta-corriente'),
    path('clientes-admin/<int:pk>/comprobantes-impagos/', comprobantes_impagos_api, name='cliente-comprobantes-impagos'),
    path('clientes-admin/<int:pk>/recibos/', recibos_cliente_api, name='cliente-recibos'),
    path('clientes-admin/<int:pk>/enviar-estado-cuenta/', views.enviar_estado_cuenta_email_api, name='enviar_estado_cuenta'),
    path('dashboard-ventas/', views.dashboard_ventas_api, name='dashboard_ventas'),
    path('comprobantes-venta/<int:pk>/convertir/', views.convertir_comprobante_api, name='convertir_comprobante'),
    path('comprobantes-venta/<int:pk>/reglas-conversion/', views.reglas_conversion_para_comprobante_api, name='reglas_conversion_comprobante'),
    # Endpoint para el botón "Reintentar AFIP" en Vue
    #path('comprobantes/<int:pk>/reintentar-cae/', reintentar_cae_api, name='reintentar-cae'),
    path('', include(router.urls)),
]