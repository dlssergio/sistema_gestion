from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .services import DashboardService

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_metrics_api(request):
    """
    API que devuelve los KPIs y datos para gráficos del Dashboard Ejecutivo.
    """
    try:
        # Llamamos al servicio que ya calcula todo
        metrics = DashboardService.get_metricas_financieras()
        return Response(metrics)
    except Exception as e:
        print(f"Error calculando métricas: {e}")
        return Response({'error': 'No se pudieron obtener las métricas'}, status=500)