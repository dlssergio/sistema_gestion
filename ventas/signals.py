# ventas/signals.py (VERSIÓN LIMPIA Y FUNCIONAL)
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.db import transaction
from .models import ComprobanteVenta, Recibo, PriceList, ProductPrice
from inventario.models import Articulo
from finanzas.models import Cheque
from inventario.services import StockService


# --- LÓGICA DE STOCK ---
@receiver(post_save, sender=ComprobanteVenta, dispatch_uid='stock_unico_venta')
def aplicar_stock_venta(sender, instance, **kwargs):
    # 1. Validar estado CONFIRMADO
    if instance.estado != ComprobanteVenta.Estado.CONFIRMADO:
        return

    # 2. BLINDAJE ANTI-VACÍO (CRÍTICO)
    # Si Django está guardando el padre pero aún no los hijos, salimos sin marcar nada.
    # Esto permite que la señal se ejecute de nuevo cuando los ítems estén listos.
    if not instance.items.exists():
        return

    # 3. Validar si ya se aplicó (consultando DB real)
    if instance.pk:
        instance.refresh_from_db(fields=['stock_aplicado'])

    if instance.stock_aplicado:
        return

    # 4. Lógica de Stock
    if instance.tipo_comprobante and instance.tipo_comprobante.mueve_stock:
        signo = instance.tipo_comprobante.signo_stock

        for item in instance.items.all():
            cantidad_real = item.cantidad * signo
            accion = 'SUMAR' if cantidad_real > 0 else 'RESTAR'
            cantidad_absoluta = abs(cantidad_real)

            if cantidad_absoluta > 0:
                StockService.ajustar_stock(
                    articulo=item.articulo,
                    deposito=instance.deposito,
                    cantidad=cantidad_absoluta,
                    operacion=accion
                )

        # 5. Marcar como aplicado
        ComprobanteVenta.objects.filter(pk=instance.pk).update(stock_aplicado=True)
        instance.stock_aplicado = True


@receiver(post_save, sender=ComprobanteVenta)
def intentar_cae_automatico(sender, instance, created, **kwargs):
    # Solo si está confirmado y NO tiene CAE
    if instance.estado == 'CN' and not instance.cae:
        from parametros.models import ConfiguracionEmpresa
        config = ConfiguracionEmpresa.objects.first()

        if config and config.modo_facturacion == 'AUTO':
            # Importar aquí para evitar importación circular
            from parametros.afip import AfipManager
            try:
                afip = AfipManager()
                afip.emitir_comprobante(instance)
            except Exception as e:
                # En signals es delicado fallar, mejor loguear el error
                print(f"Error CAE Automático: {e}")


# --- LÓGICA DE FINANZAS (RECIBOS) ---

@receiver(post_save, sender=Recibo)
def trigger_finanzas_recibo(sender, instance, **kwargs):
    if instance.estado == Recibo.Estado.ANULADO:
        instance.revertir_finanzas()


@receiver(pre_delete, sender=Recibo)
def reversar_al_eliminar_recibo(sender, instance, **kwargs):
    if instance.finanzas_aplicadas:
        imputaciones = list(instance.imputaciones.all())
        valores = list(instance.valores.all())
        with transaction.atomic():
            for imputacion in imputaciones:
                comp = imputacion.comprobante
                comp.saldo_pendiente += imputacion.monto_imputado
                comp.save()
            for valor in valores:
                valor.destino.saldo_monto -= valor.monto
                valor.destino.save()
                if valor.tipo.es_cheque:
                    Cheque.objects.filter(numero=valor.referencia).update(estado=Cheque.Estado.ANULADO)


# --- LÓGICA DE PRECIOS (SINCRONIZACIÓN) ---

@receiver(post_save, sender=Articulo)
def manage_default_product_price(sender, instance, **kwargs):
    if getattr(instance, '_from_pricelist_sync', False): return
    default_list = PriceList.objects.filter(is_default=True).first()
    if default_list:
        ProductPrice.objects.update_or_create(
            product=instance, price_list=default_list, min_quantity=1,
            defaults={'price_monto': instance.precio_venta_monto, 'price_moneda': instance.precio_venta_moneda}
        )


@receiver(post_save, sender=ProductPrice)
def sync_product_price_to_article(sender, instance, **kwargs):
    if not instance.price_list.is_default or instance.min_quantity > 1: return
    articulo = instance.product
    if articulo.precio_venta_monto == instance.price_monto: return
    articulo.precio_venta_monto = instance.price_monto
    articulo._from_pricelist_sync = True
    articulo.save()
