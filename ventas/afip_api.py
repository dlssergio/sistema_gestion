# ventas/views.py (o ventas/afip_api.py)

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db import connection

from .models import ComprobanteVenta
from .tasks import tarea_solicitar_cae

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reintentar_cae_api(request, pk):
    """
    Endpoint para reintentar manualmente la solicitud de CAE ante AFIP.
    Ideal para consumir desde un Frontend en Vue.js.
    """
    comp = get_object_or_404(ComprobanteVenta, pk=pk)

    # Validaciones de negocio
    if comp.estado != ComprobanteVenta.Estado.CONFIRMADO:
        return Response(
            {"detail": "El comprobante debe estar confirmado para solicitar CAE."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if comp.cae:
        return Response(
            {"detail": f"El comprobante ya posee el CAE: {comp.cae}"},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not (comp.serie and comp.serie.solicitar_cae_automaticamente):
        return Response(
            {"detail": "La serie de este comprobante no es electrónica."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Obtenemos el tenant y despachamos a Celery
    schema = connection.schema_name
    tarea_solicitar_cae.delay(comp.pk, schema)

    # 202 ACCEPTED es el estándar HTTP para "Procesamiento Asíncrono Aceptado"
    return Response(
        {"detail": "Solicitud enviada a la cola. El comprobante se actualizará en breve."},
        status=status.HTTP_202_ACCEPTED
    )