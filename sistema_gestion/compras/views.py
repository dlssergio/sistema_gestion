import json
from decimal import Decimal
from django.http import JsonResponse
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib.admin.views.decorators import staff_member_required
from djmoney.money import Money
from rest_framework import viewsets, status, filters
from rest_framework.response import Response
from django.core.exceptions import ValidationError

# --- Modelos ---
from .models import ComprobanteCompra, ComprobanteCompraItem, Proveedor
from inventario.models import Articulo, StockArticulo, Deposito
from parametros.models import Moneda, TipoComprobante

# --- Serializers ---
from .serializers import (
    ComprobanteCompraSerializer,
    ComprobanteCompraCreateSerializer
)

# --- Servicios ---
from ventas.services import TaxCalculatorService
from compras.services import CostCalculatorService
from entidades.serializers import ProveedorSerializer


class ComprobanteCompraViewSet(viewsets.ModelViewSet):
    queryset = ComprobanteCompra.objects.all().order_by('-fecha', '-id')

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ComprobanteCompraCreateSerializer
        return ComprobanteCompraSerializer

    def create(self, request, *args, **kwargs):
        # 1. Validación inicial
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                # 2. Separar items
                items_data = serializer.validated_data.pop('items')
                datos_compra = serializer.validated_data

                # 3. Crear Cabecera
                compra = ComprobanteCompra.objects.create(**datos_compra)

                total_acumulado = Decimal(0)
                moneda_comprobante = 'ARS'

                # 4. Procesar Ítems
                for item in items_data:
                    articulo_obj = item['articulo']
                    cantidad_val = item['cantidad']

                    # Buscamos el monto (fallback seguro)
                    monto_val = item.get('precio_costo_unitario_monto')
                    if monto_val is None:
                        monto_val = item.get('precio_costo_unitario')

                    if monto_val is None:
                        monto_val = Decimal(0)

                    # --- GUARDADO ÍTEM (Solo Monto) ---
                    item_creado = ComprobanteCompraItem.objects.create(
                        comprobante=compra,
                        articulo=articulo_obj,
                        cantidad=cantidad_val,
                        precio_costo_unitario_monto=monto_val
                        # NO guardamos currency aquí para evitar errores de columna
                    )

                    # Sumar al total acumulado (Decimal puro)
                    subtotal_linea = Decimal(item_creado.cantidad) * monto_val
                    total_acumulado += subtotal_linea

                    # Detectar moneda para referencia
                    if hasattr(item_creado, 'precio_costo_unitario') and hasattr(item_creado.precio_costo_unitario,
                                                                                 'currency'):
                        moneda_comprobante = item_creado.precio_costo_unitario.currency.code

                # 5. Actualizar Total (CORRECCIÓN FINAL - VOLVEMOS A LO QUE FUNCIONÓ)
                # NO usamos Money() aquí. Pasamos el Decimal puro.

                compra.total = total_acumulado

                # Forzamos la moneda en la columna separada (así funciona djmoney por debajo)
                if hasattr(compra, 'total_currency'):
                    compra.total_currency = moneda_comprobante

                # Saldo pendiente también recibe Decimal puro
                compra.saldo_pendiente = total_acumulado

                compra.save()

        except Exception as e:
            print(f"ERROR CREATE COMPRA: {e}")
            import traceback
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        read_serializer = ComprobanteCompraSerializer(compra)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)


# --- VISTAS AUXILIARES COMPLETAS ---

@staff_member_required
def get_precio_proveedor_json(request, proveedor_pk, articulo_pk):
    try:
        articulo = get_object_or_404(Articulo, pk=articulo_pk)
        cantidad_a_comprar = Decimal(request.GET.get('cantidad', 1))

        item_precio = CostCalculatorService.get_latest_price(
            proveedor_pk=proveedor_pk,
            articulo_pk=articulo_pk,
            cantidad=cantidad_a_comprar
        )

        costo_final_money = None
        source_info = ''

        if item_precio:
            try:
                if hasattr(item_precio, 'costo_efectivo'):
                    costo_final_money = item_precio.costo_efectivo
                else:
                    costo_final_money = CostCalculatorService.calculate_effective_cost(item_precio)
                source_info = 'Precio de Proveedor'
            except Exception as e:
                if hasattr(item_precio, 'precio_costo'):
                    costo_final_money = item_precio.precio_costo
                elif hasattr(item_precio, 'precio_lista'):
                    costo_final_money = item_precio.precio_lista

        if not costo_final_money:
            costo_final_money = articulo.precio_costo
            source_info = 'Costo Base del Artículo'

        if not isinstance(costo_final_money, Money):
            moneda_default = 'ARS'
            costo_final_money = Money(costo_final_money, moneda_default)

        moneda_obj = Moneda.objects.filter(simbolo=costo_final_money.currency.code).first()
        if not moneda_obj:
            moneda_obj = Moneda.objects.filter(es_base=True).first()

        moneda_id = moneda_obj.id if moneda_obj else 1

        return JsonResponse({
            'amount': f"{costo_final_money.amount:.4f}",
            'currency_code': costo_final_money.currency.code,
            'currency_id': moneda_id,
            'source': source_info
        })

    except Exception as e:
        return JsonResponse({
            'error': 'SERVER_ERROR',
            'message': f'Error interno: {str(e)}'
        }, status=500)


@staff_member_required
@require_POST
def calcular_totales_compra_api(request):
    """
    Calcula totales simulando el comprobante en memoria.
    """
    try:
        data = json.loads(request.body)
        items_data = data.get('items', [])

        class FakeItem:
            def __init__(self, item_data):
                self.articulo_id = item_data.get('articulo')
                if self.articulo_id:
                    self.articulo = Articulo.objects.get(pk=self.articulo_id)
                else:
                    self.articulo = None

                self.cantidad = Decimal(str(item_data.get('cantidad', 0)))

                raw_precio = item_data.get('precio_costo_unitario', 0)
                if isinstance(raw_precio, dict):
                    monto = Decimal(str(raw_precio.get('amount', 0)))
                else:
                    monto = Decimal(str(raw_precio))

                self.precio_costo_unitario = Money(monto, 'ARS')

            @property
            def subtotal(self):
                return self.cantidad * self.precio_costo_unitario

        class FakeComprobante:
            def __init__(self, items_data_raw, data_raw):
                self.items_list = []
                for i in items_data_raw:
                    if i.get('articulo'):
                        self.items_list.append(FakeItem(i))

                tipo_id = data_raw.get('tipo_comprobante')
                self.tipo_comprobante = None
                if tipo_id:
                    self.tipo_comprobante = TipoComprobante.objects.filter(pk=tipo_id).first()

            @property
            def items(self):
                return self

            def all(self):
                return self.items_list

        fake_comprobante = FakeComprobante(items_data, data)

        subtotal_val = Decimal(0)
        subtotal_currency = 'ARS'

        for item in fake_comprobante.all():
            subtotal_val += item.subtotal.amount
            subtotal_currency = item.subtotal.currency.code

        subtotal = Money(subtotal_val, subtotal_currency)

        desglose_impuestos = TaxCalculatorService.calcular_impuestos_comprobante(fake_comprobante, 'compra')
        total_impuestos_val = sum(desglose_impuestos.values())
        total_final = subtotal + Money(total_impuestos_val, subtotal.currency)

        return JsonResponse({
            'subtotal': f"{subtotal.amount:,.2f}",
            'currency_symbol': subtotal.currency.code,
            'impuestos': {k: f"{v:,.2f}" for k, v in desglose_impuestos.items()},
            'total': f"{total_final.amount:,.2f}",
        })

    except Exception as e:
        # Fallback silencioso en caso de error de cálculo
        return JsonResponse({
            'subtotal': '0.00',
            'currency_symbol': 'ARS',
            'impuestos': {},
            'total': '0.00'
        })


@staff_member_required
def get_comprobante_info(request, pk):
    try:
        comp = ComprobanteCompra.objects.get(pk=pk)
        return JsonResponse({
            'saldo': str(comp.saldo_pendiente.amount),
            'total': str(comp.total.amount),
            'id': comp.pk})
    except ComprobanteCompra.DoesNotExist:
        return JsonResponse({'error': 'Comprobante no encontrado'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


class ProveedorViewSet(viewsets.ModelViewSet):
    queryset = Proveedor.objects.all().order_by('entidad__razon_social')
    serializer_class = ProveedorSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['entidad__razon_social', 'entidad__cuit', 'nombre_fantasia']