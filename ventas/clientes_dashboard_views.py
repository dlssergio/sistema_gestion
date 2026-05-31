from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from django.shortcuts import get_object_or_404

from .models import Cliente
from .clientes_dashboard_service import ClienteDashboardService
from .clientes_dashboard_serializers import ClienteDashboardSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def cliente_dashboard_api(request, pk):
    cliente = get_object_or_404(
        Cliente.objects.select_related('entidad', 'price_list', 'vendedor'),
        pk=pk
    )

    data = ClienteDashboardService.build_dashboard(cliente)
    serializer = ClienteDashboardSerializer(data)

    return Response(serializer.data, status=status.HTTP_200_OK)