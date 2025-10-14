# compras/services.py

from decimal import Decimal
from djmoney.money import Money
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q

from .models import PrecioProveedorArticulo
from inventario.models import ConversionUnidadMedida


class CostCalculatorService:
    @staticmethod
    def apply_cascading_discounts(base_amount: Decimal, discount_list: list) -> Decimal:
        final_amount = base_amount
        for percentage in discount_list:
            try:
                percentage_decimal = Decimal(str(percentage))
                factor = Decimal(1) + (percentage_decimal / Decimal(100))
                final_amount *= factor
            except (TypeError, ValueError):
                continue
        return final_amount.quantize(Decimal('0.0001'))

    @classmethod
    def calculate_effective_cost(cls, item_precio: 'PrecioProveedorArticulo') -> Money:
        costo_base = item_precio.precio_costo.amount
        currency = item_precio.precio_costo.currency

        if item_precio.bonificacion_porcentaje > 0:
            bonificacion_factor = (Decimal(100) - item_precio.bonificacion_porcentaje) / Decimal(100)
            costo_base *= bonificacion_factor

        if item_precio.descuentos_adicionales:
            costo_base = cls.apply_cascading_discounts(costo_base, item_precio.descuentos_adicionales)

        if item_precio.descuentos_financieros:
            costo_base = cls.apply_cascading_discounts(costo_base, item_precio.descuentos_financieros)

        try:
            conversion = ConversionUnidadMedida.objects.get(
                articulo=item_precio.articulo,
                unidad_externa=item_precio.unidad_medida_compra
            )
            costo_unitario_stock = costo_base / conversion.factor_conversion
        except ObjectDoesNotExist:
            costo_unitario_stock = costo_base

        return Money(costo_unitario_stock, currency)

    @classmethod
    def get_latest_price(cls, proveedor_pk: int, articulo_pk: str,
                         cantidad: Decimal = Decimal(1)) -> 'PrecioProveedorArticulo | None':
        try:
            item_precio = PrecioProveedorArticulo.objects.filter(
                proveedor_id=proveedor_pk,
                articulo_id=articulo_pk,
                cantidad_minima__lte=cantidad
            ).order_by('-cantidad_minima').first()
            return item_precio
        except PrecioProveedorArticulo.DoesNotExist:
            return None
        except Exception as e:
            print(f"Error en get_latest_price: {e}")
            return None