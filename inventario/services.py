from django.db import transaction
from django.core.exceptions import ValidationError
from decimal import Decimal


class StockService:
    @staticmethod
    def ajustar_stock(articulo, deposito, cantidad, operacion=None):
        """
        Ajusta el stock de un artículo en un depósito.

        Soporta dos modos:
        1. Explícito: Pasar operacion='SUMAR' o 'RESTAR'. (Usa valor absoluto de cantidad)
        2. Directo: No pasar operación. (Suma algebraicamente la cantidad, que debe venir con signo)
        """
        from .models import StockArticulo

        if not deposito:
            raise ValidationError(f"No se definió depósito para el artículo {articulo}")

        # Bloqueo atómico para evitar condiciones de carrera
        with transaction.atomic():
            stock_obj, created = StockArticulo.objects.select_for_update().get_or_create(
                articulo=articulo,
                deposito=deposito,
                defaults={'cantidad': 0}
            )

            # Convertimos a Decimal por seguridad
            cantidad_dec = Decimal(str(cantidad))

            if operacion == 'SUMAR':
                stock_obj.cantidad += abs(cantidad_dec)
            elif operacion == 'RESTAR':
                stock_obj.cantidad -= abs(cantidad_dec)
            else:
                # MODO NUEVO (El que usa la Signal de Ventas)
                # Si cantidad es negativa, restará. Si es positiva, sumará.
                stock_obj.cantidad += cantidad_dec

            stock_obj.save()
            return stock_obj.cantidad