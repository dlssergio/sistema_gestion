# en ventas/views.py (VERSIÓN FINAL CON LÓGICA DE STOCK)

from django.http import JsonResponse
from django.db import transaction
from rest_framework import viewsets, status
from rest_framework.response import Response
from django.core.exceptions import ValidationError

from inventario.models import Articulo, StockArticulo
from .models import ComprobanteVenta, ComprobanteVentaItem

from .serializers import (
    ComprobanteVentaSerializer,
    ComprobanteVentaCreateSerializer
)

# Vista antigua para el admin de Django
def get_precio_articulo(request, pk):
    try:
        articulo = Articulo.objects.get(pk=pk)
        data = {'precio': articulo.precio_venta_base}
        return JsonResponse(data)
    except Articulo.DoesNotExist:
        return JsonResponse({'error': 'Artículo no encontrado'}, status=404)


class ComprobanteVentaViewSet(viewsets.ModelViewSet):
    queryset = ComprobanteVenta.objects.all().order_by('-fecha', '-numero')
    search_fields = ['numero', 'cliente__entidad__razon_social']

    def get_serializer_class(self):
        if self.action == 'create':
            return ComprobanteVentaCreateSerializer
        return ComprobanteVentaSerializer

    # --- MÉTODO CREATE() ACTUALIZADO CON LÓGICA DE STOCK ---
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                items_data = serializer.validated_data.pop('items')

                # 1. Creamos la cabecera
                comprobante = ComprobanteVenta.objects.create(**serializer.validated_data)

                # 2. Iteramos sobre los ítems y los creamos
                for item_data in items_data:
                    item_creado = ComprobanteVentaItem.objects.create(comprobante=comprobante, **item_data)

                    # --- LÓGICA DE STOCK MOVIMIDA AQUÍ ---
                    if comprobante.estado == 'FN' and comprobante.tipo_comprobante.afecta_stock:
                        articulo = item_creado.articulo
                        if articulo.administra_stock and comprobante.deposito:

                            # Primero, validamos el stock
                            stock_item = StockArticulo.objects.select_for_update().filter(
                                articulo=articulo,
                                deposito=comprobante.deposito
                            ).first()

                            stock_disponible = stock_item.cantidad if stock_item else 0

                            if stock_disponible < item_creado.cantidad:
                                # Lanzamos una excepción que será capturada por el 'except'
                                raise ValidationError(
                                    f"Stock insuficiente para '{articulo.descripcion}' en '{comprobante.deposito.nombre}'. "
                                    f"Stock disponible: {stock_disponible}, Cantidad solicitada: {item_creado.cantidad}."
                                )

                            # Si hay stock, lo descontamos
                            stock_item.cantidad -= item_creado.cantidad
                            stock_item.save()

        except ValidationError as e:
            # Capturamos específicamente el error de validación de stock
            return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # Capturamos cualquier otro error
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        read_serializer = ComprobanteVentaSerializer(comprobante)
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)