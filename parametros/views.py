# parametros/views.py (VERSIÓN FINAL Y ROBUSTA)

from rest_framework import viewsets
from .models import Moneda, TipoComprobante, Impuesto, CategoriaImpositiva, ConfiguracionEmpresa
from .serializers import (
    MonedaSerializer, TipoComprobanteSerializer, ImpuestoSerializer,
    CategoriaImpositivaSerializer, ConfiguracionEmpresaSerializer
)
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny



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
