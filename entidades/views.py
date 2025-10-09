# en entidades/views.py (CORREGIDO)

from rest_framework import viewsets
from ventas.models import Cliente
from compras.models import Proveedor
from .serializers import ClienteSerializer, ProveedorSerializer

class ClienteViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint que permite ver los Clientes.
    """
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    # Permitimos buscar por campos del modelo relacionado 'entidad'
    search_fields = ['entidad__razon_social', 'entidad__cuit']

class ProveedorViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint que permite ver los Proveedores.
    """
    queryset = Proveedor.objects.all()
    serializer_class = ProveedorSerializer
    search_fields = ['entidad__razon_social', 'entidad__cuit', 'nombre_fantasia', 'codigo_proveedor']