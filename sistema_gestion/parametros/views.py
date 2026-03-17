# parametros/views.py (VERSIÓN FINAL Y ROBUSTA)

from rest_framework import viewsets, mixins
from .models import Moneda, TipoComprobante, Impuesto, CategoriaImpositiva, ConfiguracionEmpresa, CargaMasiva
from .serializers import (
    MonedaSerializer, TipoComprobanteSerializer, ImpuestoSerializer,
    CategoriaImpositivaSerializer, ConfiguracionEmpresaSerializer,
    CargaMasivaSerializer
)
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from django.db import transaction
import threading # Temporalmente, hasta que enlacemos Celery en el paso 2


class MonedaViewSet(viewsets.ModelViewSet):
    """
    API endpoint que permite ver las Monedas.
    """
    queryset = Moneda.objects.all()
    serializer_class = MonedaSerializer

class TipoComprobanteViewSet(viewsets.ModelViewSet):
    """
    API endpoint que permite ver los Tipos de Comprobante.
    """
    queryset = TipoComprobante.objects.all()
    serializer_class = TipoComprobanteSerializer

# <<< SE ELIMINA 'ReglaImpuestoViewSet' POR COMPLETO >>>

# --- ViewSets para la Nueva Arquitectura de Impuestos ---

class ImpuestoViewSet(viewsets.ModelViewSet):
    queryset = Impuesto.objects.all()
    serializer_class = ImpuestoSerializer

class CategoriaImpositivaViewSet(viewsets.ModelViewSet):
    """
    API endpoint que permite ver y gestionar las Reglas de Impuesto.
    """
    queryset = CategoriaImpositiva.objects.all()
    serializer_class = CategoriaImpositivaSerializer


class ConfiguracionEmpresaView(APIView):
    """
    Devuelve la configuración de la empresa actual.
    Si no existe, devuelve vacío o un error controlado.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        config = ConfiguracionEmpresa.objects.first()
        if config:
            serializer = ConfiguracionEmpresaSerializer(config)
            return Response(serializer.data)
        return Response({"detail": "Empresa no configurada"}, status=404)


class CargaMasivaViewSet(viewsets.ModelViewSet):
    """
    API para gestionar la carga de archivos masivos y consultar su progreso.
    """
    queryset = CargaMasiva.objects.all()
    serializer_class = CargaMasivaSerializer
    parser_classes = (MultiPartParser, FormParser)  # <--- FUNDAMENTAL PARA RECIBIR ARCHIVOS

    def perform_create(self, serializer):
        carga = serializer.save(usuario=self.request.user)

        # Disparamos la tarea de Celery, enviándole el ID y el nombre del esquema (tenant)
        from .tasks import procesar_carga_masiva_task
        schema_name = self.request.tenant.schema_name

        transaction.on_commit(
            lambda: procesar_carga_masiva_task.delay(carga.id, schema_name)
        )
