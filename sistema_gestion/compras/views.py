# compras/views.py (VERSIÓN CORREGIDA Y ROBUSTA)

import json
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.admin.views.decorators import staff_member_required
from djmoney.money import Money
from rest_framework import viewsets
from django.shortcuts import get_object_or_404

# --- Modelos ---
from .models import ComprobanteCompra
from inventario.models import Articulo
from parametros.models import Moneda, TipoComprobante

# --- Servicios ---
from ventas.services import TaxCalculatorService
from compras.services import CostCalculatorService


class ComprobanteCompraViewSet(viewsets.ModelViewSet):
    queryset = ComprobanteCompra.objects.all().order_by('-fecha', '-numero')


@staff_member_required
def get_precio_proveedor_json(request, proveedor_pk, articulo_pk):
    """
    Busca el costo más relevante para un artículo de un proveedor específico.
    Blindada contra errores de tipos de datos.
    """
    try:
        articulo = get_object_or_404(Articulo, pk=articulo_pk)
        cantidad_a_comprar = Decimal(request.GET.get('cantidad', 1))

        # 1. Obtener precio del servicio
        # El servicio puede devolver un objeto complejo o None
        item_precio = CostCalculatorService.get_latest_price(
            proveedor_pk=proveedor_pk,
            articulo_pk=articulo_pk,
            cantidad=cantidad_a_comprar
        )

        costo_final_money = None
        source_info = ''

        if item_precio:
            # Intentamos calcular el costo efectivo
            try:
                # Si el servicio devuelve un objeto con método costo_efectivo (modelo nuevo)
                if hasattr(item_precio, 'costo_efectivo'):
                    costo_final_money = item_precio.costo_efectivo
                # Si es el modelo viejo o el servicio devuelve el objeto raw
                else:
                    costo_final_money = CostCalculatorService.calculate_effective_cost(item_precio)

                source_info = 'Precio de Proveedor'
            except Exception as e:
                print(f"Error calculando costo efectivo: {e}")
                # Fallback si falla el cálculo complejo
                if hasattr(item_precio, 'precio_costo'):
                    costo_final_money = item_precio.precio_costo
                elif hasattr(item_precio, 'precio_lista'):
                    costo_final_money = item_precio.precio_lista

        # 2. Fallback al artículo si no hay precio de proveedor
        if not costo_final_money:
            # Usamos la property del artículo que devuelve Money
            costo_final_money = articulo.precio_costo
            source_info = 'Costo Base del Artículo'

        # 3. Asegurar que tenemos un objeto Money válido
        if not isinstance(costo_final_money, Money):
            moneda_default = articulo.precio_costo_moneda.simbolo if articulo.precio_costo_moneda else 'ARS'
            costo_final_money = Money(costo_final_money, moneda_default)

        # 4. Obtener ID de moneda para el select del frontend (CORREGIDO)
        # Usamos filter().first() para evitar error si hay duplicados en la BD
        moneda_obj = Moneda.objects.filter(simbolo=costo_final_money.currency.code).first()

        if not moneda_obj:
            # Si no encuentra la moneda por símbolo, busca la base
            moneda_obj = Moneda.objects.filter(es_base=True).first()

        moneda_id = moneda_obj.id if moneda_obj else 1

        return JsonResponse({
            'amount': f"{costo_final_money.amount:.4f}",
            'currency_code': costo_final_money.currency.code,
            'currency_id': moneda_id,
            'source': source_info
        })

    except Exception as e:
        # Log del error real para debugging
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error': 'SERVER_ERROR',
            'message': f'Error interno: {str(e)}'
        }, status=500)


@staff_member_required
@require_POST
def calcular_totales_compra_api(request):
    try:
        data = json.loads(request.body)
        items_data = data.get('items', [])

        class FakeItem:
            def __init__(self, data):
                self.articulo = Articulo.objects.get(pk=data.get('articulo'))
                self.cantidad = Decimal(data.get('cantidad', '0'))
                monto = Decimal(data.get('precio_monto', '0'))
                moneda_id = data.get('precio_moneda_id')
                if moneda_id:
                    moneda_simbolo = Moneda.objects.get(pk=moneda_id).simbolo
                else:
                    moneda_simbolo = 'ARS'
                self.precio_costo_unitario = Money(monto, moneda_simbolo)

            @property
            def subtotal(self):
                return self.cantidad * self.precio_costo_unitario

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
        subtotal_currency = 'ARS'
        if fake_comprobante.all(): subtotal_currency = fake_comprobante.all()[0].subtotal.currency.code

        subtotal = sum((item.subtotal for item in fake_comprobante.all()), Money(0, subtotal_currency))
        desglose_impuestos = TaxCalculatorService.calcular_impuestos_comprobante(fake_comprobante, 'compra')
        total_impuestos = sum(desglose_impuestos.values())
        total = subtotal + Money(total_impuestos, subtotal.currency)

        return JsonResponse({
            'subtotal': f"{subtotal.amount:,.2f}",
            'currency_symbol': subtotal.currency.code,
            'impuestos': {k: f"{v:,.2f}" for k, v in desglose_impuestos.items()},
            'total': f"{total.amount:,.2f}",
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=400)


@staff_member_required
def get_comprobante_info(request, pk):
    """
    Devuelve saldo y total de un comprobante para autocompletar la Orden de Pago.
    """
    try:
        comp = ComprobanteCompra.objects.get(pk=pk)
        return JsonResponse({
            'saldo': str(comp.saldo_pendiente),
            'total': str(comp.total),
            'id': comp.pk
        })
    except ComprobanteCompra.DoesNotExist:
        return JsonResponse({'error': 'Comprobante no encontrado'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)