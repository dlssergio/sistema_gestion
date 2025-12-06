# compras/models.py (VERSIÓN FINAL DEFINITIVA - SIN ERRORES)

from django.db import models, transaction
from decimal import Decimal
from djmoney.models.fields import MoneyField
from djmoney.money import Money
from django.db.models.signals import pre_save, post_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.conf import settings

from entidades.models import Entidad
from parametros.models import Contador, TipoComprobante, Role, Moneda, UnidadMedida, get_default_unidad_medida
from inventario.services import StockService
from finanzas.models import TipoValor, CuentaFondo, Cheque, MovimientoFondo, Banco


def get_default_moneda_pk():
    """
    Obtiene el PK de la moneda base o crea una por defecto (ARS) si no existe.
    Esto es crucial para que las migraciones no fallen en una base de datos vacía.
    """
    moneda, created = Moneda.objects.get_or_create(
        es_base=True,
        defaults={'nombre': 'Peso Argentino', 'simbolo': 'ARS', 'cotizacion': 1.00}
    )
    return moneda.pk


# --- PROVEEDOR ---
class Proveedor(models.Model):
    entidad = models.OneToOneField(Entidad, on_delete=models.CASCADE, primary_key=True)
    codigo_proveedor = models.CharField(max_length=50, unique=True, blank=True, null=True, verbose_name="Código")
    nombre_fantasia = models.CharField(max_length=255, blank=True, null=True, verbose_name="Nombre de Fantasía")
    limite_credito = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Límite Crédito")
    roles = models.ManyToManyField(Role, blank=True, help_text="Roles que pueden gestionar este proveedor.")

    def __str__(self):
        return self.entidad.razon_social

    def save(self, *args, **kwargs):
        if not self.codigo_proveedor:
            try:
                with transaction.atomic():
                    contador, _ = Contador.objects.get_or_create(nombre='codigo_proveedor',
                                                                 defaults={'prefijo': 'P', 'ultimo_valor': 0})
                    contador.ultimo_valor += 1
                    self.codigo_proveedor = f"{contador.prefijo}{str(contador.ultimo_valor).zfill(5)}"
                    contador.save()
            except Exception:
                pass
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Proveedor"
        verbose_name_plural = "Proveedores"


# --- COMPROBANTE DE COMPRA ---
class ComprobanteCompra(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = 'BR', 'Borrador'
        CONFIRMADO = 'CN', 'Confirmado'
        ANULADO = 'AN', 'Anulado'

    class CondicionCompra(models.TextChoices):
        CONTADO = 'CO', 'Contado'
        CTA_CTE = 'CC', 'Cuenta Corriente'

    serie = models.ForeignKey('parametros.SerieDocumento', on_delete=models.PROTECT, null=True, blank=True,
                              verbose_name="Serie (Opcional)", help_text="Usar solo para comprobantes propios.")
    proveedor = models.ForeignKey('Proveedor', on_delete=models.PROTECT, verbose_name="Proveedor")
    deposito = models.ForeignKey('inventario.Deposito', on_delete=models.PROTECT, null=True, blank=True)
    tipo_comprobante = models.ForeignKey('parametros.TipoComprobante', on_delete=models.PROTECT,
                                         verbose_name="Tipo de Comprobante")

    letra = models.CharField(max_length=1, editable=False)
    punto_venta = models.PositiveIntegerField(default=1, verbose_name="Punto de Venta")
    numero = models.PositiveIntegerField(verbose_name="Número")
    fecha = models.DateField(verbose_name="Fecha del Comprobante", default=timezone.now)
    estado = models.CharField(max_length=2, choices=Estado.choices, default=Estado.BORRADOR, verbose_name="Estado")
    condicion_compra = models.CharField(max_length=2, choices=CondicionCompra.choices, default=CondicionCompra.CTA_CTE,
                                        verbose_name="Condición")

    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    impuestos = models.JSONField(default=dict, editable=False)
    total = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    saldo_pendiente = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)

    comprobante_origen = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True,
                                           related_name='comprobantes_derivados')
    stock_aplicado = models.BooleanField(default=False, editable=False)

    def __str__(self):
        return f"{self.tipo_comprobante.nombre} {self.letra} {self.punto_venta:05d}-{self.numero:08d} - {self.proveedor}"

    def save(self, *args, **kwargs):
        if self.serie:
            self.tipo_comprobante = self.serie.tipo_comprobante
            if not self.deposito and self.serie.deposito_defecto:
                self.deposito = self.serie.deposito_defecto
            if not self.serie.es_manual and not self.numero:
                from parametros.models import SerieDocumento
                with transaction.atomic():
                    serie_lock = SerieDocumento.objects.select_for_update().get(pk=self.serie.pk)
                    self.numero = serie_lock.ultimo_numero + 1
                    serie_lock.ultimo_numero = self.numero
                    serie_lock.save()

        if self.tipo_comprobante:
            self.letra = self.tipo_comprobante.letra

        # Depósito por defecto si está vacío
        if not self.deposito_id and self.deposito is None:
            from inventario.models import Deposito
            deposito_principal = Deposito.objects.filter(es_principal=True).first()
            if deposito_principal:
                self.deposito = deposito_principal

        super().save(*args, **kwargs)

    def clean(self):
        if self.estado == self.Estado.CONFIRMADO:
            if not self.deposito:
                from inventario.models import Deposito
                if not Deposito.objects.filter(es_principal=True).exists() and not self.serie:
                    raise ValidationError({'deposito': "Debe seleccionar un Depósito o definir uno principal."})

    class Meta:
        verbose_name = "Comprobante de Compra"; verbose_name_plural = "Comprobantes de Compra"


class ComprobanteCompraItem(models.Model):
    comprobante = models.ForeignKey(ComprobanteCompra, related_name='items', on_delete=models.CASCADE)
    articulo = models.ForeignKey('inventario.Articulo', on_delete=models.PROTECT, verbose_name="Artículo")
    cantidad = models.DecimalField(max_digits=10, decimal_places=3)
    precio_costo_unitario_monto = models.DecimalField(max_digits=14, decimal_places=4, verbose_name="Costo Unitario",
                                                      default=0)
    precio_costo_unitario_moneda = models.ForeignKey(Moneda, on_delete=models.PROTECT, default=get_default_moneda_pk)
    datos_costo_efectivo = models.JSONField(default=dict, editable=False)

    @property
    def precio_costo_unitario(self): return Money(self.precio_costo_unitario_monto,
                                                  self.precio_costo_unitario_moneda.simbolo)

    @property
    def subtotal(self): return (self.cantidad or Decimal(0)) * self.precio_costo_unitario

    def __str__(self): return f"{self.cantidad} x {self.articulo.descripcion}"


# --- LISTAS DE PRECIOS (CONDENSADO, SIN CAMBIOS) ---
class ListaPreciosProveedor(models.Model):
    proveedor = models.ForeignKey('Proveedor', on_delete=models.CASCADE, related_name='listas_precios')
    nombre = models.CharField(max_length=100, verbose_name="Nombre de la Lista")
    codigo = models.CharField(max_length=20, blank=True, verbose_name="Código")
    vigente_desde = models.DateField(default=timezone.now, verbose_name="Vigente Desde")
    vigente_hasta = models.DateField(null=True, blank=True, verbose_name="Vigente Hasta")
    es_activa = models.BooleanField(default=True, verbose_name="¿Está Activa?")
    es_principal = models.BooleanField(default=False, verbose_name="¿Es la Lista Principal?")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    observaciones = models.TextField(blank=True, verbose_name="Observaciones")

    def clean(self):
        if self.vigente_hasta and self.vigente_desde > self.vigente_hasta: raise ValidationError(
            "La fecha de fin debe ser posterior a la fecha de inicio")
        if self.es_principal:
            if ListaPreciosProveedor.objects.filter(proveedor=self.proveedor, es_principal=True).exclude(
                    pk=self.pk).exists():
                raise ValidationError(f"El proveedor ya tiene una lista principal")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.es_principal:
            ListaPreciosProveedor.objects.filter(proveedor=self.proveedor, es_principal=True).exclude(
                pk=self.pk).update(es_principal=False)

    def __str__(self):
        return f"{self.proveedor.entidad.razon_social} - {self.nombre}"

    class Meta:
        verbose_name = "1. Lista de Precios de Proveedor"
        verbose_name_plural = "1. Listas de Precios de Proveedores"
        ordering = ['proveedor__entidad__razon_social', '-es_principal', '-vigente_desde']
        unique_together = ['proveedor', 'nombre']


class ItemListaPreciosProveedor(models.Model):
    lista_precios = models.ForeignKey(ListaPreciosProveedor, on_delete=models.CASCADE, related_name='items')
    articulo = models.ForeignKey('inventario.Articulo', on_delete=models.CASCADE, related_name='precios_proveedor')
    unidad_medida_compra = models.ForeignKey('parametros.UnidadMedida', on_delete=models.PROTECT,
                                             verbose_name="Unidad Compra")
    precio_lista_monto = models.DecimalField(max_digits=14, decimal_places=4, verbose_name="Monto", default=0)
    precio_lista_moneda = models.ForeignKey(Moneda, on_delete=models.PROTECT, default=get_default_moneda_pk)
    bonificacion_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="Bonif (%)")
    descuentos_adicionales = models.JSONField(default=list, blank=True)
    descuentos_financieros = models.JSONField(default=list, blank=True)
    cantidad_minima = models.DecimalField(max_digits=10, decimal_places=3, default=1)
    codigo_articulo_proveedor = models.CharField(max_length=50, blank=True)

    @property
    def precio_lista(self): return Money(self.precio_lista_monto, self.precio_lista_moneda.simbolo)

    @property
    def costo_efectivo(self):
        from compras.services import CostCalculatorService
        return CostCalculatorService.calculate_effective_cost(self)

    def __str__(self): return f"{self.articulo.descripcion}"

    class Meta: verbose_name = "2. Ítem de Lista"; verbose_name_plural = "2. Ítems de Listas"; unique_together = [
        'lista_precios', 'articulo', 'cantidad_minima']


class HistorialPrecioProveedor(models.Model):
    item = models.ForeignKey(ItemListaPreciosProveedor, on_delete=models.CASCADE, related_name='historial')
    precio_lista_anterior = MoneyField(max_digits=14, decimal_places=4, default_currency='ARS')
    precio_lista_nuevo = MoneyField(max_digits=14, decimal_places=4, default_currency='ARS')
    costo_efectivo_anterior = MoneyField(max_digits=14, decimal_places=4, default_currency='ARS', null=True)
    costo_efectivo_nuevo = MoneyField(max_digits=14, decimal_places=4, default_currency='ARS', null=True)
    fecha_cambio = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    motivo = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "3. Historial"
        verbose_name_plural = "3. Historiales"
        ordering = ['-fecha_cambio']


# --- ORDEN DE PAGO (CORREGIDA) ---
class OrdenPago(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = 'BR', 'Borrador'
        CONFIRMADO = 'CN', 'Confirmado'
        ANULADO = 'AN', 'Anulado'

    serie = models.ForeignKey('parametros.SerieDocumento', on_delete=models.PROTECT, null=True, blank=True,
                              verbose_name="Serie (Opcional)")
    numero = models.PositiveIntegerField(verbose_name="Número", blank=True, null=True)
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT)
    fecha = models.DateField(default=timezone.now)
    estado = models.CharField(max_length=2, choices=Estado.choices, default=Estado.BORRADOR)
    monto_total = models.DecimalField(max_digits=14, decimal_places=2, default=0, editable=False)
    observaciones = models.TextField(blank=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    finanzas_aplicadas = models.BooleanField(default=False, editable=False)

    def save(self, *args, **kwargs):
        if self.serie and not self.numero and not self.serie.es_manual:
            from parametros.models import SerieDocumento
            with transaction.atomic():
                serie_lock = SerieDocumento.objects.select_for_update().get(pk=self.serie.pk)
                siguiente = serie_lock.ultimo_numero + 1
                self.numero = siguiente
                serie_lock.ultimo_numero = siguiente
                serie_lock.save()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"OP #{self.numero or '?'} - {self.proveedor}"

    # MÉTODO 1: APLICAR
    def aplicar_finanzas(self):
        """
        Ejecuta el impacto financiero:
        - Baja deuda de facturas.
        - Genera movimientos de caja/banco.
        - Emite cheques.
        """
        if self.estado != self.Estado.CONFIRMADO or self.finanzas_aplicadas: return
        if not self.valores.exists(): return

        with transaction.atomic():
            # A. Salida Dinero
            for valor in self.valores.all():
                cheque_implicado = None
                # 1. Cheque Propio
                if valor.tipo.es_cheque and valor.cheque_propio_nro:
                    cheque_implicado = Cheque.objects.create(
                        numero=valor.cheque_propio_nro,
                        banco=valor.origen.banco,
                        monto=valor.monto,
                        moneda=valor.origen.moneda,
                        fecha_emision=self.fecha,
                        fecha_pago=valor.fecha_pago_cheque or self.fecha,
                        tipo_cheque='FIS',
                        origen=Cheque.Origen.PROPIO,
                        estado=Cheque.Estado.ENTREGADO,
                        nombre_librador="EMPRESA PROPIA"
                    )
                # 2. Cheque Tercero
                elif valor.cheque_tercero:
                    cheque_implicado = valor.cheque_tercero
                    cheque_implicado.estado = Cheque.Estado.ENTREGADO
                    cheque_implicado.save()

                MovimientoFondo.objects.create(
                    fecha=self.fecha,
                    cuenta=valor.origen,
                    tipo_movimiento=MovimientoFondo.TipoMov.EGRESO,
                    tipo_valor=valor.tipo,
                    monto_egreso=valor.monto,
                    concepto=f"Pago OP #{self.numero} - {self.proveedor}",
                    usuario=self.creado_por,
                    cheque=cheque_implicado
                )
                valor.origen.saldo_monto -= valor.monto
                valor.origen.save()

            # B. Bajar Deuda
            for imputacion in self.imputaciones.all():
                comp = imputacion.comprobante
                comp.saldo_pendiente -= imputacion.monto_imputado
                if comp.saldo_pendiente < 0: comp.saldo_pendiente = 0
                comp.save()

            self.finanzas_aplicadas = True
            self.save(update_fields=['finanzas_aplicadas'])

    # MÉTODO 2: REVERTIR (Fix para eliminar)
    def revertir_finanzas(self):
        """Reversión sin chequeo de estado ANULADO, para soportar borrado físico."""
        if not self.finanzas_aplicadas: return

        # Carga ansiosa para pre_delete
        imputaciones = list(self.imputaciones.all())
        valores = list(self.valores.all())

        with transaction.atomic():
            # 1. Devolver Deuda
            for imputacion in imputaciones:
                comp = imputacion.comprobante
                comp.saldo_pendiente += imputacion.monto_imputado
                comp.save()

            # 2. Devolver Dinero
            for valor in valores:
                valor.origen.saldo_monto += valor.monto
                valor.origen.save()

                # Anular cheque propio
                if valor.tipo.es_cheque and valor.cheque_propio_nro:
                    Cheque.objects.filter(numero=valor.cheque_propio_nro, origen=Cheque.Origen.PROPIO).update(
                        estado=Cheque.Estado.ANULADO)

                # Devolver cheque tercero
                if valor.cheque_tercero:
                    valor.cheque_tercero.estado = Cheque.Estado.EN_CARTERA
                    valor.cheque_tercero.save()

            self.finanzas_aplicadas = False
            self.save(update_fields=['finanzas_aplicadas'])

    class Meta:
        verbose_name = "Orden de Pago"; verbose_name_plural = "Órdenes de Pago"


class OrdenPagoImputacion(models.Model):
    orden_pago = models.ForeignKey(OrdenPago, related_name='imputaciones', on_delete=models.CASCADE)
    comprobante = models.ForeignKey(ComprobanteCompra, on_delete=models.PROTECT, verbose_name="Factura a Pagar")
    monto_imputado = models.DecimalField(max_digits=14, decimal_places=2)

    def __str__(self): return f"Pago a {self.comprobante}"


class OrdenPagoValor(models.Model):
    orden_pago = models.ForeignKey(OrdenPago, related_name='valores', on_delete=models.CASCADE)
    tipo = models.ForeignKey(TipoValor, on_delete=models.PROTECT)
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    origen = models.ForeignKey(CuentaFondo, on_delete=models.PROTECT, verbose_name="Caja/Cuenta Origen")
    cheque_propio_nro = models.CharField(max_length=50, blank=True, verbose_name="N° Cheque Propio")
    fecha_pago_cheque = models.DateField(null=True, blank=True)
    cheque_tercero = models.ForeignKey(Cheque, on_delete=models.SET_NULL, null=True, blank=True,
                                       limit_choices_to={'estado': 'CA'})
    referencia = models.CharField(max_length=100, blank=True, verbose_name="Ref/Transf")

    def __str__(self): return f"{self.tipo} ${self.monto}"


# --- SIGNALS ---
@receiver(pre_save, sender=ItemListaPreciosProveedor)
def crear_historial_precio(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = sender.objects.get(pk=instance.pk)
            if old.precio_lista_monto != instance.precio_lista_monto:
                HistorialPrecioProveedor.objects.create(
                    item=instance,
                    precio_lista_anterior=old.precio_lista,
                    precio_lista_nuevo=instance.precio_lista,
                    costo_efectivo_anterior=None,
                    costo_efectivo_nuevo=None,
                    motivo="Actualización manual."
                )
        except Exception:
            pass


@receiver(post_save, sender=ItemListaPreciosProveedor)
def actualizar_costo_articulo_signal(sender, instance, created, **kwargs):
    """
    Signal robusta para actualizar el costo del artículo maestro.
    """
    articulo = instance.articulo
    prov_lista = instance.lista_precios.proveedor
    prov_auth = articulo.proveedor_actualiza_precio
    if prov_auth and prov_lista and prov_auth.pk == prov_lista.pk:
        costo_nuevo = instance.costo_efectivo
        if not costo_nuevo or costo_nuevo.amount == 0: costo_nuevo = instance.precio_lista
        monto_new = costo_nuevo.amount
        mon_new = costo_nuevo.currency.code
        mon_curr = articulo.precio_costo_moneda.simbolo if articulo.precio_costo_moneda else 'ARS'
        if (articulo.precio_costo_monto != monto_new) or (mon_curr != mon_new):
            articulo.precio_costo_monto = monto_new
            try:
                mon_obj = Moneda.objects.filter(simbolo=mon_new).first()
                if mon_obj: articulo.precio_costo_moneda = mon_obj
            except Exception:
                pass
            articulo.save()


@receiver(post_save, sender=ComprobanteCompra)
def aplicar_stock_compra(sender, instance, **kwargs):
    if instance.estado == ComprobanteCompra.Estado.CONFIRMADO and not instance.stock_aplicado:
        items = instance.items.all()
        if not items.exists(): return
        for item in items:
            StockService.ajustar_stock(item.articulo, instance.deposito, item.cantidad, 'SUMAR')
        ComprobanteCompra.objects.filter(pk=instance.pk).update(stock_aplicado=True)


# SIGNALS ORDEN PAGO
@receiver(post_save, sender=OrdenPago)
def trigger_finanzas_orden_pago(sender, instance, **kwargs):
    if instance.estado == OrdenPago.Estado.ANULADO:
        instance.revertir_finanzas()


@receiver(pre_delete, sender=OrdenPago)
def reversar_al_eliminar_op(sender, instance, **kwargs):
    if instance.finanzas_aplicadas:
        instance.revertir_finanzas()