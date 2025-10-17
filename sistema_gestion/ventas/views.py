# ventas/views.py (VERSIÓN CON IMPORTACIÓN CORREGIDA)

import json
from decimal import Decimal
from django.http import JsonResponse
from django.db import transaction
from django.views.decorators.http import require_POST
from django.contrib.admin.views.decorators import staff_member_required
from rest_framework import viewsets, status
from rest_framework.response import Response
from django.core.exceptions import ValidationError

from inventario.models import Articulo, StockArticulo
# --- INICIO DE LA CORRECCIÓN ---
# Se importan los modelos que SÍ pertenecen a la app 'ventas'
from .models import ComprobanteVenta, ComprobanteVentaItem
# Se importa 'TipoComprobante' desde su ubicación correcta en la app 'parametros'
from parametros.models import TipoComprobante
# --- FIN DE LA CORRECCIÓN ---
from .serializers import ComprobanteVentaSerializer, ComprobanteVentaCreateSerializer
from .services import TaxCalculatorService


@staff_member_required
def get_precio_articulo(request, pk):
    try:
        articulo = Articulo.objects.get(pk=pk)
        data = {'precio': str(articulo.precio_venta.amount)}
        return JsonResponse(data)
    except Articulo.DoesNotExist:
        return JsonResponse({'error': 'Artículo no encontrado'}, status=404)


@staff_member_required
@require_POST
def calcular_totales_api(request):
    try:
        data = json.loads(request.body)
        items_data = data.get('items', [])

        class FakeItem:
            def __init__(self, data):
                self.articulo = Articulo.objects.get(pk=data.get('articulo'))
                self.cantidad = Decimal(data.get('cantidad', '0'))
                self.precio_unitario_original = Decimal(data.get('precio', '0'))

            @property
            def subtotal(self):
                return self.cantidad * self.precio_unitario_original

        class FakeComprobante:
            def __init__(self, items_data):
                self.items_list = [FakeItem(item) for item in items_data if item.get('articulo')]
                tipo_comprobante_id = data.get('tipo_comprobante')
                self.tipo_comprobante = TipoComprobante.objects.get(
                    pk=tipo_comprobante_id) if tipo_comprobante_id else None

            @property
            def items(self):
                return self

            def all(self):
                return self.items_list

        fake_comprobante = FakeComprobante(items_data)
        subtotal = sum(item.subtotal for item in fake_comprobante.all())

        desglose_impuestos = TaxCalculatorService.calcular_impuestos_comprobante(fake_comprobante)
        total_impuestos = sum(desglose_impuestos.values())
        total = subtotal + total_impuestos

        return JsonResponse({
            'subtotal': f"{subtotal:,.2f}",
            'impuestos': {k: f"{v:,.2f}" for k, v in desglose_impuestos.items()},
            'total': f"{total:,.2f}",
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


class ComprobanteVentaViewSet(viewsets.ModelViewSet):
    # ... (El resto de la clase se mantiene igual) ...
    queryset = ComprobanteVenta.objects.all().order_by('-fecha', '-numero')
    search_fields = ['numero', 'cliente__entidad__razon_social']

    def get_serializer_class(self):
        if self.action == 'create':
            return ComprobanteVentaCreateSerializer
        return ComprobanteVentaSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                items_data = serializer.validated_data.pop('items')
                comprobante = ComprobanteVenta.objects.create(**serializer.validated_data)
                for item_data in items_data:
                    item_creado = ComprobanteVentaItem.objects.create(comprobante=comprobante, **item_data)
                    if comprobante.estado == 'FN' and comprobante.tipo_comprobante.afecta_stock:
                        # ... Lógica de stock ...
                        pass
        except ValidationError as e:
            return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        read_serializer = ComprobanteVentaSerializer(comprobante)
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)