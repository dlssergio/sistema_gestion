from django.contrib.auth import get_user_model
from django.db import models
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from entidades.models import SituacionIVA
from ventas.models import Cliente, PriceList

from .clientes_admin_serializers import (
    ClienteAdminDetailSerializer,
    ClienteAdminListSerializer,
    ClienteAdminWriteSerializer,
    PriceListOptionSerializer,
    SituacionIVAOptionSerializer,
    UserOptionSerializer,
)

User = get_user_model()


def _to_bool(value):
    if value in (True, False):
        return value
    if value is None:
        return None
    value = str(value).strip().lower()
    if value in ('1', 'true', 't', 'yes', 'si', 'sí'):
        return True
    if value in ('0', 'false', 'f', 'no'):
        return False
    return None


class ClienteAdminViewSet(viewsets.ModelViewSet):
    queryset = Cliente.objects.select_related(
        'entidad',
        'entidad__situacion_iva',
        'price_list',
        'vendedor',
    ).order_by('entidad__razon_social')

    filter_backends = [filters.OrderingFilter]
    ordering_fields = [
        'codigo_cliente',
        'entidad__razon_social',
        'entidad__cuit',
        'fecha_alta',
        'limite_credito',
    ]
    ordering = ['entidad__razon_social']

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params

        search = (p.get('search') or '').strip()
        if search:
            qs = qs.filter(
                models.Q(codigo_cliente__icontains=search) |
                models.Q(entidad__razon_social__icontains=search) |
                models.Q(nombre_fantasia__icontains=search) |
                models.Q(entidad__cuit__icontains=search) |
                models.Q(entidad__email__icontains=search) |
                models.Q(contacto_nombre__icontains=search) |
                models.Q(contacto_email__icontains=search)
            ).distinct()

        estado = (p.get('estado') or '').strip().lower()
        if estado == 'activos':
            qs = qs.filter(is_active=True)
        elif estado == 'inactivos':
            qs = qs.filter(is_active=False)

        categoria = p.get('categoria')
        if categoria:
            qs = qs.filter(categoria=categoria)

        situacion_iva = p.get('situacion_iva')
        if situacion_iva:
            qs = qs.filter(entidad__situacion_iva_id=situacion_iva)

        vendedor = p.get('vendedor')
        if vendedor:
            qs = qs.filter(vendedor_id=vendedor)

        price_list = p.get('price_list')
        if price_list:
            qs = qs.filter(price_list_id=price_list)

        permite_cta_cte = _to_bool(p.get('permite_cta_cte'))
        if permite_cta_cte is not None:
            qs = qs.filter(permite_cta_cte=permite_cta_cte)

        return qs

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ClienteAdminWriteSerializer
        if self.action == 'retrieve':
            return ClienteAdminDetailSerializer
        return ClienteAdminListSerializer

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=['is_active'])

    @action(detail=True, methods=['post'])
    def activar(self, request, pk=None):
        cliente = self.get_object()
        cliente.is_active = True
        cliente.save(update_fields=['is_active'])
        return Response({'ok': True}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def desactivar(self, request, pk=None):
        cliente = self.get_object()
        cliente.is_active = False
        cliente.save(update_fields=['is_active'])
        return Response({'ok': True}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def clientes_admin_meta_situaciones_iva_api(request):
    qs = SituacionIVA.objects.all().order_by('codigo', 'nombre')
    return Response(SituacionIVAOptionSerializer(qs, many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def clientes_admin_meta_categorias_api(request):
    data = [
        {'value': value, 'label': label}
        for value, label in Cliente.Categoria.choices
    ]
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def clientes_admin_meta_vendedores_api(request):
    qs = User.objects.filter(is_active=True).order_by('first_name', 'last_name', 'username')
    return Response(UserOptionSerializer(qs, many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def clientes_admin_meta_price_lists_api(request):
    qs = PriceList.objects.all().order_by('id')
    return Response(PriceListOptionSerializer(qs, many=True).data)