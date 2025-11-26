# ventas/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from decimal import Decimal
from inventario.models import Articulo
from .models import PriceList, ProductPrice
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Articulo)
def manage_default_product_price(sender, instance: Articulo, created, **kwargs):
    """
    Sincronización DIRECTA: Artículo -> Lista de Precios Por Defecto.
    Se dispara cuando guardas un Artículo.
    """
    # 1. Evitar bucle infinito: Si esta actualización viene desde la señal inversa, paramos.
    if getattr(instance, '_from_pricelist_sync', False):
        return

    if instance.perfil not in [Articulo.Perfil.COMPRA_VENTA, Articulo.Perfil.VENTA]:
        return

    default_list = PriceList.objects.filter(is_default=True).first()
    if not default_list:
        logger.warning(
            "SIN LISTA BASE: No se encontró una 'Lista de Precios de Venta' marcada como por defecto. "
            "No se pudo crear/actualizar el precio base para el artículo %s.", instance.cod_articulo
        )
        return

    # Usamos update_or_create para reflejar el precio base en la lista por defecto
    obj, created_price = ProductPrice.objects.update_or_create(
        product=instance,
        price_list=default_list,
        min_quantity=1,
        defaults={
            'price_monto': instance.precio_venta_monto,
            'price_moneda': instance.precio_venta_moneda
        }
    )


@receiver(post_save, sender=ProductPrice)
def sync_product_price_to_article(sender, instance: ProductPrice, created, **kwargs):
    """
    Sincronización INVERSA: Lista de Precios Por Defecto -> Artículo.
    Se dispara cuando guardas un Precio (manualmente o por acción masiva).
    """
    # 1. Validaciones: Solo actuamos si es la lista por defecto y cantidad base (1)
    if not instance.price_list.is_default:
        return

    # No sincronizamos precios escalonados (mayoristas por cantidad), solo el precio base
    if instance.min_quantity > 1:
        return

    articulo = instance.product

    # 2. ROMPER EL BUCLE INFINITO (Check de Igualdad)
    # Si el precio en el artículo YA es igual al que estamos guardando, no hacemos nada.
    # Esto detiene la recursión: Articulo -> Signal -> ProductPrice -> Signal -> (Stop aquí)
    if (articulo.precio_venta_monto == instance.price_monto and
            articulo.precio_venta_moneda == instance.price_moneda):
        return

    logger.info(
        f"SYNC INVERSO: Actualizando Artículo {articulo.cod_articulo} desde Lista Defecto ($ {instance.price_monto}).")

    # 3. Actualizar Precio en el Artículo
    articulo.precio_venta_monto = instance.price_monto
    articulo.precio_venta_moneda = instance.price_moneda

    # 4. RECALCULAR UTILIDAD (Matemática Inversa)
    # Si cambiamos el precio final manteniendo el costo, la utilidad cambió.
    # Fórmula: Utilidad% = ((PrecioVenta / Costo) - 1) * 100
    if articulo.precio_costo_monto > 0:
        # Asumimos misma moneda para este cálculo simple.
        # Si fueran monedas distintas habría que convertir, pero en lista defecto suele ser la misma.
        try:
            nuevo_precio = instance.price_monto
            costo = articulo.precio_costo_monto

            # Calculamos nueva utilidad
            nueva_utilidad = ((nuevo_precio / costo) - 1) * 100
            articulo.utilidad = nueva_utilidad
        except Exception as e:
            logger.error(f"Error recalculando utilidad para {articulo.cod_articulo}: {e}")

    # 5. Guardar Artículo con BANDERA DE SILENCIO
    # Le ponemos una marca temporal al objeto para que la señal 'manage_default_product_price'
    # sepa que no debe ejecutarse de nuevo.
    articulo._from_pricelist_sync = True
    articulo.save()