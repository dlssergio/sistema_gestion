# ventas/models.py (VERSIÓN FINAL DEFINITIVA)

from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal
from djmoney.money import Money
from inventario.services import StockService
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.conf import settings
from finanzas.models import TipoValor, CuentaFondo, Cheque, MovimientoFondo, Banco


def get_default_moneda_pk():
    from parametros.models import Moneda
    moneda, _ = Moneda.objects.get_or_create(
        es_base=True,
        defaults={'nombre': 'Peso Argentino', 'simbolo': 'ARS', 'cotizacion': 1.00}
    )
    return moneda.pk


# --- CLIENTE, COMPROBANTES, LISTAS ---
class Cliente(models.Model):
    entidad = models.OneToOneField('entidades.Entidad', on_delete=models.CASCADE, primary_key=True)
    price_list = models.ForeignKey(
        'PriceList',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Lista de Precios Asignada"
    )
    permite_cta_cte = models.BooleanField(default=False, verbose_name="Habilitar Cuenta Corriente",
                                          help_text="Si está desactivado, este cliente solo puede operar de CONTADO.")
    limite_credito = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Límite de Crédito")

    def __str__(self):
        return self.entidad.razon_social

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"


class ComprobanteVenta(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = 'BR', 'Borrador'
        CONFIRMADO = 'CN', 'Confirmado'
        ANULADO = 'AN', 'Anulado'

    class CondicionVenta(models.TextChoices):
        CONTADO = 'CO', 'Contado'
        CTA_CTE = 'CC', 'Cuenta Corriente'

    serie = models.ForeignKey('parametros.SerieDocumento', on_delete=models.PROTECT,
                              null=True, blank=True, verbose_name="Serie / Talonario")
    tipo_comprobante = models.ForeignKey('parametros.TipoComprobante', on_delete=models.PROTECT,
                                         null=True, blank=True, verbose_name="Tipo de Comprobante")
    numero = models.PositiveIntegerField(blank=True, null=True, verbose_name="Número")
    letra = models.CharField(max_length=1, editable=False)
    punto_venta = models.PositiveIntegerField(default=1, verbose_name="Punto de Venta")
    cliente = models.ForeignKey('Cliente', on_delete=models.PROTECT, verbose_name="Cliente")
    fecha = models.DateField(default=timezone.now, verbose_name="Fecha del Comprobante")
    estado = models.CharField(max_length=2, choices=Estado.choices, default=Estado.BORRADOR)
    condicion_venta = models.CharField(max_length=2, choices=CondicionVenta.choices, default=CondicionVenta.CONTADO)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    impuestos = models.JSONField(default=dict, editable=False)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    saldo_pendiente = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    deposito = models.ForeignKey('inventario.Deposito', on_delete=models.PROTECT, null=True, blank=True)
    stock_aplicado = models.BooleanField(default=False, editable=False)

    @property
    def numero_completo(self):
        return f"{self.letra} {self.punto_venta:05d}-{self.numero or 0:08d}"

    @property
    def estado_pago(self):
        if self.saldo_pendiente == 0: return "PAGADO"
        if self.saldo_pendiente == self.total: return "IMPAGO"
        return "PARCIAL"

    def clean(self):
        if self.condicion_venta == self.CondicionVenta.CTA_CTE and not self.cliente.permite_cta_cte:
            raise ValidationError(
                f"El cliente {self.cliente} NO está habilitado para operar en Cuenta Corriente. Debe ser CONTADO.")

    def save(self, *args, **kwargs):
        if self.serie:
            self.tipo_comprobante = self.serie.tipo_comprobante
            self.letra = self.serie.tipo_comprobante.letra
            self.punto_venta = self.serie.punto_venta
            if not self.deposito and self.serie.deposito_defecto:
                self.deposito = self.serie.deposito_defecto
            if not self.serie.es_manual and not self.numero:
                from parametros.models import SerieDocumento
                with transaction.atomic():
                    serie_lock = SerieDocumento.objects.select_for_update().get(pk=self.serie.pk)
                    self.numero = serie_lock.ultimo_numero + 1
                    serie_lock.ultimo_numero = self.numero
                    serie_lock.save()
        if self.tipo_comprobante and not self.letra:
            self.letra = self.tipo_comprobante.letra
        from inventario.models import Deposito
        if not self.deposito_id and self.deposito is None:
            deposito_principal = Deposito.objects.filter(es_principal=True).first()
            if deposito_principal:
                self.deposito = deposito_principal
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.tipo_comprobante.nombre if self.tipo_comprobante else 'Venta'} {self.numero_completo} - {self.cliente}"

    class Meta:
        verbose_name = "Comprobante de Venta"
        verbose_name_plural = "Comprobantes de Venta"


class ComprobanteVentaItem(models.Model):
    comprobante = models.ForeignKey(ComprobanteVenta, related_name='items', on_delete=models.CASCADE)
    articulo = models.ForeignKey('inventario.Articulo', on_delete=models.PROTECT, verbose_name="Artículo")
    cantidad = models.DecimalField(max_digits=10, decimal_places=3)
    precio_unitario_original = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Precio Unitario")

    @property
    def subtotal(self):
        return (self.cantidad or Decimal(0)) * (self.precio_unitario_original or Decimal(0))

    def __str__(self):
        return f"{self.cantidad} x {self.articulo.descripcion}"


class PriceList(models.Model):
    name = models.CharField(max_length=100, verbose_name="Nombre")
    code = models.CharField(max_length=20, unique=True, verbose_name="Código")
    valid_from = models.DateField(verbose_name="Válido Desde", null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True, verbose_name="Válido Hasta")
    is_default = models.BooleanField(default=False, verbose_name="¿Es la lista por defecto?")
    discount_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        verbose_name="Descuento general (%)"
    )
    formula = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Fórmula de Precio Personalizada",
        help_text="Ej: 'costo * 1.5 + 50'. Usa 'costo' como variable. Se aplica si no hay precio específico."
    )

    class Meta:
        verbose_name = "Lista de Precios de Venta"
        verbose_name_plural = "Listas de Precios de Venta"

    def __str__(self):
        return self.name


class ProductPrice(models.Model):
    """
    Define el precio de un producto para una lista de precios específica,
    con soporte para precios escalonados por cantidad.
    """
    product = models.ForeignKey('inventario.Articulo', on_delete=models.CASCADE, related_name='sales_prices')
    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name='product_prices')
    price_monto = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Monto del Precio")
    price_moneda = models.ForeignKey('parametros.Moneda', on_delete=models.PROTECT, default=get_default_moneda_pk)
    min_quantity = models.DecimalField(max_digits=10, decimal_places=3, default=1, verbose_name="Cantidad Mínima")
    max_quantity = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True,
                                       verbose_name="Cantidad Máxima")

    @property
    def price(self): return Money(self.price_monto, self.price_moneda.simbolo)

    class Meta:
        unique_together = ['product', 'price_list', 'min_quantity']
        ordering = ['min_quantity']
        verbose_name = "Precio de Producto"
        verbose_name_plural = "Precios de Productos"

# --- RECIBOS (MODELO CORREGIDO) ---

class Recibo(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = 'BR', 'Borrador'
        CONFIRMADO = 'CN', 'Confirmado'
        ANULADO = 'AN', 'Anulado'

    class Origen(models.TextChoices):
        COBRANZA = 'CTA', 'Cobranza Cuenta Corriente'
        CONTADO = 'CON', 'Venta Contado'

    serie = models.ForeignKey('parametros.SerieDocumento', on_delete=models.PROTECT,
                              null=True, blank=True)
    numero = models.PositiveIntegerField(blank=True, null=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT)
    fecha = models.DateField(default=timezone.now)
    estado = models.CharField(max_length=2, choices=Estado.choices, default=Estado.BORRADOR)
    monto_total = models.DecimalField(max_digits=14, decimal_places=2, default=0, editable=False)
    observaciones = models.TextField(blank=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    finanzas_aplicadas = models.BooleanField(default=False, editable=False)
    origen = models.CharField(max_length=3, choices=Origen.choices, default=Origen.COBRANZA,
                              verbose_name="Origen de Fondos")

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

    # MÉTODO 1: APLICAR
    def aplicar_finanzas(self):
        if self.estado != self.Estado.CONFIRMADO or self.finanzas_aplicadas: return

        # Validación Balanceo
        total_valores = sum(v.monto for v in self.valores.all())
        total_imputado = sum(i.monto_imputado for i in self.imputaciones.all())
        if abs(total_imputado - total_valores) > Decimal('0.05'):
            raise ValidationError(
                f"Desbalance: Valores ${total_valores} vs Imputado ${total_imputado}.")
        if not self.valores.exists():
            raise ValidationError("Debe ingresar valores de pago.")

        with transaction.atomic():
            # A. Ingreso Dinero
            for valor in self.valores.all():
                nuevo_cheque = None
                if valor.tipo.es_cheque and not valor.cheque_tercero:
                    nuevo_cheque = Cheque.objects.create(
                        numero=valor.referencia, banco=valor.banco_origen, monto=valor.monto,
                        moneda=valor.destino.moneda, fecha_emision=self.fecha,
                        fecha_pago=valor.fecha_cobro or self.fecha, tipo_cheque='FIS',
                        origen=Cheque.Origen.TERCERO, estado=Cheque.Estado.EN_CARTERA,
                        cuit_librador=valor.cuit_librador, nombre_librador=f"Cliente: {self.cliente}"
                    )
                MovimientoFondo.objects.create(
                    fecha=self.fecha, cuenta=valor.destino, tipo_movimiento=MovimientoFondo.TipoMov.INGRESO,
                    tipo_valor=valor.tipo, monto_ingreso=valor.monto,
                    concepto=f"Cobro Recibo #{self.numero} - {self.cliente}",
                    usuario=self.creado_por, cheque=nuevo_cheque or valor.cheque_tercero
                )
                valor.destino.saldo_monto += valor.monto
                valor.destino.save()

            # B. Bajar Deuda
            for imputacion in self.imputaciones.all():
                comp = imputacion.comprobante
                comp.saldo_pendiente -= imputacion.monto_imputado
                if comp.saldo_pendiente < 0: comp.saldo_pendiente = 0
                comp.save()

            self.finanzas_aplicadas = True
            self.save(update_fields=['finanzas_aplicadas'])

    # MÉTODO 2: REVERTIR
    def revertir_finanzas(self):
        if not self.finanzas_aplicadas: return

        imputaciones = list(self.imputaciones.all())
        valores = list(self.valores.all())

        with transaction.atomic():
            for imputacion in imputaciones:
                comp = imputacion.comprobante
                comp.saldo_pendiente += imputacion.monto_imputado
                comp.save()

            for valor in valores:
                valor.destino.saldo_monto -= valor.monto
                valor.destino.save()
                if valor.tipo.es_cheque:
                    Cheque.objects.filter(numero=valor.referencia, cuit_librador=valor.cuit_librador).update(
                        estado=Cheque.Estado.ANULADO)

            self.finanzas_aplicadas = False
            self.save(update_fields=['finanzas_aplicadas'])

    def __str__(self):
        return f"Recibo X {self.numero or '?'} - {self.cliente}"

    class Meta:
        verbose_name = "Recibo de Cobro"
        verbose_name_plural = "Recibos de Cobro"


class ReciboImputacion(models.Model):
    recibo = models.ForeignKey(Recibo, related_name='imputaciones', on_delete=models.CASCADE)
    comprobante = models.ForeignKey(ComprobanteVenta, on_delete=models.PROTECT)
    monto_imputado = models.DecimalField(max_digits=14, decimal_places=2)

    def __str__(self): return f"Pago a {self.comprobante}"


class ReciboValor(models.Model):
    recibo = models.ForeignKey(Recibo, related_name='valores', on_delete=models.CASCADE)
    tipo = models.ForeignKey(TipoValor, on_delete=models.PROTECT)
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    destino = models.ForeignKey(CuentaFondo, on_delete=models.PROTECT, verbose_name="Caja/Cuenta Destino")
    cheque_tercero = models.ForeignKey(Cheque, on_delete=models.SET_NULL, null=True, blank=True)
    banco_origen = models.ForeignKey(Banco, on_delete=models.SET_NULL, null=True, blank=True)
    referencia = models.CharField(max_length=100, blank=True)
    fecha_cobro = models.DateField(null=True, blank=True)
    cuit_librador = models.CharField(max_length=11, blank=True)

    def __str__(self): return f"{self.tipo} ${self.monto}"


# --- SIGNALS (LIMPIAS) ---
@receiver(post_save, sender=ComprobanteVenta)
def aplicar_stock_venta(sender, instance, **kwargs):
    afecta_stock = instance.tipo_comprobante.afecta_stock if instance.tipo_comprobante else False
    if instance.estado == ComprobanteVenta.Estado.CONFIRMADO and afecta_stock and not instance.stock_aplicado:
        if not instance.items.exists():
            return
        for item in instance.items.all():
            StockService.ajustar_stock(item.articulo, instance.deposito, item.cantidad, 'RESTAR')
        ComprobanteVenta.objects.filter(pk=instance.pk).update(stock_aplicado=True)


@receiver(post_save, sender=Recibo)
def trigger_finanzas_recibo(sender, instance, **kwargs):
    # Solo reversión al anular
    if instance.estado == Recibo.Estado.ANULADO:
        instance.revertir_finanzas()


@receiver(pre_delete, sender=Recibo)
def reversar_al_eliminar_recibo(sender, instance, **kwargs):
    if instance.finanzas_aplicadas:
        # Lectura ansiosa para evitar que CASCADE borre antes de tiempo
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
                    Cheque.objects.filter(numero=valor.referencia, cuit_librador=valor.cuit_librador).update(
                        estado=Cheque.Estado.ANULADO)


from inventario.models import Articulo


@receiver(post_save, sender=Articulo)
def manage_default_product_price(sender, instance: Articulo, created, **kwargs):
    if getattr(instance, '_from_pricelist_sync', False): return
    if instance.perfil not in [Articulo.Perfil.COMPRA_VENTA, Articulo.Perfil.VENTA]: return
    default_list = PriceList.objects.filter(is_default=True).first()
    if not default_list: return
    obj, created_price = ProductPrice.objects.update_or_create(product=instance, price_list=default_list,
                                                               min_quantity=1,
                                                               defaults={'price_monto': instance.precio_venta_monto,
                                                                         'price_moneda': instance.precio_venta_moneda})


@receiver(post_save, sender=ProductPrice)
def sync_product_price_to_article(sender, instance: ProductPrice, created, **kwargs):
    if not instance.price_list.is_default or instance.min_quantity > 1: return
    articulo = instance.product
    if (
            articulo.precio_venta_monto == instance.price_monto and articulo.precio_venta_moneda == instance.price_moneda): return
    articulo.precio_venta_monto = instance.price_monto
    articulo.precio_venta_moneda = instance.price_moneda
    if articulo.precio_costo_monto > 0:
        try:
            nueva_utilidad = ((instance.price_monto / articulo.precio_costo_monto) - 1) * 100
            articulo.utilidad = nueva_utilidad
        except Exception:
            pass
    articulo._from_pricelist_sync = True
    articulo.save()