# inventario/models.py

from django.db import models, transaction
from django.db.models import Sum, Q
from decimal import Decimal
from djmoney.models.fields import MoneyField
from djmoney.money import Money
from parametros.models import Contador, Moneda, UnidadMedida, get_default_unidad_medida, ReglaImpuesto
from django.core.exceptions import ObjectDoesNotExist


class Marca(models.Model):
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre")

    def __str__(self): return self.nombre

    class Meta: verbose_name = "Marca"; verbose_name_plural = "Marcas"


class Rubro(models.Model):
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre")

    def __str__(self): return self.nombre

    class Meta: verbose_name = "Rubro"; verbose_name_plural = "Rubros"


class Deposito(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    direccion = models.CharField(max_length=255, blank=True, null=True)
    es_principal = models.BooleanField(default=False, help_text="Marcar si este es el depósito principal.")

    def __str__(self): return self.nombre

    class Meta: verbose_name = "Depósito"; verbose_name_plural = "Depósitos"


class StockArticulo(models.Model):
    articulo = models.ForeignKey('Articulo', on_delete=models.CASCADE, related_name="stocks")
    deposito = models.ForeignKey(Deposito, on_delete=models.CASCADE)
    cantidad = models.DecimalField(max_digits=12, decimal_places=3, default=0)

    def __str__(self): return f"{self.articulo.descripcion} en {self.deposito.nombre}: {self.cantidad}"

    class Meta:
        unique_together = ('articulo', 'deposito')
        verbose_name = "Stock por Depósito";
        verbose_name_plural = "Stocks por Depósito"


class Articulo(models.Model):
    class Perfil(models.TextChoices):
        COMPRA_VENTA = 'CV', 'Compra/Venta'
        COMPRA = 'CO', 'Compra'
        VENTA = 'VE', 'Venta'

    cod_articulo = models.CharField(max_length=50, unique=True, primary_key=True, blank=True,
                                    verbose_name="Código de Artículo",
                                    help_text="Dejar en blanco para generar código automático.")
    descripcion = models.CharField(max_length=255, verbose_name="Descripción")
    perfil = models.CharField(max_length=2, choices=Perfil.choices, default=Perfil.COMPRA_VENTA,
                              verbose_name="Perfil del Artículo")
    marca = models.ForeignKey(Marca, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Marca")
    rubro = models.ForeignKey(Rubro, on_delete=models.PROTECT, verbose_name="Rubro")
    unidad_medida_stock = models.ForeignKey(UnidadMedida, on_delete=models.PROTECT, default=get_default_unidad_medida,
                                            verbose_name="Unidad de Medida de Stock",
                                            help_text="La unidad en la que se controla el inventario (la más pequeña).")
    precio_costo = MoneyField(max_digits=12, decimal_places=2, default_currency='ARS', default=0,
                              verbose_name="Precio de Costo")
    utilidad = models.DecimalField(max_digits=5, decimal_places=2, default=0.00,
                                   help_text="Porcentaje de ganancia sobre el costo.", verbose_name="Utilidad (%)")
    precio_venta = MoneyField(max_digits=12, decimal_places=2, default_currency='ARS', default=0,
                              verbose_name="Precio de Venta")
    impuesto = models.ForeignKey(ReglaImpuesto, on_delete=models.PROTECT, verbose_name="Regla Impositiva",
                                 help_text="El impuesto principal que se aplica al precio de venta.", null=True,
                                 blank=True)

    proveedores = models.ManyToManyField('compras.Proveedor', through='ProveedorArticulo',
                                         related_name='articulos_directos', blank=True,
                                         verbose_name="Proveedores Relacionados")

    administra_stock = models.BooleanField(default=True, verbose_name="¿Administra Stock?")
    esta_activo = models.BooleanField(default=True, verbose_name="¿Está Activo?")
    observaciones = models.TextField(blank=True, null=True, verbose_name="Observaciones")
    nota = models.TextField(blank=True, null=True, verbose_name="Nota Interna")

    @property
    def proveedor_actualiza_precio(self):
        try:
            return self.proveedorarticulo_set.get(es_fuente_de_verdad=True).proveedor
        except ObjectDoesNotExist:
            return None

    @property
    def stock_total(self):
        if self.administra_stock:
            total = self.stocks.aggregate(total_stock=Sum('cantidad'))['total_stock']
            return total if total is not None else Decimal('0.000')
        return Decimal('0.000')

    def save(self, *args, **kwargs):
        if not self.cod_articulo:
            try:
                with transaction.atomic():
                    contador = Contador.objects.select_for_update().get(nombre='codigo_articulo')
                    contador.ultimo_valor += 1
                    self.cod_articulo = f"{contador.prefijo}{str(contador.ultimo_valor).zfill(5)}"
                    contador.save()
            except Contador.DoesNotExist:
                pass
        if self.precio_costo.amount > 0 and self.utilidad is not None:
            self.precio_venta = self.precio_costo * (1 + (self.utilidad / Decimal(100)))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.descripcion} ({self.cod_articulo})"

    class Meta:
        verbose_name = "Artículo";
        verbose_name_plural = "Artículos"


class ProveedorArticulo(models.Model):
    proveedor = models.ForeignKey('compras.Proveedor', on_delete=models.CASCADE)
    articulo = models.ForeignKey('Articulo', on_delete=models.CASCADE)
    es_fuente_de_verdad = models.BooleanField(default=False, verbose_name="Fuente de Costo Base",
                                              help_text="Marcar si este proveedor tiene autoridad para actualizar el precio_costo del artículo.")
    fecha_relacion = models.DateField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.es_fuente_de_verdad:
            ProveedorArticulo.objects.filter(articulo=self.articulo).exclude(pk=self.pk).update(
                es_fuente_de_verdad=False)
        super().save(*args, **kwargs)

    class Meta:
        unique_together = ('proveedor', 'articulo')
        verbose_name = "Proveedor de Artículo";
        verbose_name_plural = "Proveedores de Artículos"
        constraints = [
            models.UniqueConstraint(fields=['articulo'], condition=models.Q(es_fuente_de_verdad=True),
                                    name='unique_fuente_de_verdad_por_articulo')
        ]


class ConversionUnidadMedida(models.Model):
    articulo = models.ForeignKey(Articulo, on_delete=models.CASCADE, related_name="conversiones_uom")
    unidad_externa = models.ForeignKey(UnidadMedida, on_delete=models.PROTECT, related_name="conversiones_externas",
                                       default=get_default_unidad_medida,
                                       help_text="Unidad a convertir (ej: Caja, Botella, Bulto)")
    factor_conversion = models.DecimalField(max_digits=14, decimal_places=6,
                                            help_text="¿Cuántas unidades de stock (la más pequeña) caben en la unidad externa? Ej: 1 Caja = 150 Unidades.")

    class Meta:
        unique_together = ('articulo', 'unidad_externa')
        verbose_name = "Factor de Conversión de U.M.";
        verbose_name_plural = "Factores de Conversión de U.M."

    def __str__(self):
        try:
            return f"1 {self.unidad_externa.abreviatura} = {self.factor_conversion} {self.articulo.unidad_medida_stock.abreviatura}"
        except:
            return "Conversión de Unidad Inválida"