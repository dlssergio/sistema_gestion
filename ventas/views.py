# ventas/views.py (VERSIÓN FINAL CON IMPORTACIONES CORREGIDAS)

import json
from decimal import Decimal
from django.http import JsonResponse
from django.db import transaction
from django.views.decorators.http import require_POST
from django.contrib.admin.views.decorators import staff_member_required
from rest_framework import viewsets, status
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
# --- INICIO DE LA CORRECCIÓN ---
# 1. Se mueve la importación de dataclasses al bloque de importaciones superior.
from dataclasses import asdict as dc_asdict
# --- FIN DE LA CORRECCIÓN ---

# Modelos
from inventario.models import Articulo, StockArticulo
from .models import ComprobanteVenta, ComprobanteVentaItem, Cliente
from parametros.models import TipoComprobante

# Servicios y Serializers
from .services import TaxCalculatorService, PricingService
from .serializers import ComprobanteVentaSerializer, ComprobanteVentaCreateSerializer



# --- Vistas de API para el Admin ---

@staff_member_required
def get_precio_articulo(request, pk):
    """
    Vista de fallback que devuelve el precio de venta base de un artículo.
    """
    try:
        articulo = Articulo.objects.get(pk=pk)
        data = {'precio': str(articulo.precio_venta.amount)}
        return JsonResponse(data)
    except Articulo.DoesNotExist:
        return JsonResponse({'error': 'Artículo no encontrado'}, status=404)


@staff_member_required
def get_precio_articulo_cliente(request, cliente_pk, articulo_pk):
    """
    Vista de API que devuelve el desglose de precios completo para un artículo y cliente.
    """
    try:
        articulo = get_object_or_404(Articulo, pk=articulo_pk)
        cliente = get_object_or_404(Cliente, pk=cliente_pk)
        cantidad = Decimal(request.GET.get('cantidad', '1'))

        pricing_data = PricingService.get_product_pricing(articulo, cliente, cantidad)
        data = dc_asdict(pricing_data)

        def format_for_json(obj):
            if isinstance(obj, Money):
                return {'amount': f"{obj.amount:.2f}", 'currency': obj.currency.code}
            if isinstance(obj, Decimal):
                return f"{obj:.2f}"
            if isinstance(obj, dict):
                return {k: format_for_json(v) for k, v in obj.items()}
            return obj

        json_safe_data = {k: format_for_json(v) for k, v in data.items()}

        return JsonResponse(json_safe_data)
    except Exception as e:
        # Añadimos un log para poder ver el error real en la consola del servidor
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=400)


@staff_member_required
@require_POST
def calcular_totales_api(request):
    # ... (Esta función no necesita cambios, pero se incluye para que el archivo esté completo)
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
            def items(self): return self

            def all(self): return self.items_list

        fake_comprobante = FakeComprobante(items_data)
        subtotal = sum(item.subtotal for item in fake_comprobante.all())

        desglose_impuestos = TaxCalculatorService.calcular_impuestos_comprobante(fake_comprobante, 'venta')
        total_impuestos = sum(desglose_impuestos.values())
        total = subtotal + total_impuestos

        return JsonResponse({
            'subtotal': f"{subtotal:,.2f}",
            'impuestos': {k: f"{v:,.2f}" for k, v in desglose_impuestos.items()},
            'total': f"{total:,.2f}",
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# --- ViewSet para la API REST pública ---

class ComprobanteVentaViewSet(viewsets.ModelViewSet):
    from .serializers import ComprobanteVentaSerializer, ComprobanteVentaCreateSerializer  # Importación local

    queryset = ComprobanteVenta.objects.all().order_by('-fecha', '-numero')
    search_fields = ['numero', 'cliente__entidad__razon_social']

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
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
                        articulo = item_creado.articulo
                        cantidad_a_descontar = item_creado.cantidad
                        deposito_venta = comprobante.deposito

                        if not deposito_venta:
                            raise ValidationError("No se ha especificado un depósito para la venta.")

                        stock_obj = StockArticulo.objects.select_for_update().get(
                            articulo=articulo,
                            deposito=deposito_venta
                        )

                        if stock_obj.cantidad < cantidad_a_descontar:
                            raise ValidationError(
                                f"Stock insuficiente para {articulo.descripcion}. Disponible: {stock_obj.cantidad}, Solicitado: {cantidad_a_descontar}")

                        stock_obj.cantidad -= cantidad_a_descontar
                        stock_obj.save()

        except ValidationError as e:
            return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
        except Articulo.DoesNotExist:
            return Response({'error': 'Uno de los artículos en el comprobante no existe.'},
                            status=status.HTTP_400_BAD_REQUEST)
        except StockArticulo.DoesNotExist:
            # item_data no es accesible aquí, pero podemos dar un mensaje genérico.
            return Response({
                                'error': f"Uno de los artículos no tiene un registro de stock en el depósito especificado. Por favor, cree el registro de stock primero."},
                            status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': f"Error inesperado en el servidor: {str(e)}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        read_serializer = ComprobanteVentaSerializer(comprobante)
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)