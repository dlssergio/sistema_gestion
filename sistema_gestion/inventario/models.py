# inventario/models.py (VERSIÓN FINAL, ROBUSTA Y CONSISTENTE)

from django.db import models, transaction
from django.db.models import Sum, Q
from decimal import Decimal
from djmoney.money import Money
from django.core.exceptions import ObjectDoesNotExist

# --- INICIO DE LA CORRECCIÓN ---
# Se actualizan las importaciones: se elimina ReglaImpuesto y se añaden los nuevos modelos.
from parametros.models import (
    Contador, Moneda, UnidadMedida, get_default_unidad_medida,
    Impuesto, get_default_moneda_pk, GrupoUnidadMedida, CategoriaImpositiva
)
# --- FIN DE LA CORRECCIÓN ---


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
    ean = models.CharField(max_length=13, blank=True, null=True, db_index=True,
                           verbose_name="Código de Barras EAN",
                           help_text="Código de barras EAN-13.")
    qr = models.CharField(max_length=255, blank=True, null=True, verbose_name="Código QR")
    descripcion = models.CharField(max_length=255, verbose_name="Descripción")
    perfil = models.CharField(max_length=2, choices=Perfil.choices, default=Perfil.COMPRA_VENTA,
                              verbose_name="Perfil del Artículo")
    marca = models.ForeignKey(Marca, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Marca")
    rubro = models.ForeignKey(Rubro, on_delete=models.PROTECT, verbose_name="Rubro")
    grupo_unidades = models.ForeignKey(GrupoUnidadMedida, on_delete=models.PROTECT, null=True, blank=True,
                                       verbose_name="Grupo de Unidades",
                                       help_text="Define la categoría de unidades del artículo (Peso, Volumen, etc.)")
    unidad_medida_stock = models.ForeignKey(UnidadMedida, on_delete=models.PROTECT, default=get_default_unidad_medida,
                                            related_name='articulos_stock',
                                            verbose_name="U.M. de Stock")
    unidad_medida_venta = models.ForeignKey(UnidadMedida, on_delete=models.PROTECT, default=get_default_unidad_medida,
                                            related_name='articulos_venta',
                                            verbose_name="U.M. de Venta")
    precio_costo_monto = models.DecimalField(max_digits=14, decimal_places=4, default=0, verbose_name="Monto de Costo")
    precio_costo_moneda = models.ForeignKey(Moneda, on_delete=models.PROTECT, default=get_default_moneda_pk,
                                            verbose_name="Moneda de Costo", related_name='articulos_costo')
    precio_venta_monto = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Monto de Venta")
    precio_venta_moneda = models.ForeignKey(Moneda, on_delete=models.PROTECT, default=get_default_moneda_pk,
                                            verbose_name="Moneda de Venta", related_name='articulos_venta_moneda')
    utilidad = models.DecimalField(max_digits=10, decimal_places=2, default=0.00,
                                   help_text="Porcentaje de ganancia sobre el costo.", verbose_name="Utilidad (%)")

    # --- INICIO DE LA CORRECCIÓN ---
    # Se reemplaza el ForeignKey a ReglaImpuesto por los nuevos campos.
    categoria_impositiva = models.ForeignKey(CategoriaImpositiva, on_delete=models.PROTECT, null=True, blank=True,
                                             verbose_name="Categoría Impositiva")
    impuestos = models.ManyToManyField(Impuesto, blank=True,
                                       verbose_name="Impuestos Aplicables",
                                       help_text="Seleccione todos los impuestos que aplican a este artículo (IVA, Internos, etc.)")
    # --- FIN DE LA CORRECCIÓN ---

    proveedores = models.ManyToManyField('compras.Proveedor', through='ProveedorArticulo',
                                         related_name='articulos_directos', blank=True,
                                         verbose_name="Proveedores Relacionados")
    administra_stock = models.BooleanField(default=True, verbose_name="¿Administra Stock?")
    esta_activo = models.BooleanField(default=True, verbose_name="¿Está Activo?")
    observaciones = models.TextField(blank=True, null=True, verbose_name="Observaciones")
    nota = models.TextField(blank=True, null=True, verbose_name="Nota Interna")

    @property
    def precio_costo(self):
        return Money(self.precio_costo_monto, self.precio_costo_moneda.simbolo)

    @property
    def precio_venta(self):
        return Money(self.precio_venta_monto, self.precio_venta_moneda.simbolo)

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
                    contador, created = Contador.objects.get_or_create(nombre='codigo_articulo',
                                                                       defaults={'prefijo': 'A', 'ultimo_valor': 0})
                    contador.ultimo_valor += 1
                    self.cod_articulo = f"{contador.prefijo}{str(contador.ultimo_valor).zfill(5)}"
                    contador.save()
            except Contador.DoesNotExist:
                pass

        # ... (lógica de cálculo de precios sin cambios) ...
        if self.precio_costo_monto > 0 and self.utilidad is not None:
            costo_en_base = self.precio_costo_monto * self.precio_costo_moneda.cotizacion
            venta_en_base = costo_en_base * (Decimal(1) + (self.utilidad / Decimal(100)))
            if self.precio_venta_moneda.cotizacion > 0:
                self.precio_venta_monto = venta_en_base / self.precio_venta_moneda.cotizacion
            else:
                self.precio_venta_monto = venta_en_base

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
            ProveedorArticulo.objects.filter(articulo=self.articulo).exclude(pk=self.pk).update(es_fuente_de_verdad=False)
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
            return f"1 {self.unidad_externa.simbolo} = {self.factor_conversion} {self.articulo.unidad_medida_stock.simbolo}"
        except:
            return "Conversión de Unidad Inválida"