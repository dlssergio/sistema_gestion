from django.db import models
from django.db.models import Sum
from decimal import Decimal

from entidades.models import Entidad
from inventario.models import Articulo, Deposito, StockArticulo
from parametros.models import TipoComprobante


class Cliente(models.Model):
    entidad = models.OneToOneField(Entidad, on_delete=models.CASCADE, primary_key=True)

    def __str__(self): return self.entidad.razon_social

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"


class ComprobanteVenta(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = 'BR', 'Borrador'
        FINALIZADO = 'FN', 'Finalizado'
        ANULADO = 'AN', 'Anulado'

    tipo_comprobante = models.ForeignKey(TipoComprobante, on_delete=models.PROTECT, verbose_name="Tipo de Comprobante")
    letra = models.CharField(max_length=1, editable=False)
    punto_venta = models.PositiveIntegerField(default=1, verbose_name="Punto de Venta")
    numero = models.PositiveIntegerField(verbose_name="Número")
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, verbose_name="Cliente")
    fecha = models.DateField(verbose_name="Fecha del Comprobante")
    estado = models.CharField(max_length=2, choices=Estado.choices, default=Estado.BORRADOR, verbose_name="Estado")

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    impuestos = models.JSONField(default=dict, editable=False, help_text="Desglose de impuestos calculados")
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)

    deposito = models.ForeignKey(Deposito, on_delete=models.PROTECT, null=True, blank=True)

    # <<< CAMBIO CLAVE: El método save() ahora es simple y directo >>>
    def save(self, *args, **kwargs):
        if self.tipo_comprobante: self.letra = self.tipo_comprobante.letra
        if not self.deposito_id and self.deposito is None:
            deposito_principal = Deposito.objects.filter(es_principal=True).first()
            if deposito_principal:
                self.deposito = deposito_principal
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.tipo_comprobante.nombre} {self.numero_completo} a {self.cliente}"

    @property
    def numero_completo(self):
        return f"{self.letra} {self.punto_venta:05d}-{self.numero:08d}"

    class Meta:
        verbose_name = "Comprobante de Venta"
        verbose_name_plural = "Comprobantes de Venta"
        unique_together = ('tipo_comprobante', 'punto_venta', 'numero')


class ComprobanteVentaItem(models.Model):
    comprobante = models.ForeignKey(ComprobanteVenta, related_name='items', on_delete=models.CASCADE)
    articulo = models.ForeignKey(Articulo, on_delete=models.PROTECT, verbose_name="Artículo")
    cantidad = models.DecimalField(max_digits=10, decimal_places=3)
    precio_unitario_original = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Precio Unitario")

    @property
    def subtotal(self):
        return (self.cantidad or Decimal(0)) * (self.precio_unitario_original or Decimal(0))

    def __str__(self):
        return f"{self.cantidad} x {self.articulo.descripcion}"