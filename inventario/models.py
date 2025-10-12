# en inventario/models.py (VERSIÓN FINAL CON LÓGICA SAVE() CORREGIDA Y ROBUSTA)

from django.db import models, transaction
from django.db.models import Sum
from decimal import Decimal
from parametros.models import Contador, Impuesto, Moneda
from djmoney.models.fields import MoneyField
from djmoney.money import Money


# ... (Clases Marca, Rubro, Deposito, StockArticulo sin cambios) ...
class Marca(models.Model):
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre")

    def __str__(self): return self.nombre

    class Meta:
        verbose_name = "Marca"
        verbose_name_plural = "Marcas"


class Rubro(models.Model):
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre")

    def __str__(self): return self.nombre

    class Meta:
        verbose_name = "Rubro"
        verbose_name_plural = "Rubros"


class Deposito(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    direccion = models.CharField(max_length=255, blank=True, null=True)
    es_principal = models.BooleanField(default=False,
                                       help_text="Marcar si este es el depósito principal o por defecto.")

    def __str__(self): return self.nombre

    class Meta:
        verbose_name = "Depósito"
        verbose_name_plural = "Depósitos"


class StockArticulo(models.Model):
    articulo = models.ForeignKey('Articulo', on_delete=models.CASCADE, related_name="stocks")
    deposito = models.ForeignKey(Deposito, on_delete=models.CASCADE)
    cantidad = models.DecimalField(max_digits=12, decimal_places=3, default=0)

    def __str__(self): return f"{self.articulo.descripcion} en {self.deposito.nombre}: {self.cantidad}"

    class Meta:
        unique_together = ('articulo', 'deposito')
        verbose_name = "Stock por Depósito"
        verbose_name_plural = "Stocks por Depósito"


class Articulo(models.Model):
    class UnidadMedida(models.TextChoices):
        UNIDADES = 'UN', 'Unidades'
        KILOGRAMO = 'KG', 'Kilogramo'
        LITRO = 'LT', 'Litro'
        METRO = 'MT', 'Metro'

    class Perfil(models.TextChoices):
        COMPRA_VENTA = 'CV', 'Compra/Venta'
        COMPRA = 'CO', 'Compra'
        VENTA = 'VE', 'Venta'

    cod_articulo = models.CharField(max_length=50, unique=True, primary_key=True, blank=True,
                                    verbose_name="Código de Artículo",
                                    help_text="Dejar en blanco para generar un código automático.")
    ean = models.CharField(max_length=13, blank=True, null=True, db_index=True, verbose_name="Código de Barras (EAN)")
    qr_code = models.CharField(max_length=255, blank=True, null=True, verbose_name="Código QR")
    descripcion = models.CharField(max_length=255, verbose_name="Descripción")
    perfil = models.CharField(max_length=2, choices=Perfil.choices, default=Perfil.COMPRA_VENTA,
                              verbose_name="Perfil del Artículo")
    marca = models.ForeignKey(Marca, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Marca")
    rubro = models.ForeignKey(Rubro, on_delete=models.PROTECT, verbose_name="Rubro")
    unidad_medida = models.CharField(max_length=2, choices=UnidadMedida.choices, default=UnidadMedida.UNIDADES,
                                     verbose_name="Unidad de Medida")

    precio_costo = MoneyField(max_digits=12, decimal_places=2, default_currency='ARS', default=0,
                              verbose_name="Precio de Costo")
    utilidad = models.DecimalField(max_digits=5, decimal_places=2, default=30.00,
                                   help_text="Porcentaje de ganancia sobre el costo. Modificar este campo recalculará el Precio de Venta.",
                                   verbose_name="Utilidad (%)")
    precio_venta = MoneyField(max_digits=12, decimal_places=2, default_currency='ARS', default=0,
                              verbose_name="Precio de Venta")
    impuesto = models.ForeignKey(Impuesto, on_delete=models.PROTECT, verbose_name="Impuesto (IVA)")
    administra_stock = models.BooleanField(default=True, verbose_name="¿Administra Stock?")
    stock_minimo = models.DecimalField(max_digits=12, decimal_places=3, default=0, verbose_name="Stock Mínimo")
    stock_maximo = models.DecimalField(max_digits=12, decimal_places=3, default=0, verbose_name="Stock Máximo")
    punto_pedido = models.DecimalField(max_digits=12, decimal_places=3, default=0, verbose_name="Punto de Pedido")
    esta_activo = models.BooleanField(default=True, verbose_name="¿Está Activo?")
    observaciones = models.TextField(blank=True, null=True, verbose_name="Observaciones")
    nota = models.TextField(blank=True, null=True, verbose_name="Nota Interna")

    @property
    def precio_final_calculado(self):
        if self.precio_venta and self.impuesto:
            return self.precio_venta * (1 + (self.impuesto.tasa / Decimal(100)))
        return Money(0, self.precio_venta.currency if self.precio_venta else 'ARS')

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

        old_instance = Articulo.objects.filter(pk=self.pk).first()
        is_new = old_instance is None

        # Determinar qué campo cambió el usuario
        utilidad_changed = not is_new and self.utilidad != old_instance.utilidad
        costo_changed = not is_new and self.precio_costo != old_instance.precio_costo
        venta_changed = not is_new and self.precio_venta != old_instance.precio_venta

        try:
            monedas = {m.simbolo: m.cotizacion for m in Moneda.objects.all()}
            cotizacion_costo = monedas.get(str(self.precio_costo.currency), Decimal('1.0'))
            cotizacion_venta = monedas.get(str(self.precio_venta.currency), Decimal('1.0'))

            costo_en_base = self.precio_costo.amount * cotizacion_costo

            # Prioridad 1: Si la utilidad o el costo cambian (o es nuevo), recalcular precio de venta.
            if is_new or utilidad_changed or costo_changed:
                venta_en_base = costo_en_base * (1 + (self.utilidad / Decimal(100)))
                if cotizacion_venta > 0:
                    self.precio_venta = Money(venta_en_base / cotizacion_venta, self.precio_venta.currency)

            # Prioridad 2: Si el precio de venta cambió, recalcular la utilidad.
            elif venta_changed:
                if costo_en_base > 0:
                    venta_en_base = self.precio_venta.amount * cotizacion_venta
                    self.utilidad = ((venta_en_base / costo_en_base) - 1) * 100
                else:
                    self.utilidad = 0
        except Exception as e:
            print(f"ADVERTENCIA: No se pudieron realizar los cálculos de precios. Error: {e}")

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.descripcion} ({self.cod_articulo})"

    class Meta:
        verbose_name = "Artículo"
        verbose_name_plural = "Artículos"