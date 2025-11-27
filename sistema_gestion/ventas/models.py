# ventas/models.py (VERSIÓN CORREGIDA: TRANSACTION + CAMPOS OPCIONALES)

from django.db import models
from django.db.models import Sum
from decimal import Decimal
from djmoney.money import Money
from django.db import transaction
from django.utils import timezone
from inventario.services import StockService

from django.dispatch import receiver
from django.db.models.signals import post_save

# Función local para evitar importación circular
def get_default_moneda_pk():
    from parametros.models import Moneda
    moneda, created = Moneda.objects.get_or_create(
        es_base=True,
        defaults={'nombre': 'Peso Argentino', 'simbolo': 'ARS', 'cotizacion': 1.00}
    )
    return moneda.pk


# --- MODELOS EXISTENTES ---

class Cliente(models.Model):
    entidad = models.OneToOneField('entidades.Entidad', on_delete=models.CASCADE, primary_key=True)
    price_list = models.ForeignKey(
        'PriceList',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Lista de Precios Asignada"
    )

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

    # Serie / Talonario
    serie = models.ForeignKey('parametros.SerieDocumento', on_delete=models.PROTECT,
                              null=True, blank=True, verbose_name="Serie / Talonario",
                              help_text="Seleccione la serie para numeración automática")

    # CORRECCIÓN 2: Hacemos opcional el tipo de comprobante para que la Serie lo pueda llenar
    tipo_comprobante = models.ForeignKey('parametros.TipoComprobante', on_delete=models.PROTECT,
                                         verbose_name="Tipo de Comprobante",
                                         null=True, blank=True)

    letra = models.CharField(max_length=1, editable=False)
    punto_venta = models.PositiveIntegerField(default=1, verbose_name="Punto de Venta")

    # CORRECCIÓN 3: El número también opcional para que sea automático
    numero = models.PositiveIntegerField(verbose_name="Número", blank=True,
                                         null=True)

    cliente = models.ForeignKey('Cliente', on_delete=models.PROTECT, verbose_name="Cliente")
    fecha = models.DateField(verbose_name="Fecha del Comprobante", default=timezone.now)
    estado = models.CharField(max_length=2, choices=Estado.choices, default=Estado.BORRADOR, verbose_name="Estado")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    impuestos = models.JSONField(default=dict, editable=False, help_text="Desglose de impuestos calculados")
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    deposito = models.ForeignKey('inventario.Deposito', on_delete=models.PROTECT, null=True, blank=True)

    stock_aplicado = models.BooleanField(default=False, editable=False)

    def save(self, *args, **kwargs):
        # 1. AUTOMATIZACIÓN POR SERIE
        if self.serie:
            # Copiar configuración base
            self.tipo_comprobante = self.serie.tipo_comprobante
            self.letra = self.serie.tipo_comprobante.letra
            self.punto_venta = self.serie.punto_venta

            # Asignar depósito por defecto si no se eligió uno
            if not self.deposito and self.serie.deposito_defecto:
                self.deposito = self.serie.deposito_defecto

            # Generación de Número (Solo si no tiene número y la serie es automática)
            if not self.serie.es_manual and not self.numero:
                from parametros.models import SerieDocumento
                # Bloqueo atómico para evitar duplicados en concurrencia
                with transaction.atomic():
                    serie_lock = SerieDocumento.objects.select_for_update().get(pk=self.serie.pk)
                    siguiente = serie_lock.ultimo_numero + 1
                    self.numero = siguiente

                    # Actualizar contador
                    serie_lock.ultimo_numero = siguiente
                    serie_lock.save()

        # 2. LÓGICA LEGADA (Fallback)
        if self.tipo_comprobante and not self.letra:
            self.letra = self.tipo_comprobante.letra

        from inventario.models import Deposito
        if not self.deposito_id and self.deposito is None:
            deposito_principal = Deposito.objects.filter(es_principal=True).first()
            if deposito_principal:
                self.deposito = deposito_principal

        super().save(*args, **kwargs)

    def __str__(self):
        tipo_nombre = self.tipo_comprobante.nombre if self.tipo_comprobante else "Comprobante"
        return f"{tipo_nombre} {self.numero_completo} a {self.cliente}"

    @property
    def numero_completo(self):
        num = self.numero if self.numero else 0
        return f"{self.letra} {self.punto_venta:05d}-{num:08d}"

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


# --- MODELOS DE LISTAS DE PRECIOS DE VENTA ---

class PriceList(models.Model):
    """
    Listas de precios de venta múltiples (Ej: 'Minorista', 'Mayorista', 'VIP').
    """
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

    class Meta:
        unique_together = ['product', 'price_list', 'min_quantity']
        ordering = ['min_quantity']
        verbose_name = "Precio de Producto"
        verbose_name_plural = "Precios de Productos"

    @property
    def price(self):
        return Money(self.price_monto, self.price_moneda.simbolo)


@receiver(post_save, sender=ComprobanteVenta)
def aplicar_stock_venta(sender, instance, **kwargs):
    # Verificamos si el tipo de comprobante afecta stock
    afecta_stock = instance.tipo_comprobante.afecta_stock if instance.tipo_comprobante else True

    if instance.estado == ComprobanteVenta.Estado.CONFIRMADO and afecta_stock and not instance.stock_aplicado:

        items = instance.items.all()
        # CORRECCIÓN CRÍTICA: Esperar a que haya items
        if not items.exists():
            return

        for item in items:
            # En ventas RESTAMOS stock
            StockService.ajustar_stock(item.articulo, instance.deposito, item.cantidad, 'RESTAR')

        # Bloqueamos para que no se aplique de nuevo
        ComprobanteVenta.objects.filter(pk=instance.pk).update(stock_aplicado=True)