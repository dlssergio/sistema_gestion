# entidades/views.py

from rest_framework import viewsets
from rest_framework.filters import SearchFilter, OrderingFilter

from ventas.models import Cliente
from compras.models import Proveedor
from .serializers import ClienteSerializer, ProveedorSerializer

from guardian.shortcuts import get_objects_for_user


class ClienteViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint que permite ver los Clientes.
    """
    queryset = Cliente.objects.all().order_by('entidad__razon_social')
    serializer_class = ClienteSerializer

    # ✅ Esto es lo que faltaba: DRF necesita filter_backends para usar ?search=
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['entidad__razon_social', 'entidad__cuit', 'codigo_cliente']
    ordering_fields = ['entidad__razon_social', 'entidad__cuit']
    ordering = ['entidad__razon_social']


class ProveedorViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint que permite ver los Proveedores.
    ¡AHORA USA EL MOTOR DE PERMISOS DE DJANGO-GUARDIAN!
    """
    serializer_class = ProveedorSerializer

    # ✅ idem: habilitar ?search=
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['entidad__razon_social', 'entidad__cuit', 'nombre_fantasia', 'codigo_proveedor']
    ordering_fields = ['entidad__razon_social', 'entidad__cuit', 'nombre_fantasia', 'codigo_proveedor']
    ordering = ['entidad__razon_social']

    def get_queryset(self):
        """
        Este método ahora filtra los proveedores basándose en los permisos
        a nivel de objeto que hemos asignado.
        """
        user = self.request.user

        # El superusuario siempre puede ver todo.
        if user.is_superuser:
            return Proveedor.objects.all().order_by('entidad__razon_social')

        # <<< 2. LA LÓGICA DE GUARDIAN >>>
        # Le pedimos a guardian que nos devuelva una lista de todos los objetos 'Proveedor'
        # para los cuales el usuario actual tiene el permiso de 'view_proveedor'.
        # El formato es siempre 'app_label.view_modelname'.
        return get_objects_for_user(user, 'compras.view_proveedor').order_by('entidad__razon_social')