# ventas/services.py (VERSIÓN FINAL CORREGIDA)

from django.utils import timezone
from django.db.models import Q
from decimal import Decimal
from djmoney.money import Money
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Any

from .models import PriceList, ProductPrice, Cliente
from inventario.models import Articulo
from compras.services import CostCalculatorService


@dataclass
class PricingResult:
    costo: Money
    utilidad: Decimal
    markup: Decimal
    precio_venta_neto: Money
    precio_final: Money  # <--- Campo movido arriba (ya lo habíamos arreglado)
    impuestos: Dict[str, Money] = field(default_factory=dict)


class TaxCalculatorService:
    # ... (sin cambios en TaxCalculatorService, déjalo como estaba) ...
    @staticmethod
    def calcular_impuestos_comprobante(comprobante, tipo_operacion: str):
        impuestos_agrupados = defaultdict(Decimal)
        today = timezone.now().date()

        items_iter = comprobante.items.all() if hasattr(comprobante.items, 'all') else comprobante.items

        for item in items_iter:
            subtotal_item_raw = item.subtotal
            # Robustez: obtener amount si es Money
            subtotal_item = subtotal_item_raw.amount if hasattr(subtotal_item_raw, 'amount') else subtotal_item_raw

            if not subtotal_item or subtotal_item <= 0: continue

            impuestos_aplicables = item.articulo.impuestos.filter(
                Q(aplica_a=tipo_operacion) | Q(aplica_a='ambos'),
                vigente_desde__lte=today
            ).filter(Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=today))

            for impuesto in impuestos_aplicables:
                monto_impuesto = Decimal('0.00')
                if impuesto.es_porcentaje:
                    monto_impuesto = subtotal_item * (impuesto.tasa / Decimal(100))
                else:
                    monto_impuesto = impuesto.tasa * item.cantidad
                impuestos_agrupados[impuesto.nombre] += monto_impuesto

        return {nombre: monto.quantize(Decimal('0.01')) for nombre, monto in impuestos_agrupados.items()}


class PricingService:
    @staticmethod
    def get_product_pricing(product: Articulo, customer: Cliente, quantity: Decimal = Decimal(1)) -> "PricingResult":
        date = timezone.now().date()

        # 1. COSTO
        costo_efectivo = product.precio_costo
        proveedor_fuente = product.proveedor_actualiza_precio

        if proveedor_fuente:
            item_costo = CostCalculatorService.get_latest_price(
                proveedor_pk=proveedor_fuente.pk,
                articulo_pk=product.pk,
                cantidad=quantity
            )
            if item_costo:
                costo_efectivo = CostCalculatorService.calculate_effective_cost(item_costo)

        # 2. PRECIO VENTA NETO
        precio_venta_neto = product.precio_venta
        price_list_to_use = None

        if customer.price_list:
            lista = customer.price_list
            is_valid = True
            if lista.valid_from and date < lista.valid_from: is_valid = False
            if lista.valid_until and date > lista.valid_until: is_valid = False
            if is_valid: price_list_to_use = lista

        if not price_list_to_use:
            default_list = PriceList.objects.filter(is_default=True).first()
            if default_list:
                is_valid = True
                if default_list.valid_from and date < default_list.valid_from: is_valid = False
                if default_list.valid_until and date > default_list.valid_until: is_valid = False
                if is_valid: price_list_to_use = default_list

        if price_list_to_use:
            price_obj = ProductPrice.objects.filter(
                product=product,
                price_list=price_list_to_use,
                min_quantity__lte=quantity
            ).filter(Q(max_quantity__isnull=True) | Q(max_quantity__gte=quantity)).order_by('-min_quantity').first()

            if price_obj:
                precio_venta_neto = Money(price_obj.price_monto, price_obj.price_moneda.simbolo)

            if price_list_to_use.discount_percentage > 0:
                factor = Decimal(1) - (price_list_to_use.discount_percentage / Decimal(100))
                precio_venta_neto = precio_venta_neto * factor

        # 3. MÁRGENES
        costo_monto = costo_efectivo.amount
        venta_neta_monto = precio_venta_neto.amount
        utilidad = Decimal('0.00')
        markup = Decimal('0.00')

        if venta_neta_monto > 0:
            utilidad = ((venta_neta_monto - costo_monto) / venta_neta_monto) * 100
        if costo_monto > 0:
            markup = ((venta_neta_monto - costo_monto) / costo_monto) * 100

        # 4. IMPUESTOS
        class FakeItem:
            subtotal = precio_venta_neto
            articulo = product
            cantidad = quantity

        class FakeComprobante:
            items = [FakeItem()]

        impuestos_calculados_dict = TaxCalculatorService.calcular_impuestos_comprobante(FakeComprobante(), 'venta')
        total_impuestos = sum(impuestos_calculados_dict.values(), Decimal('0.00'))

        # 5. FINAL
        precio_final = precio_venta_neto + Money(total_impuestos, precio_venta_neto.currency)

        # --- CORRECCIÓN DEL ERROR ATTRIBUTE ERROR ---
        # En lugar de .quantize() directo al objeto Money, usamos round() que django-money soporta
        # O redondeamos el .amount y recreamos el Money.

        def round_money(money_obj):
            return Money(money_obj.amount.quantize(Decimal('0.01')), money_obj.currency)

        return PricingResult(
            costo=round_money(costo_efectivo),
            utilidad=utilidad.quantize(Decimal('0.01')),
            markup=markup.quantize(Decimal('0.01')),
            precio_venta_neto=round_money(precio_venta_neto),
            impuestos={k: Money(v, precio_venta_neto.currency) for k, v in impuestos_calculados_dict.items()},
            precio_final=round_money(precio_final)
        )