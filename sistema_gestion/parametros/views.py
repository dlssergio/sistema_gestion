# parametros/views.py (VERSIÓN FINAL Y ROBUSTA)

from rest_framework import viewsets
# <<< INICIO DE LA CORRECCIÓN >>>
# Se importa Moneda, TipoComprobante, y los NUEVOS modelos de impuestos.
# Se elimina la importación del obsoleto 'ReglaImpuesto'.
from .models import Moneda, TipoComprobante, Impuesto, CategoriaImpositiva
from .serializers import MonedaSerializer, TipoComprobanteSerializer, ImpuestoSerializer, CategoriaImpositivaSerializer
# <<< FIN DE LA CORRECCIÓN >>>

class MonedaViewSet(viewsets.ModelViewSet):
    queryset = Moneda.objects.all()
    serializer_class = MonedaSerializer

class TipoComprobanteViewSet(viewsets.ModelViewSet):
    queryset = TipoComprobante.objects.all()
    serializer_class = TipoComprobanteSerializer

# <<< SE ELIMINA 'ReglaImpuestoViewSet' POR COMPLETO >>>

# --- ViewSets para la Nueva Arquitectura de Impuestos ---

class ImpuestoViewSet(viewsets.ModelViewSet):
    queryset = Impuesto.objects.all()
    serializer_class = ImpuestoSerializer

class CategoriaImpositivaViewSet(viewsets.ModelViewSet):
    queryset = CategoriaImpositiva.objects.all()
    serializer_class = CategoriaImpositivaSerializer