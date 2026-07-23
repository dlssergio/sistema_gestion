# ventas/signals.py
"""
Signals del módulo de ventas.

Cambios respecto a la versión anterior:
  - intentar_cae_automatico ahora delega la petición a CELERY (tarea_solicitar_cae.delay)
    eliminando el bloqueo de respuesta web si AFIP está lento o caído.
  - REGLA NEGOCIO: Ahora respeta los parámetros de ConfiguracionEmpresa (modo manual/auto).
  - Refactorización de aplicar_movimiento_stock utilizando filtros atómicos.
  - Se agregó 'proteger_stock_aplicado' (pre_save) para prevenir el bug de doble
    descuento causado por Stale Objects (sobreescritura de memoria).
  - Logger propio por módulo con trazabilidad granular restaurada.
"""

import logging

from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver
from django.db import transaction

from .models import ComprobanteVenta, Recibo, PriceList, ProductPrice
from inventario.models import Articulo
from finanzas.models import Cheque
from inventario.services import StockManager
from parametros.models import ConfiguracionEmpresa

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 1. AUTOMATIZACIÓN CAE (ASÍNCRONO CON CELERY + SAFE COMMIT)
# ═══════════════════════════════════════════════════════════════════════════

@receiver(post_save, sender=ComprobanteVenta)
def intentar_cae_automatico(sender, instance, created, raw=False, **kwargs):
    """
    Delega la solicitud de CAE a AFIP a la cola de tareas de Celery,
    respetando los parámetros generales de la empresa y la serie seleccionada.
    """
    if raw:
        return

    # 1. Filtros básicos
    if not (
            instance.estado == ComprobanteVenta.Estado.CONFIRMADO
            and not instance.cae
            and instance.serie
    ):
        return

    # 2. Consultar la Configuración Global de la Empresa
    config = ConfiguracionEmpresa.objects.first()
    if not config:
        logger.warning("Abortando solicitud automática: No se encontró Configuración de Empresa para este esquema.")
        return

    from django.db import connection
    schema = connection.schema_name

    # Normalización absoluta de los datos leídos para evitar fallas por tipos o espacios
    modo_fact = str(getattr(config, 'modo_facturacion', 'MANUAL')).strip().upper()
    usar_fe = getattr(config, 'usar_factura_electronica', True)
    serie_auto = getattr(instance.serie, 'solicitar_cae_automaticamente', False)

    # Trazabilidad granular: Esto te imprimirá en la consola de Django qué valores reales existen en la BD
    logger.info(
        "Evaluando configuración AFIP | comprobante=%s | tenant=%s | usar_factura_electronica=%s | modo_facturacion=%s | serie_automatica=%s",
        instance.numero_completo,
        schema,
        usar_fe,
        modo_fact,
        serie_auto,
    )

    # 3. REGLAS DE NEGOCIO PARA AFIP
    # A) Si la facturación electrónica está deshabilitada globalmente -> Abortar
    if not usar_fe:
        logger.info("Solicitud automática omitida: Facturación electrónica desactivada globalmente | comprobante=%s", instance.numero_completo)
        return

    # B) Si los parámetros de la empresa indican Modo Manual (o False por checkboxes) -> Abortar
    if modo_fact in ['MANUAL', 'FALSE', '0']:
        logger.info("Solicitud automática omitida: Empresa configurada en modo MANUAL | comprobante=%s", instance.numero_completo)
        return

    # C) Si el talonario específico NO es automático -> Abortar
    if not serie_auto:
        logger.info("Solicitud automática omitida: Talonario configurado en modo MANUAL | comprobante=%s", instance.numero_completo)
        return

    # 4. Bandera en memoria: Evita encolar múltiples veces si Django guarda
    # la misma instancia repetidamente en fracciones de segundo.
    if getattr(instance, '_cae_encolado', False):
        return
    instance._cae_encolado = True

    from ventas.tasks import tarea_solicitar_cae

    logger.info(
        "Preparando solicitud de CAE asíncrona | comprobante=%s | tenant=%s",
        instance.numero_completo,
        schema,
    )

    # 5. ON_COMMIT: Garantiza que el mensaje a Celery (Redis) se envíe ÚNICAMENTE
    # cuando la transacción SQL en PostgreSQL haya finalizado exitosamente.
    transaction.on_commit(lambda: tarea_solicitar_cae.delay(instance.pk, schema))


# ═══════════════════════════════════════════════════════════════════════════
# 2. MOVIMIENTO DE STOCK (PROTECCIÓN DOBLE DESCUENTO)
# ═══════════════════════════════════════════════════════════════════════════

@receiver(pre_save, sender=ComprobanteVenta)
def proteger_stock_aplicado(sender, instance, **kwargs):
    """
    ESCUDO PROTECTOR: Previene que una instancia vieja (stale object) en memoria
    vuelva a guardar stock_aplicado=False en la base de datos, lo que causa
    el bug del doble descuento de stock.
    """
    if instance.pk:
        try:
            db_instance = ComprobanteVenta.objects.get(pk=instance.pk)
            if db_instance.stock_aplicado and not instance.stock_aplicado:
                logger.warning(
                    "Stale Object detectado y bloqueado | comprobante=%s. "
                    "Evitando reversión de stock_aplicado a False.",
                    instance.numero_completo
                )
                instance.stock_aplicado = True
        except ComprobanteVenta.DoesNotExist:
            pass


@receiver(post_save, sender=ComprobanteVenta, dispatch_uid='stock_movement_signal')
def aplicar_movimiento_stock(sender, instance, created, raw=False, **kwargs):
    """
    Maneja el impacto en stock al confirmar un comprobante.
    Implementa un candado (lock) atómico basado en el campo `stock_aplicado`.
    """
    if raw:
        return

    # Evita ejecución recursiva en la misma transacción de memoria
    if getattr(instance, '_stock_procesado', False):
        return

    if instance.estado != ComprobanteVenta.Estado.CONFIRMADO:
        return

    if instance.stock_aplicado:
        return

    if not instance.items.exists():
        return

    tipo = instance.tipo_comprobante
    if not tipo or not tipo.mueve_stock:
        return

    with transaction.atomic():
        filas_actualizadas = ComprobanteVenta.objects.filter(
            pk=instance.pk,
            stock_aplicado=False
        ).update(stock_aplicado=True)

        if filas_actualizadas == 0:
            logger.info(
                "Movimiento de stock abortado: Ya aplicado previamente o condición de carrera evitada | comprobante=%s",
                instance.numero_completo
            )
            return

        # Actualizamos la memoria
        instance.stock_aplicado = True
        instance._stock_procesado = True

        # ── Signo del movimiento ──────────────────────────────────────────────
        signo = tipo.signo_stock
        if tipo.codigo_afip in ['003', '008', '013']:  # NC
            if instance.concepto_nota_credito == ComprobanteVenta.ConceptoNC.FINANCIERO:
                logger.info(
                    "Stock no movido: NC financiera | comprobante=%s",
                    instance.numero_completo,
                )
                return
            if instance.concepto_nota_credito in [
                ComprobanteVenta.ConceptoNC.DEVOLUCION,
                ComprobanteVenta.ConceptoNC.ANULACION,
            ]:
                signo = 1

        ref = f"Venta: {tipo.nombre} {instance.numero_completo}"

        logger.info(
            "Aplicando movimiento de stock | comprobante=%s | tipo=%s | signo=%s | items=%s",
            instance.numero_completo,
            tipo.nombre,
            signo,
            instance.items.count(),
        )

        # ── A. Stock REAL (físico) ─────────────────────────────────────────────
        if getattr(tipo, 'afecta_stock_fisico', False):
            for item in instance.items.all():
                cantidad_final = abs(item.cantidad) * signo
                try:
                    StockManager.registrar_movimiento(
                        articulo=item.articulo,
                        deposito=instance.deposito,
                        codigo_tipo='REAL',
                        cantidad=cantidad_final,
                        origen_sistema='VENTAS',
                        origen_referencia=ref,
                        usuario=None,
                        permitir_stock_negativo=None,
                    )
                    logger.debug(
                        "Stock REAL movido | articulo=%s | cantidad=%s | deposito=%s",
                        item.articulo.cod_articulo,
                        cantidad_final,
                        instance.deposito.nombre if instance.deposito else '—',
                    )
                except Exception as exc:
                    logger.error(
                        "Error al mover stock REAL | comprobante=%s | articulo=%s | error=%s",
                        instance.numero_completo,
                        item.articulo.cod_articulo,
                        exc,
                        exc_info=True,
                    )
                    raise

        # ── B. Stock RSRV (comprometido) ──────────────────────────────────────
        if getattr(tipo, 'afecta_stock_comprometido', False):
            for item in instance.items.all():
                cantidad_final = abs(item.cantidad) * signo
                try:
                    StockManager.registrar_movimiento(
                        articulo=item.articulo,
                        deposito=instance.deposito,
                        codigo_tipo='RSRV',
                        cantidad=cantidad_final,
                        origen_sistema='VENTAS',
                        origen_referencia=ref,
                        usuario=None,
                        permitir_stock_negativo=True,
                    )
                    logger.debug(
                        "Stock RSRV movido | articulo=%s | cantidad=%s",
                        item.articulo.cod_articulo,
                        cantidad_final,
                    )
                except Exception as exc:
                    logger.error(
                        "Error al mover stock RSRV | comprobante=%s | articulo=%s | error=%s",
                        instance.numero_completo,
                        item.articulo.cod_articulo,
                        exc,
                        exc_info=True,
                    )
                    raise

        # ── C. Descompromiso RSRV desde nota de pedido ────────────────────────
        if getattr(tipo, 'afecta_stock_fisico', False) and not getattr(tipo, 'afecta_stock_comprometido', False):
            for origen in instance.comprobantes_asociados.all():
                tipo_origen = origen.tipo_comprobante
                if not (tipo_origen and getattr(tipo_origen, 'mueve_stock', False) and getattr(tipo_origen,
                                                                                               'afecta_stock_comprometido',
                                                                                               False)):
                    continue

                logger.info(
                    "Liberando reserva RSRV | factura=%s | pedido=%s",
                    instance.numero_completo,
                    origen.numero_completo,
                )

                for item_factura in instance.items.all():
                    try:
                        StockManager.registrar_movimiento(
                            articulo=item_factura.articulo,
                            deposito=instance.deposito,
                            codigo_tipo='RSRV',
                            cantidad=-abs(item_factura.cantidad),
                            origen_sistema='VENTAS',
                            origen_referencia=(
                                f"Descompromiso {instance.numero_completo} "
                                f"(Ref: {origen.numero_completo})"
                            ),
                            usuario=None,
                            permitir_stock_negativo=True,
                        )
                    except Exception as exc:
                        logger.error(
                            "Error al liberar reserva RSRV | factura=%s | articulo=%s | error=%s",
                            instance.numero_completo,
                            item_factura.articulo.cod_articulo,
                            exc,
                            exc_info=True,
                        )
                        raise

        logger.info(
            "Movimiento de stock completado exitosamente | comprobante=%s | stock_aplicado=True",
            instance.numero_completo,
        )


# ═══════════════════════════════════════════════════════════════════════════
# 3. FINANZAS
# ═══════════════════════════════════════════════════════════════════════════

@receiver(post_save, sender=Recibo)
def trigger_finanzas_recibo(sender, instance, **kwargs):
    """Revierte finanzas automáticamente cuando un recibo es anulado."""
    if instance.estado == Recibo.Estado.ANULADO:
        logger.info("Revirtiendo finanzas | recibo=%s", instance.numero or instance.pk)
        instance.revertir_finanzas()


@receiver(pre_delete, sender=Recibo)
def reversar_al_eliminar_recibo(sender, instance, **kwargs):
    """Revierte el impacto financiero antes de eliminar un recibo."""
    if not instance.finanzas_aplicadas:
        return

    logger.warning(
        "Eliminando recibo con finanzas aplicadas — revirtiendo | recibo=%s",
        instance.numero or instance.pk,
    )

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
                Cheque.objects.filter(numero=valor.referencia).update(
                    estado=Cheque.Estado.ANULADO
                )


# ═══════════════════════════════════════════════════════════════════════════
# 4. PRECIOS
# ═══════════════════════════════════════════════════════════════════════════

@receiver(post_save, sender=Articulo)
def manage_default_product_price(sender, instance, **kwargs):
    """Sincroniza el precio del artículo a la lista de precios por defecto."""
    if getattr(instance, '_from_pricelist_sync', False):
        return
    default_list = PriceList.objects.filter(is_default=True).first()
    if not default_list:
        return
    ProductPrice.objects.update_or_create(
        product=instance,
        price_list=default_list,
        min_quantity=1,
        defaults={
            'price_monto': instance.precio_venta_monto,
            'price_moneda': instance.precio_venta_moneda,
        }
    )


@receiver(post_save, sender=ProductPrice)
def sync_product_price_to_article(sender, instance, **kwargs):
    """Refleja el cambio de precio en la lista default de vuelta al artículo."""
    if not instance.price_list.is_default or instance.min_quantity > 1:
        return
    articulo = instance.product
    if articulo.precio_venta_monto == instance.price_monto:
        return
    articulo.precio_venta_monto = instance.price_monto
    articulo._from_pricelist_sync = True
    articulo.save()