# en parametros/views.py

from rest_framework import viewsets
from .models import Moneda, TipoComprobante, Impuesto
from .serializers import MonedaSerializer, TipoComprobanteSerializer, ImpuestoSerializer

class MonedaViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint que permite ver las Monedas.
    """
    queryset = Moneda.objects.all()
    serializer_class = MonedaSerializer

class TipoComprobanteViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint que permite ver los Tipos de Comprobante.
    """
    queryset = TipoComprobante.objects.all()
    serializer_class = TipoComprobanteSerializer

class ImpuestoViewSet(viewsets.ModelViewSet):
    """
    API endpoint que permite ver y gestionar Impuestos.
    """
    queryset = Impuesto.objects.all()
    serializer_class = ImpuestoSerializer