# parametros/views.py (VERSIÓN FINAL Y ROBUSTA)

from rest_framework import viewsets, mixins
from .models import Moneda, TipoComprobante, Impuesto, CategoriaImpositiva, ConfiguracionEmpresa, CargaMasiva, UnidadMedida, SerieDocumento, ReglaConversionComprobante
from .serializers import (
    MonedaSerializer, TipoComprobanteSerializer, ImpuestoSerializer,
    CategoriaImpositivaSerializer, ConfiguracionEmpresaSerializer,
    CargaMasivaSerializer, ReglaConversionSerializer
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


# ─────────────────────────────────────────────
#  UNIDADES DE MEDIDA (necesario para formulario de artículos)
# ─────────────────────────────────────────────

from rest_framework import serializers as drf_serializers


class UnidadMedidaSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = UnidadMedida
        fields = ['id', 'nombre', 'simbolo']


class UnidadMedidaViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/unidades-medida/     — lista todas las unidades
    GET /api/unidades-medida/{id}/
    """
    queryset         = UnidadMedida.objects.all().order_by('nombre')
    serializer_class = UnidadMedidaSerializer


class SerieDocumentoSerializer(drf_serializers.ModelSerializer):
    tipo_display = drf_serializers.CharField(source='get_tipo_comprobante_display', read_only=True)

    class Meta:
        model = SerieDocumento
        fields = ['id', 'nombre', 'tipo_comprobante', 'tipo_display',
                  'punto_venta', 'ultimo_numero', 'es_manual', 'activo']


class SerieDocumentoViewSet(viewsets.ModelViewSet):
    """
    CRUD /api/series/   — series (talonarios) de comprobantes
    """
    serializer_class = SerieDocumentoSerializer

    def get_queryset(self):
        qs = SerieDocumento.objects.all().order_by('nombre')
        activo = self.request.query_params.get('activo')
        if activo is not None:
            qs = qs.filter(activo=(activo.lower() == 'true'))
        clase = self.request.query_params.get('clase')
        if clase:
            qs = qs.filter(tipo_comprobante__clase=clase)
        return qs


class ReglaConversionViewSet(viewsets.ModelViewSet):
    queryset = ReglaConversionComprobante.objects.select_related(
        'tipo_origen', 'tipo_destino'
    ).order_by('orden', 'tipo_origen__nombre')
    serializer_class = ReglaConversionSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        origen = self.request.query_params.get('tipo_origen')
        if origen:
            qs = qs.filter(tipo_origen_id=origen, activo=True)
        activo = self.request.query_params.get('activo')
        if activo is not None:
            qs = qs.filter(activo=activo.lower() in ('true', '1', 'yes'))
        return qs