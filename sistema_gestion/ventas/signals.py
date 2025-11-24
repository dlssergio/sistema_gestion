# ventas/signals.py (NUEVO ARCHIVO)

from django.db.models.signals import post_save
from django.dispatch import receiver
from inventario.models import Articulo
from .models import PriceList, ProductPrice
import logging

# Configurar un logger para poder ver qué está pasando en la consola
logger = logging.getLogger(__name__)

@receiver(post_save, sender=Articulo)
def manage_default_product_price(sender, instance: Articulo, created, **kwargs):
    """
    Signal que se dispara después de guardar un Artículo.
    Asegura que cada artículo vendible tenga una entrada en la lista de precios base.
    Si la utilidad del artículo cambia, el precio en la lista base se actualiza.
    """
    # Solo actuar sobre artículos que se pueden vender
    if instance.perfil not in [Articulo.Perfil.COMPRA_VENTA, Articulo.Perfil.VENTA]:
        return

    # Buscar la lista de precios por defecto (debería haber solo una)
    default_list = PriceList.objects.filter(is_default=True).first()

    if not default_list:
        logger.warning(
            "SIN LISTA BASE: No se encontró una 'Lista de Precios de Venta' marcada como por defecto. "
            "No se pudo crear/actualizar el precio base para el artículo %s.", instance.cod_articulo
        )
        return

    # Usamos update_or_create:
    # - Si el artículo es nuevo (created=True), creará el ProductPrice.
    # - Si el artículo se edita (ej. cambia su costo o utilidad), actualizará el ProductPrice existente.
    obj, created_price = ProductPrice.objects.update_or_create(
        product=instance,
        price_list=default_list,
        min_quantity=1, # El precio base siempre aplica desde la primera unidad
        defaults={
            'price_monto': instance.precio_venta_monto,
            'price_moneda': instance.precio_venta_moneda
        }
    )

    if created_price:
        logger.info(
            "AUTO-PRECIO CREADO: Precio base para el nuevo artículo '%s' añadido a la lista '%s'.",
            instance.cod_articulo, default_list.name
        )
    else:
        # Esto nos permite ver en la consola si un cambio en el artículo actualizó el precio.
        logger.info(
            "AUTO-PRECIO ACTUALIZADO: Precio base para el artículo '%s' actualizado en la lista '%s'.",
            instance.cod_articulo, default_list.name
        )