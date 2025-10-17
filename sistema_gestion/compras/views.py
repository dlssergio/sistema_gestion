# compras/views.py (VERSIÓN ACTUALIZADA PARA LA NUEVA ARQUITECTURA)

import json
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.admin.views.decorators import staff_member_required
from djmoney.money import Money
from rest_framework import viewsets
from django.shortcuts import get_object_or_404

# --- Modelos ---
# <<< CORRECCIÓN: Ya no importamos 'PrecioProveedorArticulo' >>>
from .models import ComprobanteCompra
from inventario.models import Articulo
from parametros.models import Moneda, TipoComprobante

# --- Servicios ---
# Importamos los servicios que contienen la lógica de negocio.
from ventas.services import TaxCalculatorService
# <<< ¡CRÍTICO! Aún no hemos creado el PriceListService, así que usaremos CostCalculatorService por ahora >>>
from compras.services import CostCalculatorService


class ComprobanteCompraViewSet(viewsets.ModelViewSet):
    # (Este ViewSet no se ve afectado por los cambios, se mantiene igual)
    queryset = ComprobanteCompra.objects.all().order_by('-fecha', '-numero')
    # ... el resto de tu implementación de ViewSet si la tienes ...
    # serializer_class = ComprobanteCompraSerializer # Descomentar cuando lo creemos


@staff_member_required
def get_precio_proveedor_json(request, proveedor_pk, articulo_pk):
    """
    Busca el costo más relevante para un artículo de un proveedor específico.
    Esta es la VISTA CLAVE que utiliza la nueva lógica de precios.
    """
    try:
        articulo = get_object_or_404(Articulo, pk=articulo_pk)
        cantidad_a_comprar = Decimal(request.GET.get('cantidad', 1))

        # 1. Utilizamos el SERVICIO para obtener el precio (abstracción)
        #    En el futuro, este servicio usará las nuevas listas de precios.
        #    Por ahora, se mantiene compatible con el modelo viejo si existe.
        item_precio = CostCalculatorService.get_latest_price(
            proveedor_pk=proveedor_pk,
            articulo_pk=articulo_pk,
            cantidad=cantidad_a_comprar
        )

        if item_precio:
            # 2. Si se encuentra un precio, calculamos su costo efectivo
            costo_efectivo = CostCalculatorService.calculate_effective_cost(item_precio)
            source_info = 'Precio de Proveedor (Sistema Actual)'
        else:
            # 3. Fallback: si no hay precio de proveedor, usamos el costo base del artículo
            costo_efectivo = articulo.precio_costo
            source_info = 'Costo Base del Artículo (Fallback)'

        moneda_id = Moneda.objects.get(simbolo=costo_efectivo.currency.code).id

        return JsonResponse({
            'amount': f"{costo_efectivo.amount:.4f}",
            'currency_code': costo_efectivo.currency.code,
            'currency_id': moneda_id,
            'source': source_info
        })

    except Moneda.DoesNotExist:
        return JsonResponse({'error': 'CONFIG_ERROR', 'message': 'Moneda no encontrada en parámetros.'}, status=500)
    except Exception as e:
        return JsonResponse({'error': 'SERVER_ERROR', 'message': f'Error al procesar el precio: {str(e)}'}, status=500)


@staff_member_required
@require_POST
def calcular_totales_compra_api(request):
    # (Esta vista no se ve afectada por los cambios, se mantiene igual)
    try:
        data = json.loads(request.body)
        items_data = data.get('items', [])

        class FakeItem:
            def __init__(self, data):
                self.articulo = Articulo.objects.get(pk=data.get('articulo'))
                self.cantidad = Decimal(data.get('cantidad', '0'))
                monto = Decimal(data.get('precio_monto', '0'))
                # Asumimos que el ID de la moneda viene en el payload
                moneda_simbolo = Moneda.objects.get(pk=data.get('precio_moneda_id')).simbolo
                self.precio_costo_unitario = Money(monto, moneda_simbolo)

            @property
            def subtotal(self): return self.cantidad * self.precio_costo_unitario

        class FakeComprobante:
            def __init__(self, items_data):
                self.items_list = [FakeItem(item) for item in items_data if item.get('articulo')]
                tipo_comprobante_id = data.get('tipo_comprobante')
                self.tipo_comprobante = TipoComprobante.objects.get(pk=tipo_comprobante_id) if tipo_comprobante_id else None
            @property
            def items(self): return self
            def all(self): return self.items_list

        fake_comprobante = FakeComprobante(items_data)
        subtotal_currency = 'ARS'
        if fake_comprobante.all(): subtotal_currency = fake_comprobante.all()[0].subtotal.currency.code
        subtotal = sum((item.subtotal for item in fake_comprobante.all()), Money(0, subtotal_currency))
        desglose_impuestos = TaxCalculatorService.calcular_impuestos_comprobante(fake_comprobante, 'compra')
        total_impuestos = sum(desglose_impuestos.values())
        total = subtotal + Money(total_impuestos, subtotal.currency)

        return JsonResponse({
            'subtotal': f"{subtotal.amount:,.2f}", 'currency_symbol': subtotal.currency.code,
            'impuestos': {k: f"{v:,.2f}" for k, v in desglose_impuestos.items()},
            'total': f"{total.amount:,.2f}",
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)