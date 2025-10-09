# en compras/views.py (VERSIÓN FINAL CON LÓGICA DE STOCK)

from django.db import transaction
from rest_framework import viewsets, status
from rest_framework.response import Response

# Importamos los modelos que necesitamos para la lógica
from .models import ComprobanteCompra, ComprobanteCompraItem
from inventario.models import StockArticulo

from .serializers import (
    ComprobanteCompraSerializer,
    ComprobanteCompraCreateSerializer
)

class ComprobanteCompraViewSet(viewsets.ModelViewSet):
    queryset = ComprobanteCompra.objects.all().order_by('-fecha', '-numero')

    def get_serializer_class(self):
        if self.action == 'create':
            return ComprobanteCompraCreateSerializer
        return ComprobanteCompraSerializer

    # --- MÉTODO CREATE() ACTUALIZADO CON LÓGICA DE STOCK ---
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                items_data = serializer.validated_data.pop('items')

                # 1. Creamos la cabecera
                comprobante = ComprobanteCompra.objects.create(**serializer.validated_data)

                # 2. Iteramos sobre los ítems y los creamos
                for item_data in items_data:
                    # Creamos el ComprobanteCompraItem
                    item_creado = ComprobanteCompraItem.objects.create(comprobante=comprobante, **item_data)

                    # --- LÓGICA DE STOCK MOVIMIDA AQUÍ ---
                    # Si el comprobante es finalizado y afecta stock...
                    if comprobante.estado == 'FN' and comprobante.tipo_comprobante.afecta_stock:
                        articulo = item_creado.articulo
                        if articulo.administra_stock and comprobante.deposito:
                            stock_item, created = StockArticulo.objects.select_for_update().get_or_create(
                                articulo=articulo,
                                deposito=comprobante.deposito,
                                defaults={'cantidad': 0}
                            )
                            stock_item.cantidad += item_creado.cantidad
                            stock_item.save()

                        # Actualizamos el precio de costo del artículo
                        articulo.precio_costo_original = item_creado.precio_costo_unitario_original
                        articulo.moneda_costo = item_creado.moneda_costo
                        articulo.save() # Esto recalcula precios de venta, etc.

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        read_serializer = ComprobanteCompraSerializer(comprobante)
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)