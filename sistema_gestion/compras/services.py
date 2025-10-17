# compras/services.py (VERSIÓN FINAL CON LÓGICA DE BÚSQUEDA)

from decimal import Decimal
from djmoney.money import Money
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.utils import timezone

# Importamos los modelos necesarios aquí
from .models import ListaPreciosProveedor, ItemListaPreciosProveedor, Proveedor
from inventario.models import ConversionUnidadMedida, Articulo


class CostCalculatorService:
    # ... (el método apply_cascading_discounts se mantiene igual) ...
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
    def calculate_effective_cost(cls, item_precio: ItemListaPreciosProveedor) -> Money:
        costo_base = item_precio.precio_lista.amount
        currency = item_precio.precio_lista.currency

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
            if conversion.factor_conversion > 0:
                costo_unitario_stock = costo_base / conversion.factor_conversion
            else:
                costo_unitario_stock = costo_base
        except ObjectDoesNotExist:
            costo_unitario_stock = costo_base

        return Money(costo_unitario_stock, currency)

    @classmethod
    def get_latest_price(cls, proveedor_pk: int, articulo_pk: str, cantidad: Decimal = Decimal(1)):
        """
        MÉTODO ACTUALIZADO: Busca el precio usando la nueva lógica de listas de precios.
        """
        try:
            proveedor = Proveedor.objects.get(pk=proveedor_pk)
            articulo = Articulo.objects.get(pk=articulo_pk)
            fecha = timezone.now().date()

            # 1. Buscar en la lista principal activa y vigente
            lista_principal = ListaPreciosProveedor.objects.filter(
                proveedor=proveedor, es_principal=True, es_activa=True,
                vigente_desde__lte=fecha
            ).filter(Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=fecha)).first()

            if lista_principal:
                item = ItemListaPreciosProveedor.objects.filter(
                    lista_precios=lista_principal, articulo=articulo, cantidad_minima__lte=cantidad
                ).order_by('-cantidad_minima').first()
                if item:
                    return item

            # 2. Si no se encontró, buscar en CUALQUIER otra lista activa y vigente
            otras_listas = ListaPreciosProveedor.objects.filter(
                proveedor=proveedor, es_principal=False, es_activa=True,
                vigente_desde__lte=fecha
            ).filter(Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=fecha)).order_by('-vigente_desde')

            for lista in otras_listas:
                item = ItemListaPreciosProveedor.objects.filter(
                    lista_precios=lista, articulo=articulo, cantidad_minima__lte=cantidad
                ).order_by('-cantidad_minima').first()
                if item:
                    return item

            return None  # Si no se encuentra en ninguna lista, no hay precio.

        except (Proveedor.DoesNotExist, Articulo.DoesNotExist):
            return None
        except Exception as e:
            print(f"Error en get_latest_price: {e}")
            return None