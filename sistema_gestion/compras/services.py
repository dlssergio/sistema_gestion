# compras/services.py (VERSIÓN CON LÓGICA DE CONVERSIÓN JERÁRQUICA)

from decimal import Decimal
from djmoney.money import Money
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.utils import timezone

from .models import ListaPreciosProveedor, ItemListaPreciosProveedor, Proveedor
from inventario.models import ConversionUnidadMedida, Articulo


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
        # Redondeamos a 4 decimales para mantener la precisión en los cálculos intermedios.
        return final_amount.quantize(Decimal('0.0001'))

    @classmethod
    def calculate_effective_cost(cls, item_precio: ItemListaPreciosProveedor) -> Money:
        """
        Calcula el costo efectivo final en la UNIDAD DE STOCK del artículo.
        Utiliza una jerarquía de reglas de conversión.
        """
        costo_base = item_precio.precio_lista.amount
        currency = item_precio.precio_lista.currency

        # --- PASO 1: Aplicar todos los descuentos al precio de compra ---
        if item_precio.bonificacion_porcentaje > 0:
            bonificacion_factor = (Decimal(100) - item_precio.bonificacion_porcentaje) / Decimal(100)
            costo_base *= bonificacion_factor

        if item_precio.descuentos_adicionales:
            costo_base = cls.apply_cascading_discounts(costo_base, item_precio.descuentos_adicionales)

        if item_precio.descuentos_financieros:
            costo_base = cls.apply_cascading_discounts(costo_base, item_precio.descuentos_financieros)

        # --- PASO 2: Lógica de Conversión Jerárquica ---
        unidad_compra = item_precio.unidad_medida_compra
        unidad_stock = item_precio.articulo.unidad_medida_stock

        costo_unitario_stock = costo_base  # Por defecto, el costo es el calculado.

        # La conversión solo es necesaria si las unidades son diferentes.
        if unidad_compra != unidad_stock:
            try:
                # REGLA #1 (Máxima Prioridad): Buscar una regla de conversión específica para este artículo.
                # Esta regla maneja casos como "1 Metro de Chapa = 2.5 Kilos" o "1 Caja = 32 Unidades".
                conversion = ConversionUnidadMedida.objects.get(
                    articulo=item_precio.articulo,
                    unidad_externa=unidad_compra
                )

                # Si se encuentra la regla y el factor es válido, se aplica la conversión.
                if conversion.factor_conversion and conversion.factor_conversion > 0:
                    costo_unitario_stock = costo_base / conversion.factor_conversion
                else:
                    # Si el factor es 0, la conversión es inválida. Se podría loggear un warning.
                    pass

            except ObjectDoesNotExist:
                # REGLA #2 (Fallback): Si no hay regla específica, en el futuro aquí iría la lógica
                # para convertir entre unidades del mismo grupo (ej. Kilos a Gramos).
                # Por ahora, si no hay regla explícita, no se puede convertir.
                # Esto indica que falta una configuración en el sistema para este caso.
                pass

        # --- PASO 3: Devolver el resultado final ---
        return Money(costo_unitario_stock, currency)

    @classmethod
    def get_latest_price(cls, proveedor_pk: int, articulo_pk: str, cantidad: Decimal = Decimal(1)):
        # ... (Tu método get_latest_price se mantiene exactamente igual) ...
        try:
            proveedor = Proveedor.objects.get(pk=proveedor_pk)
            articulo = Articulo.objects.get(pk=articulo_pk)
            fecha = timezone.now().date()

            # 1. Buscar en la lista principal
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

            # 2. Buscar en otras listas
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

            return None

        except (Proveedor.DoesNotExist, Articulo.DoesNotExist):
            return None
        except Exception as e:
            # En un entorno de producción, sería mejor usar logging en lugar de print.
            # import logging
            # logging.error(f"Error en get_latest_price: {e}")
            print(f"Error en get_latest_price: {e}")
            return None