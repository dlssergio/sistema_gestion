from django.db import transaction
from django.core.exceptions import ValidationError



class StockService:
    @staticmethod
    def ajustar_stock(articulo, deposito, cantidad, operacion):
        """
        Ajusta el stock de un artículo en un depósito.
        operacion: 'SUMAR' o 'RESTAR'
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

            if operacion == 'SUMAR':
                stock_obj.cantidad += cantidad
            elif operacion == 'RESTAR':
                stock_obj.cantidad -= cantidad

            stock_obj.save()
            return stock_obj.cantidad