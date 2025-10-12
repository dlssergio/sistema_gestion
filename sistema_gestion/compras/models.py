# en compras/models.py (Refactorizado con django-money)

from django.db import models
from django.db import transaction
from entidades.models import Entidad
from parametros.models import Contador, TipoComprobante, Role
from inventario.models import Articulo, Deposito
from djmoney.models.fields import MoneyField  # <<< CAMBIO: Importamos MoneyField


class Proveedor(models.Model):
    entidad = models.OneToOneField(Entidad, on_delete=models.CASCADE, primary_key=True)
    codigo_proveedor = models.CharField(max_length=50, unique=True, blank=True, null=True,
                                        verbose_name="Código de Proveedor",
                                        help_text="Dejar en blanco para generar un código automático.")
    nombre_fantasia = models.CharField(max_length=255, blank=True, null=True, verbose_name="Nombre de Fantasía")

    # <<< CAMBIO CLAVE: Volvemos a DecimalField y añadimos un default=0 >>>
    limite_credito = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Límite de Crédito")

    roles = models.ManyToManyField(
        Role,
        blank=True,
        help_text="Roles que tienen permiso para gestionar este proveedor."
    )

    def save(self, *args, **kwargs):
        if not self.codigo_proveedor:
            try:
                with transaction.atomic():
                    contador = Contador.objects.select_for_update().get(nombre='codigo_proveedor')
                    contador.ultimo_valor += 1
                    self.codigo_proveedor = f"{contador.prefijo}{str(contador.ultimo_valor).zfill(5)}"
                    contador.save()
            except Contador.DoesNotExist:
                print("ADVERTENCIA: No se encontró el contador 'codigo_proveedor'.")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.entidad.razon_social

    class Meta:
        verbose_name = "Proveedor"
        verbose_name_plural = "Proveedores"


class ComprobanteCompra(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = 'BR', 'Borrador'
        FINALIZADO = 'FN', 'Finalizado'
        ANULADO = 'AN', 'Anulado'

    tipo_comprobante = models.ForeignKey('parametros.TipoComprobante', on_delete=models.PROTECT,
                                         verbose_name="Tipo de Comprobante")
    letra = models.CharField(max_length=1, editable=False)
    punto_venta = models.PositiveIntegerField(default=1, verbose_name="Punto de Venta")
    numero = models.PositiveIntegerField(verbose_name="Número")
    proveedor = models.ForeignKey('Proveedor', on_delete=models.PROTECT, verbose_name="Proveedor")
    fecha = models.DateField(verbose_name="Fecha del Comprobante")
    estado = models.CharField(max_length=2, choices=Estado.choices, default=Estado.BORRADOR, verbose_name="Estado")

    # <<< CAMBIO: total ahora es un MoneyField >>>
    total = MoneyField(max_digits=12, decimal_places=2, default_currency='ARS', default=0, editable=False)

    comprobante_origen = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True,
                                           related_name='comprobantes_derivados')
    deposito = models.ForeignKey(Deposito, on_delete=models.PROTECT, null=True, blank=True)

    def save(self, *args, **kwargs):
        # ... (lógica de save sin cambios) ...
        if self.tipo_comprobante: self.letra = self.tipo_comprobante.letra
        if not self.deposito_id:
            deposito_principal = Deposito.objects.filter(es_principal=True).first()
            if deposito_principal:
                self.deposito = deposito_principal
        super().save(*args, **kwargs)

    @property
    def numero_completo(self):
        return f"{self.letra} {self.punto_venta:05d}-{self.numero:08d}"

    def __str__(self):
        return f"{self.tipo_comprobante.nombre} {self.numero_completo} de {self.proveedor}"

    class Meta:
        verbose_name = "Comprobante de Compra"
        verbose_name_plural = "Comprobantes de Compra"
        unique_together = ('tipo_comprobante', 'punto_venta', 'numero', 'proveedor')


class ComprobanteCompraItem(models.Model):
    comprobante = models.ForeignKey(ComprobanteCompra, related_name='items', on_delete=models.CASCADE)
    articulo = models.ForeignKey(Articulo, on_delete=models.PROTECT, verbose_name="Artículo")
    cantidad = models.DecimalField(max_digits=10, decimal_places=3)

    # <<< CAMBIO: moneda_costo y precio_costo_unitario_original reemplazados por un MoneyField >>>
    precio_costo_unitario = MoneyField(max_digits=12, decimal_places=2, default_currency='ARS', default=0,
                                       verbose_name="Costo Unitario")

    # <<< CAMBIO: La propiedad ahora opera con objetos Money >>>
    @property
    def subtotal(self):
        # La multiplicación de un Decimal (cantidad) por un Money (precio) resulta en un Money. ¡Perfecto!
        return self.cantidad * self.precio_costo_unitario

    def __str__(self): return f"{self.cantidad} x {self.articulo.descripcion}"