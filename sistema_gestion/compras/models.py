# compras/models.py

from django.db import models, transaction
from decimal import Decimal
from djmoney.models.fields import MoneyField
from djmoney.money import Money
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from entidades.models import Entidad
from parametros.models import Contador, TipoComprobante, Role, UnidadMedida, get_default_unidad_medida


# No se importa nada de 'inventario' para evitar ciclos. Se usan referencias de cadena.

class Proveedor(models.Model):
    entidad = models.OneToOneField(Entidad, on_delete=models.CASCADE, primary_key=True)
    codigo_proveedor = models.CharField(max_length=50, unique=True, blank=True, null=True,
                                        verbose_name="Código de Proveedor",
                                        help_text="Dejar en blanco para generar código automático.")
    nombre_fantasia = models.CharField(max_length=255, blank=True, null=True, verbose_name="Nombre de Fantasía")
    limite_credito = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Límite de Crédito")
    roles = models.ManyToManyField(Role, blank=True, help_text="Roles que pueden gestionar este proveedor.")

    def __str__(self):
        return self.entidad.razon_social

    def save(self, *args, **kwargs):
        if not self.codigo_proveedor:
            try:
                # La lógica de autocompletar código se mueve aquí si es necesario
                with transaction.atomic():
                    contador, created = Contador.objects.get_or_create(nombre='codigo_proveedor',
                                                                       defaults={'prefijo': 'P', 'ultimo_valor': 0})
                    contador.ultimo_valor += 1
                    self.codigo_proveedor = f"{contador.prefijo}{str(contador.ultimo_valor).zfill(5)}"
                    contador.save()
            except Exception:
                pass  # Evita que la creación del proveedor falle si el contador no existe
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Proveedor"
        verbose_name_plural = "Proveedores"


# <<< DESTRUIDO: El modelo ListaPreciosProveedor se elimina por completo. >>>

# <<< ARQUITECTURA CORRECTA: Este modelo representa el precio de un artículo PARA un proveedor. >>>
class PrecioProveedorArticulo(models.Model):
    proveedor = models.ForeignKey(Proveedor, on_delete=models.CASCADE, related_name='precios')
    articulo = models.ForeignKey('inventario.Articulo', on_delete=models.CASCADE, related_name='precios_de_proveedores')
    unidad_medida_compra = models.ForeignKey(
        UnidadMedida, on_delete=models.PROTECT,
        verbose_name="U. de Medida de Compra", default=get_default_unidad_medida
    )
    precio_costo = MoneyField(max_digits=14, decimal_places=4, default_currency='ARS',
                              verbose_name="Precio de Costo de Lista")
    bonificacion_porcentaje = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, verbose_name="Bonificación (%)",
        help_text="Ej: 15% significa que pagas 85 de cada 100 unidades."
    )
    descuentos_adicionales = models.JSONField(
        default=list, blank=True, verbose_name="Descuentos Adicionales por Ítem (%)",
        help_text="Lista de porcentajes en cascada. Usar negativo para descuento. Ej: [-5.0, 2.0]"
    )
    descuentos_financieros = models.JSONField(
        default=list, blank=True, verbose_name="Descuentos/Recargos Financieros (%)",
        help_text="Lista de porcentajes en cascada. Usar negativo para descuento. Ej: [-10.0, 5.0]"
    )
    cantidad_minima = models.DecimalField(max_digits=10, decimal_places=3, default=1, verbose_name="Cantidad Mínima")
    codigo_articulo_proveedor = models.CharField(max_length=50, blank=True, null=True,
                                                 verbose_name="Código de Proveedor")

    @property
    def costo_unitario_efectivo(self):
        from compras.services import CostCalculatorService
        try:
            return CostCalculatorService.calculate_effective_cost(self)
        except Exception as e:
            print(f"Error al calcular costo efectivo: {e}")
            return self.precio_costo

    class Meta:
        verbose_name = "Precio de Proveedor por Artículo"
        verbose_name_plural = "Precios de Proveedor por Artículo"
        unique_together = ('proveedor', 'articulo', 'cantidad_minima', 'unidad_medida_compra')


class ComprobanteCompra(models.Model):
    proveedor = models.ForeignKey('Proveedor', on_delete=models.PROTECT, verbose_name="Proveedor")
    deposito = models.ForeignKey('inventario.Deposito', on_delete=models.PROTECT, null=True, blank=True)

    class Estado(
        models.TextChoices): BORRADOR = 'BR', 'Borrador'; FINALIZADO = 'FN', 'Finalizado'; ANULADO = 'AN', 'Anulado'

    tipo_comprobante = models.ForeignKey('parametros.TipoComprobante', on_delete=models.PROTECT,
                                         verbose_name="Tipo de Comprobante")
    letra = models.CharField(max_length=1, editable=False)
    punto_venta = models.PositiveIntegerField(default=1, verbose_name="Punto de Venta")
    numero = models.PositiveIntegerField(verbose_name="Número")
    fecha = models.DateField(verbose_name="Fecha del Comprobante")
    estado = models.CharField(max_length=2, choices=Estado.choices, default=Estado.BORRADOR, verbose_name="Estado")
    subtotal = MoneyField(max_digits=12, decimal_places=2, default_currency='ARS', default=0, editable=False)
    impuestos = models.JSONField(default=dict, editable=False, help_text="Desglose de impuestos")
    total = MoneyField(max_digits=12, decimal_places=2, default_currency='ARS', default=0, editable=False)
    comprobante_origen = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True,
                                           related_name='comprobantes_derivados')

    def __str__(self): return f"{self.tipo_comprobante.nombre} de {self.proveedor}"

    def save(self, *args, **kwargs):
        if self.tipo_comprobante: self.letra = self.tipo_comprobante.letra
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Comprobante de Compra";
        verbose_name_plural = "Comprobantes de Compra"


class ComprobanteCompraItem(models.Model):
    comprobante = models.ForeignKey(ComprobanteCompra, related_name='items', on_delete=models.CASCADE)
    articulo = models.ForeignKey('inventario.Articulo', on_delete=models.PROTECT, verbose_name="Artículo")
    cantidad = models.DecimalField(max_digits=10, decimal_places=3)
    precio_costo_unitario = MoneyField(max_digits=12, decimal_places=2, default_currency='ARS', default=0,
                                       verbose_name="Costo Unitario")
    datos_costo_efectivo = models.JSONField(default=dict, editable=False)

    @property
    def subtotal(self): return (self.cantidad or Decimal(0)) * self.precio_costo_unitario

    def __str__(self): return f"{self.cantidad} x {self.articulo.descripcion if self.articulo else 'N/A'}"


@receiver(post_save, sender=PrecioProveedorArticulo)
def actualizar_costo_articulo_signal(sender, instance, **kwargs):
    articulo = instance.articulo
    proveedor_precio = instance.proveedor
    if articulo.proveedor_actualiza_precio == proveedor_precio:
        costo_efectivo_actualizado = instance.costo_unitario_efectivo
        if articulo.precio_costo != costo_efectivo_actualizado:
            articulo.precio_costo = costo_efectivo_actualizado
            articulo.save()