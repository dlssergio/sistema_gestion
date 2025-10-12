from django.db import transaction
from rest_framework import viewsets, status
from rest_framework.response import Response
from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required

from .models import ComprobanteCompra, ComprobanteCompraItem
from inventario.models import StockArticulo, Articulo
from .serializers import ComprobanteCompraSerializer, ComprobanteCompraCreateSerializer


class ComprobanteCompraViewSet(viewsets.ModelViewSet):
    queryset = ComprobanteCompra.objects.all().order_by('-fecha', '-numero')

    def get_serializer_class(self):
        if self.action == 'create':
            return ComprobanteCompraCreateSerializer
        return ComprobanteCompraSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                items_data = serializer.validated_data.pop('items')
                comprobante = ComprobanteCompra.objects.create(**serializer.validated_data)

                for item_data in items_data:
                    item_creado = ComprobanteCompraItem.objects.create(comprobante=comprobante, **item_data)

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

                        articulo.precio_costo = item_creado.precio_costo_unitario
                        articulo.save()

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        read_serializer = ComprobanteCompraSerializer(comprobante)
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)


@staff_member_required
def get_articulo_costo_json(request, articulo_pk):
    """
    Vista de API interna para el admin que devuelve el costo de un artículo,
    respetando el sistema de Monedas personalizado.
    """
    try:
        articulo = Articulo.objects.get(pk=articulo_pk)
        costo = articulo.precio_costo

        # --- CAMBIO CLAVE ---
        # django-money crea un campo oculto ForeignKey a nuestro modelo Moneda
        # cuando se configura correctamente. Obtenemos su ID.
        moneda_id = None
        if hasattr(articulo, 'precio_costo_currency_id') and articulo.precio_costo_currency_id:
            moneda_id = articulo.precio_costo_currency_id

        return JsonResponse({
            'amount': f"{costo.amount:.2f}",
            'currency_id': moneda_id  # <<< Enviamos el ID de tu modelo Moneda
        })
    except Articulo.DoesNotExist:
        return JsonResponse({'error': 'Artículo no encontrado'}, status=404)
    except Exception as e:
        print(f"Error en get_articulo_costo_json: {e}")
        return JsonResponse({'error': 'Error interno del servidor'}, status=500)