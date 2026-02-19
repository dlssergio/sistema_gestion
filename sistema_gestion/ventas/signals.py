# ventas/signals.py (CORREGIDO PARA RESPETAR GATEKEEPER Y RSRV)

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.db import transaction
from .models import ComprobanteVenta, Recibo, PriceList, ProductPrice
from inventario.models import Articulo
from finanzas.models import Cheque
from inventario.services import StockManager  # Usamos el nuevo Manager


# --- 1. AUTOMATIZACIÓN CAE ---
@receiver(post_save, sender=ComprobanteVenta)
def intentar_cae_automatico(sender, instance, created, **kwargs):
    if instance.estado == ComprobanteVenta.Estado.CONFIRMADO and not instance.cae and instance.serie:
        if instance.serie.solicitar_cae_automaticamente:
            from parametros.afip import AfipManager
            try:
                print(f"⚡ Iniciando CAE Automático para {instance.numero_completo}...")
                afip = AfipManager()
                afip.emitir_comprobante(instance)
            except Exception as e:
                print(f"❌ Error CAE Automático: {e}")
                instance.afip_error = str(e)
                instance.save(update_fields=['afip_error'])


# --- 2. LÓGICA DE STOCK HÍBRIDA (ENTERPRISE) ---
@receiver(post_save, sender=ComprobanteVenta, dispatch_uid='stock_movement_signal')
def aplicar_movimiento_stock(sender, instance, **kwargs):
    """
    Maneja:
    1. El movimiento propio del comprobante (Ej: Factura baja Real).
    2. El efecto de los orígenes (Ej: Si viene de Nota de Pedido, baja Comprometido).
    """
    # A. Validaciones
    if instance.estado != ComprobanteVenta.Estado.CONFIRMADO: return
    if instance.pk: instance.refresh_from_db(fields=['stock_aplicado'])
    if instance.stock_aplicado: return
    if not instance.items.exists(): return

    tipo = instance.tipo_comprobante

    # Interruptor general
    if not tipo or not tipo.mueve_stock: return

    # B. Signo Base
    signo = tipo.signo_stock
    if tipo.codigo_afip in ['003', '008', '013']:  # NC (Notas de Crédito)
        if instance.concepto_nota_credito == ComprobanteVenta.ConceptoNC.FINANCIERO:
            return
        if instance.concepto_nota_credito in [ComprobanteVenta.ConceptoNC.DEVOLUCION,
                                              ComprobanteVenta.ConceptoNC.ANULACION]:
            signo = 1

    # C. Ejecución de Movimientos
    ref = f"Venta: {tipo.nombre} {instance.numero_completo}"

    for item in instance.items.all():
        cantidad_abs = abs(item.cantidad)
        cantidad_final = cantidad_abs * signo  # Normalmente negativo para ventas

        # 1. Impacto REAL (Físico)
        # Esto ocurre si es Factura o Remito
        if tipo.afecta_stock_fisico:
            StockManager.registrar_movimiento(
                articulo=item.articulo,
                deposito=instance.deposito,
                codigo_tipo='REAL',
                cantidad=cantidad_final,
                origen_sistema='VENTAS',
                origen_referencia=ref,
                usuario=None,
                # CAMBIO CRÍTICO: Pasamos None para que StockManager verifique los flags
                # de Artículo y Depósito. Si es False (default), rechazará stock negativo.
                permitir_stock_negativo=None
            )

        # 2. Impacto RSRV (Comprometido) - DIRECTO
        # Esto ocurre SOLO si el comprobante actual es una Nota de Pedido / Reserva.
        # Una Factura NO debería entrar aquí (si está bien configurada).
        if tipo.afecta_stock_comprometido:
            StockManager.registrar_movimiento(
                articulo=item.articulo,
                deposito=instance.deposito,
                codigo_tipo='RSRV',
                cantidad=cantidad_final,  # En NP, signo suele ser positivo (suma reserva)
                origen_sistema='VENTAS',
                origen_referencia=ref,
                usuario=None,
                permitir_stock_negativo=True  # Las reservas suelen permitir ir a negativo virtualmente si se configura
            )

    # D. Lógica de Descompromiso (Impacto RSRV - INDIRECTO)
    # Si este comprobante mueve Físico (es Factura) Y NO mueve Comprometido (no es Pedido),
    # entonces revisamos si viene de un Pedido para "liberar" esa reserva.
    if tipo.afecta_stock_fisico and not tipo.afecta_stock_comprometido:
        for origen in instance.comprobantes_asociados.all():
            tipo_origen = origen.tipo_comprobante

            # Si el origen era una reserva (Suma RSRV)
            if tipo_origen.mueve_stock and tipo_origen.afecta_stock_comprometido:
                print(f"🔄 Liberando reserva de {origen}")
                for item_factura in instance.items.all():
                    # Liberamos (Restamos) del RSRV la cantidad que estamos facturando
                    StockManager.registrar_movimiento(
                        articulo=item_factura.articulo,
                        deposito=instance.deposito,
                        codigo_tipo='RSRV',
                        cantidad=-abs(item_factura.cantidad),  # Siempre negativo para liberar
                        origen_sistema='VENTAS',
                        origen_referencia=f"Descompromiso {instance.numero_completo} (Ref: {origen.numero_completo})",
                        usuario=None,
                        permitir_stock_negativo=True
                    )

    # E. Bloqueo
    ComprobanteVenta.objects.filter(pk=instance.pk).update(stock_aplicado=True)
    instance.stock_aplicado = True


# --- 3. FINANZAS ---
@receiver(post_save, sender=Recibo)
def trigger_finanzas_recibo(sender, instance, **kwargs):
    if instance.estado == Recibo.Estado.ANULADO: instance.revertir_finanzas()


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


# --- 4. PRECIOS ---
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