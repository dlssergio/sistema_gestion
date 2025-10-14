from rest_framework import viewsets
# <<< CAMBIO CLAVE: Eliminamos 'Impuesto' y añadimos 'ReglaImpuesto' >>>
from .models import Moneda, TipoComprobante, ReglaImpuesto
# <<< CAMBIO CLAVE: Eliminamos 'ImpuestoSerializer' y añadimos 'ReglaImpuestoSerializer' >>>
from .serializers import MonedaSerializer, TipoComprobanteSerializer, ReglaImpuestoSerializer

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

# <<< CAMBIO CLAVE: Eliminamos el ImpuestoViewSet obsoleto >>>
# class ImpuestoViewSet(viewsets.ModelViewSet):
#     """
#     API endpoint que permite ver y gestionar Impuestos.
#     """
#     queryset = Impuesto.objects.all()
#     serializer_class = ImpuestoSerializer

# <<< AÑADIMOS EL NUEVO VIEWSET PARA REGLAS DE IMPUESTO >>>
class ReglaImpuestoViewSet(viewsets.ModelViewSet):
    """
    API endpoint que permite ver y gestionar las Reglas de Impuesto.
    """
    queryset = ReglaImpuesto.objects.all()
    serializer_class = ReglaImpuestoSerializer